"""A/B test: does retrying with the server's own "Try again" action beat a bare re-send?

Two arms, alternated on every trial so both see the same backend conditions:

  bare    - retry re-sends the prompt, no action code (what the library does today)
  action  - retry sets inner_req_list[63] = [1001, null, 0]

The server labels 1001 "Try again" and offers it on the very frame that carries
the rejection flag (7/7 error captures), so the retry should be able to name the
rejected generation rather than asking the question again from scratch.

Each trial is one prompt sent until it errors, then one retry. Recovery is the
only outcome measured: did the retry return a real answer?

Run inside gemini-proxy:
    BATCH=batch_03 python tests/scratch/errorcard/probe_action_code.py

Env:
    BATCH     batch directory under /app/runs holding prompt.md (default batch_03)
    MAX       trials per arm (default 12)
    DELAY     seconds between requests (default 1.0)
"""
import asyncio
import json
import os
import sys

# Inside gemini-proxy the library is installed at a fixed container path; on the
# host (e.g. _verify_wiretap.py importing this module) the repo's src/ is used.
_HOST_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "src")
for _p in ("/app/lib/python3.12/site-packages", os.path.abspath(_HOST_SRC)):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

from gemini_webapi import GeminiClient  # noqa: E402
from gemini_webapi.constants import ACTION_CODE_INDEX, TRY_AGAIN_ACTION_CODE  # noqa: E402

COOKIES = os.getenv("GEMINI_COOKIES_PATH", "/data/cookies/gemini_cookies.json")
BATCH = os.getenv("BATCH", "batch_03")
PROMPT_PATH = os.getenv("PROMPT_PATH") or f"/app/runs/{BATCH}/prompt.md"
MAX = int(os.getenv("MAX", "12"))
DELAY = float(os.getenv("DELAY", "1.0"))
OUT = os.getenv("OUT") or "/app/action_code_results.json"

class WireTap:
    """Records the action code actually put on the wire for each generation.

    A single _generate() also issues ancillary batchexecute calls whose bodies
    carry a "f.req" of a completely different shape, so bodies are selected by
    shape rather than by arrival order. Taking the last one captured silently
    reads a usage-info payload instead of the generation.
    """

    def __init__(self):
        self.slot63 = None
        self.captured = 0

    @staticmethod
    def parse(body):
        """(is_generation, slot63) for a request body.

        slot63 is None both for a non-generation body and for a generation that
        leaves the slot unset, so the flag cannot be inferred from the value.
        """
        if not isinstance(body, dict):
            return False, None
        freqs = body.get("f.req")
        if not isinstance(freqs, str):
            return False, None
        try:
            outer = json.loads(freqs)
        except Exception:
            return False, None
        if not (isinstance(outer, list) and len(outer) == 2
                and isinstance(outer[1], str)):
            return False, None
        try:
            inner = json.loads(outer[1])
        except Exception:
            return False, None
        if not (isinstance(inner, list) and len(inner) == 81):
            return False, None
        return True, inner[ACTION_CODE_INDEX]

    def install(self, client):
        sess = client._live_client
        orig = sess.request

        async def request(*a, **kw):
            is_generation, value = self.parse(kw.get("data"))
            if is_generation:
                self.slot63 = value
                self.captured += 1
            return await orig(*a, **kw)

        sess.request = request


async def one_request(client, prompt, action_code=None):
    """Send one generation.

    Returns (text, was_error_card, slot63_as_sent). The error verdict comes from
    the structural flag the client sets on each candidate, not from matching
    wording, so an unlisted phrasing still counts as a failure.
    """
    last_text = ""
    flagged = False
    tap = client._action_tap

    async for chunk in client._generate(
        prompt=prompt,
        temporary=False,
        action_code=action_code,
    ):
        last_text = chunk.text or ""
        if any(getattr(c, "is_error_card", False) for c in (chunk.candidates or [])):
            flagged = True

    slot63 = tap.slot63

    return last_text, flagged, slot63


async def trial(client, prompt, arm):
    """One prompt, up to 2 attempts. Returns a result dict."""
    action = TRY_AGAIN_ACTION_CODE if arm == "action" else None

    text, first_error, slot63 = await one_request(client, prompt, None)

    if not first_error:
        return {
            "arm": arm, "errored": False, "attempts": 1,
            "first_len": len(text), "recovered_len": None,
            "slot63_first": slot63, "slot63_retry": None,
        }

    await asyncio.sleep(DELAY)
    retry_text, retry_error, slot63b = await one_request(client, prompt, action)

    return {
        "arm": arm,
        "errored": True,
        "attempts": 2,
        "error_text": text[:90],
        "first_len": len(text),
        "recovered": not retry_error,
        "recovered_len": None if retry_error else len(retry_text),
        "retry_head": retry_text[:90],
        "slot63_first": slot63,
        "slot63_retry": slot63b,
    }


async def main():
    d = json.load(open(COOKIES, encoding="utf-8"))
    if not os.path.exists(PROMPT_PATH):
        print(f"NO PROMPT at {PROMPT_PATH}")
        return 3
    prompt = open(PROMPT_PATH, encoding="utf-8").read()

    client = GeminiClient(
        secure_1psid=d["__Secure-1PSID"],
        secure_1psidts=d["__Secure-1PSIDTS"],
        auto_refresh=True,
        refresh_interval=300,
    )
    await client.init()
    print(f"[init] account_status={client.account_status}", flush=True)
    if str(client.account_status) != "1000":
        print("NOT AUTHENTICATED")
        return 2

    tap = WireTap()
    tap.install(client)
    client._action_tap = tap

    print(f"prompt: {PROMPT_PATH} ({len(prompt)} chars)", flush=True)
    print(f"arms: bare vs action({TRY_AGAIN_ACTION_CODE}) at slot {ACTION_CODE_INDEX}", flush=True)
    print(f"trials per arm: {MAX}\n", flush=True)

    results = {"bare": [], "action": []}
    arms = ["bare", "action"]
    idx = 0

    while any(len(results[a]) < MAX for a in arms):
        arm = arms[idx % 2]
        idx += 1
        if len(results[arm]) >= MAX:
            continue

        r = await trial(client, prompt, arm)
        results[arm].append(r)

        if not r["errored"]:
            print(f"  [{arm} {len(results[arm])}/{MAX}] clean ({r['first_len']} chars)", flush=True)
        else:
            verdict = "RECOVERED" if r.get("recovered") else "STILL FAILED"
            print(
                f"  [{arm} {len(results[arm])}/{MAX}] error card -> {verdict} "
                f"(retry {r.get('recovered_len')} chars, slot63={r['slot63_retry']!r})",
                flush=True,
            )
            print(f"      error text: {r['error_text']!r}", flush=True)

        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        await asyncio.sleep(DELAY)

    await client.close()

    print("\n=== SUMMARY ===")
    for arm in arms:
        rows = results[arm]
        errs = [r for r in rows if r["errored"]]
        rec = [r for r in errs if r.get("recovered")]
        print(
            f"  {arm:6s}: {len(errs)} error cards / {len(rows)} trials, "
            f"recovered {len(rec)}/{len(errs)}"
        )
        for r in errs:
            print(f"      slot63_retry={r['slot63_retry']!r} recovered={r.get('recovered')} "
                  f"len={r.get('recovered_len')} head={r.get('retry_head','')[:60]!r}")
    print(f"\nsaved to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
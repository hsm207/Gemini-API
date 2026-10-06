"""Live acceptance check: the retry loop must convert error cards into answers.

Sends the batch_03 trigger (the corpus prompt with the highest observed failure
rate, 3 errors in 10 runs) through the public generate_content() TRIALS times.
Every transient error card must be recovered in-conversation: 3 retries with
exponential backoff, each retry regenerating the failed turn via the server's
"Try again" action code (1001). The run fails if any trial still returns an
error card.

Every outcome is logged so it can be audited against the gemini.google.com web
UI: retry/exhaustion warnings carry cid, failed rcid and the card text; a
recovery INFO line carries the new rcid; the end-of-run mapping prints one
conversation URL per trial. The expected UI picture per trial is a user turn
whose failed variants are marked with error cards plus the regenerated answer.

Cookies go stale within minutes: refresh via the gemini-reauth sidecar
(POST http://localhost:9000/refresh inside the container) immediately before
running. Needs a live account; costs credits.

Run:  python sanity_10x_live.py

Env:
    TRIALS   sends per run (default 10)
    DELAY    seconds between trials (default 2.0)
    COOKIES  path to gemini_cookies.json
             (default: gemini-reauth bind mount in ../google-ai-subscription-bridge)
"""
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))

from gemini_webapi import GeminiClient  # noqa: E402

PROMPT_PATH = os.path.join(HERE, "..", "corpus", "runs", "batch_03", "prompt.md")
COOKIES = os.getenv("COOKIES") or os.path.join(
    HERE, "..", "..", "..", "..", "..",
    "google-ai-subscription-bridge", "data", "cookies", "gemini_cookies.json",
)
TRIALS = int(os.getenv("TRIALS", "10"))
DELAY = float(os.getenv("DELAY", "2.0"))

mapping = []


async def main():
    PROMPT = open(PROMPT_PATH, encoding="utf-8").read()
    with open(COOKIES, encoding="utf-8") as f:
        cookie_data = json.load(f)

    client = GeminiClient(
        secure_1psid=cookie_data["__Secure-1PSID"],
        secure_1psidts=cookie_data["__Secure-1PSIDTS"],
        verbose=False,
    )
    await client.init()
    print(f"account_status={client.account_status}", flush=True)
    if str(client.account_status) != "1000":
        print("AUTH FAILED - aborting before any trial")
        return 2

    ok = 0
    for i in range(1, TRIALS + 1):
        t0 = time.monotonic()
        try:
            out = await client.generate_content(PROMPT)
        except Exception as exc:  # noqa: BLE001 - the run must report, not crash
            print(f"trial {i:2}: EXCEPTION {type(exc).__name__}: {exc!s:.120}", flush=True)
            continue
        dt = time.monotonic() - t0
        text = (out.text or "").strip()
        is_err = any(getattr(c, "is_error_card", False) for c in out.candidates)
        status = "ERROR-CARD" if is_err else "OK"
        cid = out.metadata[0] if out.metadata else None
        final_rcid = out.rcid
        print(
            f"trial {i:2}: {status:10} cid={cid} final_rcid={final_rcid} "
            f"{len(text):5} chars  {dt:6.1f}s  "
            f"{text[:60].replace(chr(10), ' ')!r}",
            flush=True,
        )
        if not is_err:
            ok += 1
        mapping.append(
            f"  trial {i:2}: https://gemini.google.com/app/{cid}  "
            f"final_rcid={final_rcid}  status={status}"
        )
        if i < TRIALS:
            await asyncio.sleep(DELAY)

    print(f"\nRESULT: {ok}/{TRIALS} returned real answers "
          f"({TRIALS - ok} still error-cards after retries)")
    print("\nPer-trial conversation mapping (open in web UI to verify the "
          "error-card variant was retried and replaced by a real answer):")
    for line in mapping:
        print(line)
    return 0 if ok == TRIALS else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

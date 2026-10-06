"""The retry must match the UI's recovery of a failed generation.

Wire-captured 2026-10-05 (error card driven live in the web UI, "Try again"
clicked, StreamGenerate body pulled from the network log): the UI's retry sends
slot 63 as [1001, null, 0] together with the conversation id, and slot 63 is
UNSET on the failing first attempt.

Two things have to hold on every retry attempt:
  1. a chat carrying the FAILED attempt's conversation id is passed in, so the
     server re-enters that conversation instead of allocating a new one;
  2. action_code=1001 is set, which is what the UI's "Try again" sends on a
     failed generation.

It also asserts session_state is per attempt, since a shared dict leaves the
failed attempt's text behind and empties the recovered answer's deltas.

Run:  python _verify_retry_identity.py
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))

from gemini_webapi.client import GeminiClient  # noqa: E402
from gemini_webapi.constants import TRY_AGAIN_ACTION_CODE  # noqa: E402,F401


class FakeCand:
    def __init__(self, text, is_error_card, rcid=""):
        self.text = text
        self.text_delta = text
        self.is_error_card = is_error_card
        self.rcid = rcid


class FakeOutput:
    def __init__(self, text, cid, is_error_card):
        self.text = text
        self.metadata = [cid, "r_test"]
        self.candidates = [FakeCand(text, is_error_card, rcid=f"rc_{cid}")]


async def run(fail_times, label):
    client = GeminiClient.__new__(GeminiClient)
    client.verbose = False
    client.build_label = None
    client.session_id = None
    client.language = "en"
    client.auto_close = False
    client._reqid = 1
    client._sessionid = "s"
    client.access_token = None
    client.account_status = None
    client._model_registry = {}

    seen = []
    cids = [f"c_{i}" for i in range(10)]

    async def fake_sync():
        return None

    client._sync_activity = fake_sync

    async def fake_generate(**kw):
        n = len(seen)
        seen.append(
            {
                "chat_cid": getattr(kw.get("chat"), "cid", None),
                "chat_rcid": getattr(kw.get("chat"), "rcid", None),
                "action_code": kw.get("action_code"),
                "session_state_id": id(kw.get("session_state")),
            }
        )
        is_err = n < fail_times
        return FakeOutput(
            "ERR" if is_err else "REAL ANSWER",
            cids[n],
            is_err,
        )

    async def gen():
        out = None
        async for chunk in fake_generate():
            out = chunk
        return out

    # Bind the retry loop's collaborator.
    client._generate = lambda **kw: _drive(fake_generate, kw)

    output = await client.generate_content(prompt="p")

    print(f"\n--- {label} ---")
    for i, s in enumerate(seen):
        print(
            f"  attempt {i + 1}: chat_cid={s['chat_cid']!r:10} "
            f"chat_rcid={s['chat_rcid']!r:12} session_state={s['session_state_id']}"
        )
    print(f"  attempts={len(seen)}  returned={output.text!r}  "
          f"error_card={output.candidates[0].is_error_card}")
    return seen, output


async def _drive(fake_generate, kw):
    yield await fake_generate(**kw)


def check(seen, fail_times, label):
    problems = []

    # 1. first attempt has no chat and no action code
    if seen[0]["chat_cid"] is not None:
        problems.append("first attempt should have no chat")
    if seen[0]["action_code"] is not None:
        problems.append("first attempt should have no action code")
    if seen[0]["chat_rcid"] is not None:
        problems.append("first attempt should have no rcid")

    # 2. every retry carries the previous attempt's cid and the action code
    for i in range(1, len(seen)):
        if seen[i]["action_code"] != TRY_AGAIN_ACTION_CODE:
            problems.append(
                f"attempt {i + 1} action_code={seen[i]['action_code']!r}, "
                f"expected {TRY_AGAIN_ACTION_CODE} (the UI's Try again)"
            )
        if seen[i]["chat_rcid"] != f"rc_c_{i - 1}":
            problems.append(
                f"attempt {i + 1} chat_rcid={seen[i]['chat_rcid']!r}, "
                f"expected rc_c_{i - 1} (the failed generation)"
            )
        # the failed attempt's conversation is c_<i-1>; the retry must reuse it
        if seen[i]["chat_cid"] != f"c_{i - 1}":
            problems.append(
                f"attempt {i + 1} chat_cid={seen[i]['chat_cid']!r}, "
                f"expected c_{i - 1}"
            )

    # 3. session_state must be fresh per attempt
    ids = [s["session_state_id"] for s in seen]
    if len(set(ids)) != len(ids):
        problems.append("session_state shared across attempts")

    print(f"  {'OK' if not problems else 'FAIL'}: {label}")
    for p in problems:
        print(f"      - {p}")
    return not problems


async def caller_chat_case():
    """A caller-supplied ChatSession must still receive last_output after a retry.

    The loop rebinds `chat` to the failed attempt's conversation, so the caller's
    object has to be captured separately or the write-back lands on the wrong one.
    """
    from gemini_webapi.client import ChatSession

    client = GeminiClient.__new__(GeminiClient)
    client.verbose = False
    client.build_label = None
    client.session_id = None
    client.language = "en"
    client.auto_close = False
    client._reqid = 1
    client._sessionid = "s"
    client.access_token = None
    client.account_status = None
    client._model_registry = {}

    async def noop():
        return None

    client._sync_activity = noop

    n = {"i": 0}

    async def fake_generate(**kw):
        i = n["i"]
        n["i"] += 1
        yield FakeOutput("ERR" if i == 0 else "REAL", f"c_{i}", i == 0)

    client._generate = lambda **kw: fake_generate(**kw)

    caller = ChatSession(geminiclient=client, cid="c_caller", rid="r_caller")
    out = await client.generate_content(prompt="p", chat=caller)

    print("--- caller supplied its own chat ---")
    print(f"  returned text  : {out.text!r}")
    print(f"  caller.cid     : {caller.cid!r} (must stay the caller's)")
    print(f"  caller.last_out: {type(caller.last_output).__name__ if caller.last_output else None}")

    problems = []
    if caller.last_output is not out:
        problems.append("caller's ChatSession did not receive last_output")
    if caller.cid != "c_caller":
        problems.append("caller's cid was overwritten")
    print(f"  {'OK' if not problems else 'FAIL'}: caller's chat object preserved")
    for p in problems:
        print(f"      - {p}")
    return not problems


async def main():
    ok = True
    seen, _ = await run(fail_times=1, label="recover on attempt 2")
    ok &= check(seen, 1, "retry re-enters the failed conversation")

    seen, _ = await run(fail_times=3, label="recover on attempt 4 (last retry)")
    ok &= check(seen, 3, "every retry re-enters its own failed conversation")

    seen, out = await run(fail_times=0, label="never fails")
    ok &= check(seen, 0, "no retry, no chat, no action code")
    ok &= (len(seen) == 1 and out.text == "REAL ANSWER")

    seen, out = await run(fail_times=9, label="exhausted")
    ok &= (len(seen) == 4 and out.text == "ERR" and out.candidates[0].is_error_card)
    print(f"  exhausted: {len(seen)} attempts (1 + 3 retries), returns error card")
    ok &= await caller_chat_case()

    print("\nASSERTIONS PASS" if ok else "\nASSERTIONS FAILED")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))

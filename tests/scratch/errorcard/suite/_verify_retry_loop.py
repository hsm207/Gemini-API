"""Drive the REAL generate_content retry loop with a stubbed _generate.

Everything asserted about attempt counts and log wording in the last report
came from a hand-written simulation of the loop. This runs the actual code so
those claims rest on execution rather than on reading.

Cases:
  A. every attempt returns an error card -> exhaustion path, never seen live
  B. attempt 2 succeeds                      -> the observed recovery shape
  C. no attempt fails                        -> no retry at all
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))

from gemini_webapi.client import GeminiClient
from gemini_webapi.constants import DEFAULT_METADATA
from gemini_webapi.types import Candidate, ModelOutput

LOG = []


class FakeClient(GeminiClient):
    """generate_content with the network replaced by a scripted answer."""

    def __init__(self, script):
        # Deliberately skip GeminiClient.__init__: it builds a live session.
        # Only the attributes generate_content touches before _generate.
        self.auto_close = False
        self.verbose = False
        self._script = script
        self.calls = 0
        self.seen_states = []

    async def _sync_activity(self):
        pass

    async def _generate(self, prompt, session_state=None, **kw):
        self.calls += 1
        # Snapshot what the loop handed us, to see if state carries over.
        self.seen_states.append(
            {k: {kk: len(vv) for kk, vv in v.items()} for k, v in (session_state or {}).items()}
        )
        error = self._script[self.calls - 1]
        await asyncio.sleep(0)  # keep it a real await point
        cand = Candidate(rcid=f"rc_test{self.calls}", text=("ERR" if error else "REAL ANSWER"))
        cand.is_error_card = error
        metadata = list(DEFAULT_METADATA)
        metadata[9] = f"ctx_{self.calls}"
        yield ModelOutput(
            candidates=[cand],
            text=cand.text,
            # ModelOutput.metadata is all-str; DEFAULT_METADATA carries Nones
            # that only the request builder tolerates.
            metadata=["" if v is None else v for v in metadata],
        )


async def run(name, script):
    LOG.clear()
    c = FakeClient(script)
    out = await c.generate_content(prompt="hello")
    print(f"\n=== {name} ===")
    print(f"  HTTP attempts made : {c.calls}")
    print(f"  returned .text     : {out.text!r}")
    print(f"  is_error_card      : {out.candidates[0].is_error_card}")
    print(f"  state len per call : {c.seen_states}")
    return c.calls, out


async def main():
    a_calls, a_out = await run("A. all attempts fail (exhaustion)", [True] * 5)
    b_calls, b_out = await run("B. attempt 2 succeeds", [True, False])
    c_calls, c_out = await run("C. never fails", [False])

    print("\n" + "=" * 60)
    print(f"exhaustion made {a_calls} requests (code allows 4)")
    assert a_calls == 4, f"expected 4, got {a_calls}"
    assert c_calls == 1, f"expected 1, got {c_calls}"
    assert b_calls == 2, f"expected 2, got {b_calls}"
    print("verified: 1 initial + 3 retries = 4 requests max")
    print("verified: no retry when clean")
    print(f"\nexhaustion returns the error card as the answer: "
          f"{a_out.candidates[0].is_error_card} / {a_out.text!r}")
    print("ASSERTIONS PASS")


if __name__ == "__main__":
    asyncio.run(main())
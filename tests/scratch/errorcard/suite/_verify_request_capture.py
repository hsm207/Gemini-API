"""Verify the request-side capture in tools/collect.py.

The retry invariants (same conversation cid, carried rcid, "Try again" action
code) live in the request body, so a collector that only saves responses cannot
verify a retry offline. This drives the tap with a stubbed session - no
network, no cookies - and checks that the body is recorded verbatim, that
headers are captured with credential values replaced by <REDACTED> (so no
cookie or access token can reach the committed corpus), that the response
capture did not regress, and that the sidecar round-trips.

Run:  python _verify_request_capture.py
"""
import asyncio
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import collect  # noqa: E402  (imports GeminiClient, so src/ must be on the path)

SECRET = "__Secure-1PSID=SUPERSECRETCOOKIE"
SECRET2 = "__Secure-1PSIDTS=ROTATEDSUPERSECRET"
# The value this codebase actually sends (constants.py Headers.GEMINI).
FORM_CT = "application/x-www-form-urlencoded;charset=utf-8"
# Shaped like the real f.req: an outer list whose second entry is the inner
# request list as a JSON string, carrying cid/rid/rcid and slot 63.
INNER = ["c_abc123", "rid_1", "rc_first", [None, [None, 63, [1001, None, 0]]]]
FREQ = json.dumps([[None, json.dumps(INNER)]])


class StubResponse:
    status_code = 200
    # The rotated session cookie arrives in a response header; it must never
    # reach disk, but the framing headers beside it must.
    headers = {
        "content-type": "application/json+protobuf",
        "content-length": "7",
        "set-cookie": SECRET2 + "; Path=/; Secure",
    }

    def aiter_content(self):
        async def gen():
            yield b")]}'\n"
            yield b"12\n[[1,2,3]"
        return gen()


class StubSession:
    def __init__(self):
        self.calls = []

    async def request(self, *a, **kw):
        self.calls.append((a, kw))
        return StubResponse()


class StubGeminiClient:
    """Stands in for GeminiClient so main() can be driven without a network."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.account_status = 1000
        self._live_client = StubSession()

    async def init(self):
        pass

    async def close(self):
        pass

    async def _generate(self, prompt=None, temporary=False):
        # The real client drains the stream inside its async-with block; the
        # tap only records a body once the body is fully consumed.
        resp = await self._live_client.request(
            "POST",
            "https://generativelanguage.example/StreamGenerate",
            params={"rpcids": "abc"},
            headers={"Cookie": SECRET},
            data={"at": "TOKEN", "f.req": FREQ},
            stream=True,
        )
        async for _ in resp.aiter_content():
            pass
        yield None


async def run_main_end_to_end():
    """Drive collect.main() with the stub client: what a real collection writes."""
    with tempfile.TemporaryDirectory() as tmp:
        cookies = os.path.join(tmp, "cookies.json")
        prompt = os.path.join(tmp, "prompt.md")
        with open(cookies, "w", encoding="utf-8") as f:
            json.dump({"__Secure-1PSID": "a", "__Secure-1PSIDTS": "b"}, f)
        with open(prompt, "w", encoding="utf-8") as f:
            f.write("hello")

        saved = (collect.GeminiClient, collect.COOKIES, collect.PROMPT_PATH,
                 collect.OUTDIR, collect.N, collect.CAPTURE_REQUESTS,
                 collect.BLOBS, collect.REQUESTS)
        collect.GeminiClient = StubGeminiClient
        collect.COOKIES, collect.PROMPT_PATH, collect.OUTDIR = cookies, prompt, tmp
        collect.N, collect.CAPTURE_REQUESTS = 1, True
        collect.BLOBS, collect.REQUESTS = [], []
        try:
            rc = await collect.main()
        finally:
            (collect.GeminiClient, collect.COOKIES, collect.PROMPT_PATH,
             collect.OUTDIR, collect.N, collect.CAPTURE_REQUESTS,
             collect.BLOBS, collect.REQUESTS) = saved

        assert rc == 0, f"main() returned {rc}"

        resp_path = os.path.join(tmp, "run01.bin")
        req_path = os.path.join(tmp, "run01.request.json")
        assert os.path.isfile(resp_path), "response capture not written by main()"
        assert os.path.isfile(req_path), "request sidecar not written by main()"

        body = open(resp_path, "rb").read()
        assert b"[[1,2,3]" in body, "response body not saved verbatim"
        assert not body.startswith(b"{"), "response file looks like a request"

        raw = open(req_path, encoding="utf-8").read()
        sidecar = json.loads(raw)
        assert len(sidecar) == 1, f"want 1 request, got {len(sidecar)}"
        assert sidecar[0]["data"]["f.req"] == FREQ, "sidecar lost the request body"
        assert SECRET not in raw and SECRET2 not in raw, "a credential reached disk"
        assert sidecar[0]["response_headers"]["content-length"] == "7", "framing context missing from the sidecar"

    print("main() wrote run01.bin + run01.request.json, cookies never hit disk")


async def run_checks():
    sess = StubSession()
    client = type("StubClient", (), {"_live_client": sess})()
    collect.tee(client)
    collect.BLOBS.clear()
    collect.REQUESTS.clear()

    resp = await sess.request(
        "POST",
        "https://generativelanguage.example/StreamGenerate",
        params={"rpcids": "abc"},
        headers={"Cookie": SECRET, "Content-Type": FORM_CT},
        data={"at": "TOKEN", "f.req": FREQ},
        stream=True,
    )
    async for _ in resp.aiter_content():
        pass

    assert len(collect.REQUESTS) == 1, f"want 1 captured request, got {len(collect.REQUESTS)}"
    cap = collect.REQUESTS[0]
    assert cap["method"] == "POST", cap["method"]
    assert cap["url"].endswith("/StreamGenerate"), cap["url"]
    assert cap["data"]["f.req"] == FREQ, "request body not captured verbatim"
    assert cap["data"]["at"] == collect.REDACTED, "access token not redacted"
    assert cap["headers"]["cookie"] == collect.REDACTED, "request cookie not redacted"
    assert cap["headers"]["content-type"] == FORM_CT, "non-credential request header was dropped"
    assert cap["response_headers"]["set-cookie"] == collect.REDACTED, "rotated cookie not redacted"
    assert cap["response_headers"]["content-type"] == "application/json+protobuf", "response context header was dropped"
    assert collect.SENSITIVE_FIELDS == {"at"}, "token field list changed - review it"
    blob = json.dumps(cap)
    assert SECRET not in blob and SECRET2 not in blob, "a credential reached the capture"

    assert len(collect.BLOBS) == 1, f"want 1 response blob, got {len(collect.BLOBS)}"
    assert b"[[1,2,3]" in collect.BLOBS[0], "response capture regressed"

    with tempfile.TemporaryDirectory() as tmp:
        path = collect.write_request_capture(os.path.join(tmp, "run01.request.json"), [cap])
        back = json.load(open(path, encoding="utf-8"))
        assert back[0]["data"]["f.req"] == FREQ, "sidecar did not round-trip"

        # The point of the capture: retry invariants must be readable offline.
        inner = json.loads(back[0]["data"]["f.req"])[0][1]
        assert "c_abc123" in inner and "rc_first" in inner, inner
        assert "1001" in inner, f"action code not readable from the capture: {inner}"

    print("request captured verbatim, cookies absent, sidecar round-trips")
    await run_main_end_to_end()
    print("ASSERTIONS PASS")


if __name__ == "__main__":
    asyncio.run(run_checks())

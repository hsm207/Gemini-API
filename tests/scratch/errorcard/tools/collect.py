"""Make N requests and dump the ENTIRE raw request and response for each one.

Every attempt is saved, error or not. Classification happens offline by
comparing the decoded structures - not here.

Both sides are captured because a retry cannot be verified from one of them:
the response proves an answer came back, but the request is where the retry
invariants live (same conversation cid, carried rcid, "Try again" action code).

Headers are captured too - they are what contextualises the body (content-type
says which endpoint answered, content-length/content-encoding explain a saved
body that does not match the advertised size). Credential-bearing values are
replaced with <REDACTED> rather than hashed: the corpus is committed, and no
diagnostic we need survives losing them. Header names are kept, so you can
still see that a cookie was sent or that the server rotated one.

Run inside gemini-proxy:
    BATCH=batch_05 N=10 python collect.py

Environment:
    BATCH             batch dir under /app/runs  (default: reads /app/prompt.md)
    N                 how many sends              (default 20)
    OUTDIR            where bodies are written    (default /app/runs/<batch>)
    CAPTURE_REQUESTS  0 to skip the request sidecars (default 1)
"""
import asyncio, json, os, sys
from gemini_webapi import GeminiClient

COOKIES = os.getenv("GEMINI_COOKIES_PATH", "/data/cookies/gemini_cookies.json")
# BATCH names the batch being collected, e.g. BATCH=batch_03. The prompt is
# read from that batch's own prompt.md so every batch is reproducible from its
# directory alone, with no dependency on a shared prompt file.
BATCH = os.getenv("BATCH", "")
PROMPT_PATH = os.getenv("PROMPT_PATH") or (
    f"/app/runs/{BATCH}/prompt.md" if BATCH else "/app/prompt.md"
)
N = int(os.getenv("N", "20"))
OUTDIR = os.getenv("OUTDIR") or (
    f"/app/runs/{BATCH}" if BATCH else "/app/runs"
)
CAPTURE_REQUESTS = os.getenv("CAPTURE_REQUESTS", "1") != "0"

# Header and form-field names whose values are credentials. The corpus is
# committed, so the value is dropped outright - a hash would only confirm a
# guess and its safety would depend on entropy we do not control.
SENSITIVE_HEADERS = {
    "cookie", "set-cookie", "authorization", "proxy-authorization",
    "x-goog-api-key", "x-api-key",
}
SENSITIVE_FIELDS = {"at"}  # per-request NlM0e access token
REDACTED = "<REDACTED>"

BLOBS = []
REQUESTS = []


def redact_headers(headers):
    """Every header name, credential values dropped."""
    return {
        str(k).lower(): (REDACTED if str(k).lower() in SENSITIVE_HEADERS else v)
        for k, v in dict(headers or {}).items()
    }


def redact_body(body):
    """Drop credential form fields. Returns a copy - the live request is untouched."""
    if not isinstance(body, dict):
        return body
    return {k: (REDACTED if k in SENSITIVE_FIELDS else v) for k, v in body.items()}


def tee(client):
    """Tap the session: record every request body and every response body."""
    sess = client._live_client
    orig = sess.request

    async def request(*a, **kw):
        # Positional args are (method, url); the rest arrive as kwargs. Every
        # body kwarg the session accepts is recorded, so a call site that later
        # switches from data= to files=/content= cannot capture a silent null.
        body = {k: kw[k] for k in ("data", "content", "json", "files", "form")
                if k in kw}
        record = {
            "method": a[0] if len(a) > 0 else kw.get("method"),
            "url": a[1] if len(a) > 1 else kw.get("url"),
            "params": kw.get("params"),
            "headers": redact_headers(kw.get("headers")),
            **body,
        }
        if "data" in record:
            record["data"] = redact_body(record["data"])
        # Appended before the await so a request that fails is still recorded.
        REQUESTS.append(record)
        resp = await orig(*a, **kw)
        record["response_headers"] = redact_headers(getattr(resp, "headers", None))
        it = resp.aiter_content

        async def aiter(*aa, **kk):
            buf = bytearray()
            async for chunk in it(*aa, **kk):
                buf.extend(chunk)
                yield chunk
            BLOBS.append(bytes(buf))

        resp.aiter_content = aiter
        return resp

    sess.request = request


def write_request_capture(path, requests):
    """Persist the raw request(s) of one send, exactly as they went out."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=2, default=str)
    return path


async def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    d = json.load(open(COOKIES, encoding="utf-8"))
    if not os.path.exists(PROMPT_PATH):
        print(f"NO PROMPT at {PROMPT_PATH}")
        return 3
    prompt = open(PROMPT_PATH, encoding="utf-8").read()

    c = GeminiClient(
        secure_1psid=d["__Secure-1PSID"], secure_1psidts=d["__Secure-1PSIDTS"],
        auto_refresh=True, refresh_interval=300,
    )
    await c.init()
    print(f"[init] account_status={c.account_status}", flush=True)
    if str(c.account_status) != "1000":
        print("NOT AUTHENTICATED")
        return 2

    tee(c)

    for i in range(1, N + 1):
        n0, r0 = len(BLOBS), len(REQUESTS)
        async for _ in c._generate(prompt=prompt, temporary=False):
            pass
        body = b"".join(BLOBS[n0:]) if len(BLOBS) > n0 else b""
        with open(os.path.join(OUTDIR, f"run{i:02d}.bin"), "wb") as f:
            f.write(body)
        note = ""
        if CAPTURE_REQUESTS:
            reqs = REQUESTS[r0:] if len(REQUESTS) > r0 else []
            path = write_request_capture(
                os.path.join(OUTDIR, f"run{i:02d}.request.json"), reqs
            )
            note = f", {len(reqs)} request(s) -> {os.path.basename(path)}"
        print(f"  run {i}: {len(body)} bytes{note}", flush=True)
        await asyncio.sleep(1.0)

    await c.close()
    print(f"\nsaved {N} responses to {OUTDIR}"
          f"{' with request sidecars' if CAPTURE_REQUESTS else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

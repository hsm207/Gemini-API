"""Make N requests and dump the ENTIRE raw response body for each one.

Every attempt is saved, error or not. Classification happens offline by
comparing the decoded structures - not here.

Run inside gemini-proxy:
    python tests/scratch/dump20.py
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

BLOBS = []


def tee(client):
    sess = client._live_client
    orig = sess.request

    async def request(*a, **kw):
        resp = await orig(*a, **kw)
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
        n0 = len(BLOBS)
        async for _ in c._generate(prompt=prompt, temporary=False):
            pass
        body = b"".join(BLOBS[n0:]) if len(BLOBS) > n0 else b""
        with open(os.path.join(OUTDIR, f"run{i:02d}.bin"), "wb") as f:
            f.write(body)
        print(f"  run {i}: {len(body)} bytes", flush=True)
        await asyncio.sleep(1.0)

    await c.close()
    print(f"\nsaved {N} responses to {OUTDIR}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

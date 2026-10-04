import asyncio
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from gemini_webapi import GeminiClient

async def test_timing_and_images():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=None)

    # 1. Measure Init time
    t0 = time.perf_counter()
    await client.init(timeout=30, auto_refresh=False)
    t_init = time.perf_counter() - t0
    print(f"\n[INIT BENCHMARK] Client handshake took: {t_init:.2f} seconds")

    # Inspect raw quotas dict
    print("\n--- Raw Quota Breakdown ---")
    for q_id, q_data in client.quotas.items():
        print(f"  * Quota ID [{q_id}]: {q_data}")

    # 2. Measure Single-turn text latency
    t0 = time.perf_counter()
    resp_text = await client.generate_content("Reply with 'pong' only.")
    t_text = time.perf_counter() - t0
    print(f"\n[TEXT BENCHMARK] Text round-trip took: {t_text:.2f} seconds")
    print(f"  Response: {resp_text.text.strip()}")

    # 3. Test Image Generation
    print("\n[IMAGE GENERATION TEST] Asking Gemini to generate an image...")
    t0 = time.perf_counter()
    prompt = """
    objective: ad for a luxurious intimate wear
image of a beaufitul young woman, german, long hair, porcelain white skin, ethereal beauty, black garter, thong, thigh highs, bralette wiht underwire, clear night sky, moonlight, glass floor to ceiling window, outdoors, balcony, 9:16
    
    """
    resp_img = await client.generate_content(prompt)
    t_img = time.perf_counter() - t0
    print(f"[IMAGE BENCHMARK] Generation round-trip took: {t_img:.2f} seconds")
    print(f"  Text description: {resp_img.text[:150] if resp_img.text else '(no text)'}...")
    print(f"  Images returned: {len(resp_img.images)}")

    out_dir = os.path.join(os.path.dirname(__file__), "output_images")
    os.makedirs(out_dir, exist_ok=True)

    for i, img in enumerate(resp_img.images):
        print(f"    Image {i+1}: type={type(img).__name__}, title='{getattr(img, 'title', '')}', url={str(getattr(img, 'url', ''))[:60]}...")
        save_file = os.path.join(out_dir, f"test_robot_{i}.png")
        try:
            await img.save(path=out_dir, filename=f"test_robot_{i}.png")
            print(f"    Saved successfully to: {save_file}")
        except Exception as e:
            print(f"    Save error: {e}")

if __name__ == "__main__":
    asyncio.run(test_timing_and_images())


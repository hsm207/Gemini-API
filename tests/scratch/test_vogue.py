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


async def generate_vogue_editorial():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=None)
    await client.init(timeout=30, auto_refresh=False)

    # High-fashion editorial prompt designed for Vogue / Harper's Bazaar aesthetic
    prompt = """
    Generate a high-fashion editorial photograph suitable for Vogue Magazine cover spread.
    Subject: A captivating German haute couture fashion model with striking high cheekbones, delicate jawline, porcelain radiant skin, effortless textured honey-blonde hair gently windswept.
    Attire: Bespoke luxury French couture intimate wear — intricate Chantilly lace noir bralette with architectural underwire, matching delicate floral lace garter belt, sheer silk gossamer thigh-high stockings, draped effortlessly with a flowing fluid satin robe slipping off one shoulder.
    Lighting & Mood: Cinematic high-contrast editorial lighting. Dramatic chiaroscuro with soft diffused silver moonlight rim lighting highlighting her silhouette, accompanied by subtle warm tungsten key light from a chic penthouse interior creating rich three-dimensional volume and velvety shadow depth.
    Environment: Penthouse glass terrace overlooking a blurred Parisian or Milanese midnight skyline with glimmering bokeh city lights under a deep sapphire starry night sky.
    Photography Style: 35mm fashion editorial photography by Peter Lindbergh and Helmut Newton, shot on Hasselblad H6D-100c with 85mm f/1.4 lens, shallow depth of field, natural film grain texture, tactile fabric details, exquisite couture realism, elegant, powerful, artistic, 9:16 vertical aspect ratio.
    """

    print("[VOGUE EDITORIAL TEST] Sending upgraded high-fashion prompt to Gemini...")
    t0 = time.perf_counter()
    resp = await client.generate_content(prompt)
    t_gen = time.perf_counter() - t0
    print(f"Generation took: {t_gen:.2f} seconds")
    print(f"Images returned: {len(resp.images)}")

    out_dir = os.path.join(os.path.dirname(__file__), "output_images")
    os.makedirs(out_dir, exist_ok=True)

    for i, img in enumerate(resp.images):
        save_file = os.path.join(out_dir, f"vogue_editorial_{i}.png")
        await img.save(path=out_dir, filename=f"vogue_editorial_{i}.png")
        print(f"Saved: {save_file}")


if __name__ == "__main__":
    asyncio.run(generate_vogue_editorial())

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

async def generate_vulnerable_devilish_vision():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=None)
    await client.init(timeout=30, auto_refresh=False)

    # Specific camera angle (high-angle looking down) + exact psychological subtext
    prompt = """
    A cinematographic, high-fashion narrative photograph with intense psychological micro-expression and vulnerable perspective.
    Camera Angle & Framing: High-angle camera looking slightly down at her from an elevated perspective (top-down view). This makes her look delicate, petite, and physically vulnerable as she tilts her chin slightly down and casts her eyes upward into the lens.
    Subject & Face: The exact same striking German model with delicate porcelain skin, gentle rosy blushing cheeks (innocent blushing bride aesthetic), long messy honey-blonde hair falling across her shoulders.
    The Micro-Expression Juxtaposition:
    - Upper face / Eyes: Wide, luminous, innocent doe eyes looking up with faux hesitation, wide and glistening, shyly telegraphing: 'Oh... I don't know if you should be here... someone might hear us...'
    - Lower face / Mouth: In sharp contrast to her innocent eyes, her lips curl into an unmistakable, subtle, devilishly playful cat-like smirk, whispering the unspoken dare: '...come in if you dare.' A tantalizing, provocative secret smile.
    Setting & Atmosphere: Standing at the threshold between her candlelit private bedchamber (hundreds of warm flickering candles creating a romantic amber sanctuary) and the stone balcony outside (cold midnight air, silver moonlight, crescent moon in the dark starry sky).
    Pose: Coyly leaning against the gothic stone doorframe, chin slightly lowered, one delicate hand shyly holding the edge of the stone archway, body gracefully turned in her couture black lace intimate wear and draped velvet robe.
    Lighting: Dual-temperature lighting — soft candlelit amber warmth illuminating her blush and the right side of her figure, balanced by cold silver moonlight sculpting the left side. 35mm film grain, 85mm portrait lens, shallow depth of field, 9:16 vertical aspect ratio.
    """

    print("[VISION TEST] Generating high-angle vulnerable gaze with devilish dare smirk...")
    t0 = time.perf_counter()
    resp = await client.generate_content(prompt)
    t_gen = time.perf_counter() - t0
    print(f"Generation took: {t_gen:.2f} seconds")
    print(f"Images returned: {len(resp.images)}")

    out_dir = os.path.join(os.path.dirname(__file__), "output_images")
    os.makedirs(out_dir, exist_ok=True)

    for i, img in enumerate(resp.images):
        save_file = os.path.join(out_dir, f"blushing_dare_{i}.png")
        await img.save(path=out_dir, filename=f"blushing_dare_{i}.png")
        print(f"Saved: {save_file}")

if __name__ == "__main__":
    asyncio.run(generate_vulnerable_devilish_vision())

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

async def generate_mischievous_contrast():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=None)
    await client.init(timeout=30, auto_refresh=False)

    # Sharp comedic & aesthetic juxtaposition: Gloomy Gothic melancholy backdrop VS playful, cheeky wink & tongue expression
    prompt = """
    A high-concept fashion editorial photograph featuring a brilliant juxtaposition of gothic gloom versus playful mischief.
    Subject: The exact same striking German haute couture model from the previous photo — high cheekbones, pale porcelain skin, long honey-blonde hair tousled playfully in the breeze.
    Expression & Contrast: Instead of being gloomy, she breaks the dark solemn mood with an adorable, cheeky, mischievous wink and playful tongue-out face (playful winking one eye, sticking the tip of her tongue out sideways with a cute impish smirk), directly engaging the camera with fun, irreverent charisma.
    Pose: Casually leaning on the weathered stone balustrade of the medieval castle balcony, confident hourglass curves, one hand resting on the stone while playfully tossing her hair with the other.
    Attire: Bespoke couture noir intimate lingerie — delicate midnight Chantilly lace underwire bralette, floral garter belt, sheer black silk stockings, with an unbuttoned velvet black cloak slipping off her shoulders.
    Setting: Deep gloomy gothic atmosphere — an isolated stone fortress tower high on a cliff, dark foggy pine wilderness below under a moonlit misty midnight sky with a glowing crescent moon, moody antique lantern on the masonry wall.
    Photography Style: 35mm candid fashion editorial, Hasselblad aesthetic, sharp focus on her playful facial expression, rich atmospheric film grain, cinematic contrast between the dark brooding background and her bubbly rebellious attitude, 9:16 vertical aspect ratio.
    """

    print("[MISCHIEF CONTRAST TEST] Generating cheeky gothic juxtaposition...")
    t0 = time.perf_counter()
    resp = await client.generate_content(prompt)
    t_gen = time.perf_counter() - t0
    print(f"Generation took: {t_gen:.2f} seconds")
    print(f"Images returned: {len(resp.images)}")

    out_dir = os.path.join(os.path.dirname(__file__), "output_images")
    os.makedirs(out_dir, exist_ok=True)

    for i, img in enumerate(resp.images):
        save_file = os.path.join(out_dir, f"mischief_contrast_{i}.png")
        await img.save(path=out_dir, filename=f"mischief_contrast_{i}.png")
        print(f"Saved: {save_file}")

if __name__ == "__main__":
    asyncio.run(generate_mischievous_contrast())

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

async def generate_two_brides():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts, proxy=None)
    await client.init(timeout=30, auto_refresh=False)

    # Multi-subject interaction: German bride + Chinese bride embracing in the doorway threshold
    prompt = """
    A masterclass high-fashion narrative editorial photograph with complex multi-subject interaction and romantic intimacy.
    Subjects & Interaction:
    Two stunning haute couture brides in an intimate, tender embrace at the threshold of the castle balcony doorway:
    1. First bride (German): The exact same captivating model with honey-blonde tousled hair, radiant porcelain skin with soft rosy blushing cheeks, delicate high cheekbones.
    2. Second bride (Chinese): An ethereal, stunning East Asian model with sleek glossy obsidian black hair elegantly pinned in a loose romantic updo with loose tendrils framing her face, flawless porcelain skin with a gentle petal-pink blush, elegant almond-shaped eyes, and refined high cheekbones.
    The Embrace & Connection: They stand closely intertwined in the gothic stone doorway. The German bride has one arm gently wrapped around the Chinese bride's waist, while the Chinese bride gently rests her cheek near her partner's shoulder, her slender fingers delicately resting on the German bride's collarbone. Their bodies lean naturally into each other in a sweet, protective, affectionate embrace.
    Expressions & Gaze: Both look up toward the camera with the same disarming psychological contrast — wide, vulnerable, innocent doe eyes blushing under the viewer's gaze, but both sharing conspiratorial, subtle, mischievous little smiles as if sharing an intimate secret.
    Attire: Harmonious bespoke haute couture bridal lingerie:
    - German bride wears midnight Chantilly lace with an open black velvet robe slipping off her shoulders.
    - Chinese bride wears ivory and pearl-toned delicate French silk and lace bralette with matching intricate silk garter and sheer stockings, draped with a fluid cream satin robe.
    Setting & Lighting: Standing right at the archway between the warm interior bedchamber (lit by dozens of flickering candles creating a deep golden glow) and the cold midnight castle balcony outside (misty air, silver crescent moon, deep star-studded sky). Dual-temperature lighting carving rich, soft highlights across both subjects. Hasselblad medium format portrait aesthetic, 85mm f/1.4 lens, 9:16 vertical aspect ratio.
    """

    print("[TWO BRIDES TEST] Generating multi-subject embrace with German & Chinese brides...")
    t0 = time.perf_counter()
    resp = await client.generate_content(prompt)
    t_gen = time.perf_counter() - t0
    print(f"Generation took: {t_gen:.2f} seconds")
    print(f"Images returned: {len(resp.images)}")

    out_dir = os.path.join(os.path.dirname(__file__), "output_images")
    os.makedirs(out_dir, exist_ok=True)

    for i, img in enumerate(resp.images):
        save_file = os.path.join(out_dir, f"two_brides_{i}.png")
        await img.save(path=out_dir, filename=f"two_brides_{i}.png")
        print(f"Saved: {save_file}")

if __name__ == "__main__":
    asyncio.run(generate_two_brides())

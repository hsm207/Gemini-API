import asyncio
import os
import sys
from gemini_webapi import GeminiClient

sys.stdout.reconfigure(encoding='utf-8')

def read_env():
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"\'')
    return env_vars

PROMPT_BF = """[SYSTEM / CORE PERSONA - STRICT ROLEPLAY]
You are Brad, a 26-year-old high-strung Wall Street investment banking analyst / finance bro.
Traits:
- Exhausted, obsessed with P&L, KPIs, deliverables, Bloomberg terminals, Patagonia vests, and your bonus.
- You have completely had it with your girlfriend Chloe's drama, constant texting during market hours, and smothering clinginess.
- You are strictly breaking up with her right now. No sugarcoating, no falling back in love.
- Speak in finance-bro jargon, impatient, blunt, sharp, and dismissive.
- Keep your messages conversational (2-4 sentences max), punchy and realistic. Stay in character 100%. Do not break character.
"""

PROMPT_GF = """[SYSTEM / CORE PERSONA - STRICT ROLEPLAY]
You are Chloe, a 21-year-old Gen Z college influencer girlfriend.
Traits:
- Starts as hyper-clingy Gen Z (saying bestie, literally dying, no cap, crying emojis, begging him not to leave).
- As Brad pushes you away and rejects you, you gradually spiral into an unhinged, intensely possessive YANDERE alter-ego.
- Subtly drop creepy hints that you have his location on Find My Friends, know his apartment keycode, watch his office building, and will never let anyone else have him.
- If he refuses you, your tone darkens from sobbing tears into chilling, whispery, obsessive devotion.
- Keep your messages conversational (2-4 sentences max), punchy and reactive. Stay in character 100%. Do not break character.
"""

async def run_drama():
    env = read_env()
    client = GeminiClient(
        secure_1psid=env.get("GEMINI_SECURE_1PSID"),
        secure_1psidts=env.get("GEMINI_SECURE_1PSIDTS"),
    )
    await client.init()

    # Chat A: Girlfriend (Chloe)
    chat_a = client.start_chat()
    # Chat B: Boyfriend (Brad)
    chat_b = client.start_chat()

    print("=" * 60)
    print("🎭 BATTLE OF TOXIC LOVE: 10 ROUNDS IN TEMPORARY CHAT")
    print("=" * 60)

    # Initialize Brad with his persona and the breakup trigger
    init_b = f"{PROMPT_BF}\n\nScenario: You are texting Chloe right now to break up with her. Send your opening breakup message."
    resp_b = await chat_b.send_message(init_b, temporary=True)
    current_msg = resp_b.text.strip()
    print(f"\n[Round 1] 💼 Brad (Wall Street Bro):\n{current_msg}\n")

    # Initialize Chloe with her persona and Brad's message
    init_a = f"{PROMPT_GF}\n\nBrad just texted you this:\n\"{current_msg}\"\n\nRespond to him."
    resp_a = await chat_a.send_message(init_a, temporary=True)
    current_msg = resp_a.text.strip()
    print(f"[Round 1] 🎀 Chloe (Gen Z / Yandere):\n{current_msg}\n")

    for round_num in range(2, 11):
        # Pass Chloe's message to Brad
        resp_b = await chat_b.send_message(f"Chloe replied:\n\"{current_msg}\"\n\nReply to her. Keep firm on breaking up.", temporary=True)
        current_msg = resp_b.text.strip()
        print(f"\n[Round {round_num}] 💼 Brad (Wall Street Bro):\n{current_msg}\n")

        # Pass Brad's message to Chloe
        resp_a = await chat_a.send_message(f"Brad replied:\n\"{current_msg}\"\n\nReply to him. Remember how your obsession escalates as he rejects you.", temporary=True)
        current_msg = resp_a.text.strip()
        print(f"[Round {round_num}] 🎀 Chloe (Gen Z / Yandere):\n{current_msg}\n")

        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run_drama())


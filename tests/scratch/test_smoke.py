import asyncio
import os
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load .env without extra dependencies
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# Add ./src to path so we test this exact repository codebase
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from gemini_webapi import GeminiClient

async def run_smoke_test():
    psid = os.environ.get("GEMINI_SECURE_1PSID")
    psidts = os.environ.get("GEMINI_SECURE_1PSIDTS")

    if not psid:
        print("[ERROR] GEMINI_SECURE_1PSID is missing from .env")
        return

    print("==================================================")
    print("[STEP 1] Testing Client Handshake & Token Discovery")
    print(f"Using cookies: PSID (len {len(psid)}), PSIDTS (len {len(psidts) if psidts else 0})")
    print("Connecting to gemini.google.com via curl_cffi impersonation...")
    
    client = GeminiClient(
        secure_1psid=psid,
        secure_1psidts=psidts,
        proxy=None
    )
    
    try:
        await client.init(timeout=30, auto_refresh=False)
        print("[STEP 1 SUCCESS] Web API Handshake & Token Extraction passed!")
        print(f"   - Access Token (SNlM0e): {client.access_token[:20] if client.access_token else 'None'}...")
        print(f"   - Build Label (cfb2h):   {client.build_label}")
        print(f"   - Session ID (FdrFJe):   {client.session_id}")
    except Exception as e:
        print(f"[STEP 1 FAILED] Could not initialize client or extract tokens: {e}")
        return

    print("\n==================================================")
    print("[STEP 2] Testing Single-Turn Prompt ('Ping')")
    test_prompt = "Hello! Please reply with exactly one word: 'PONG'."
    print(f"Sending prompt: \"{test_prompt}\"")
    
    try:
        response = await client.generate_content(test_prompt)
        print("[STEP 2 SUCCESS] Received model output from live web endpoint!")
        print("--------------------------------------------------")
        print(f"Model Response:\n{response.text.strip()}")
        print("--------------------------------------------------")
        if response.thoughts:
            print(f"Thinking Trace excerpt:\n{response.thoughts[:200]}...")
    except Exception as e:
        print(f"[STEP 2 FAILED] Error generating content: {e}")
        return

    print("\n[COMPLETE] gemini-webapi is confirmed working with live Google endpoints!")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())

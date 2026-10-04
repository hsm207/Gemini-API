
import asyncio
import os
import sys
import uuid
import json
from gemini_webapi import GeminiClient
from gemini_webapi.constants import Endpoint, Headers, MODEL_HEADER_KEY

sys.stdout.reconfigure(encoding='utf-8')

def read_env():
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

async def test_step722_again():
    env = read_env()
    client = GeminiClient(
        secure_1psid=env.get("GEMINI_SECURE_1PSID"),
        secure_1psidts=env.get("GEMINI_SECURE_1PSIDTS"),
    )
    await client.init()

    message_content = [
        "Remember this secret codeword: 'NEBULA_BLUE_42'. Acknowledge concisely.",
        0,
        None,
        None,
        None,
        None,
        0,
    ]
    inner_req_list = [None] * 99
    inner_req_list[0] = message_content
    inner_req_list[1] = ["en"]
    inner_req_list[6] = [1]
    inner_req_list[7] = 1
    inner_req_list[10] = 1
    inner_req_list[11] = 0
    inner_req_list[17] = [[0]]
    inner_req_list[18] = 0
    inner_req_list[27] = 1
    inner_req_list[30] = [4, 16]
    inner_req_list[41] = [1]
    inner_req_list[45] = 1
    inner_req_list[49] = 0
    inner_req_list[53] = 0
    uuid_val = str(uuid.uuid4()).upper()
    inner_req_list[59] = uuid_val
    inner_req_list[61] = []
    inner_req_list[68] = 2
    inner_req_list[79] = 1
    inner_req_list[80] = 1
    inner_req_list[91] = 0
    inner_req_list[96] = 0
    inner_req_list[98] = 1

    mh = [1, None, None, None, "56fdd199312815e2", None, None, 1, [4, 5, 6, 8, 16], None, None, 2, None, None, 1, 1, uuid_val, None, None]

    request_headers = {
        **client._live_client.headers,
        MODEL_HEADER_KEY: json.dumps(mh),
        "x-goog-ext-525005358-jspb": f'["{uuid_val}",1]',
        "x-goog-ext-73010989-jspb": "[0]",
        "x-goog-ext-73010990-jspb": "[0,0,0]",
        **Headers.SAME_DOMAIN.value,
    }

    request_data = {
        "at": client.access_token or "",
        "f.req": json.dumps([None, json.dumps(inner_req_list)]),
    }

    params = {"hl": client.language, "_reqid": client._reqid, "rt": "c"}
    if client.build_label:
        params["bl"] = client.build_label
    if client.session_id:
        params["f.sid"] = client.session_id

    async with client._live_client.stream(
        "POST",
        Endpoint.GENERATE,
        params=params,
        headers=request_headers,
        data=request_data,
    ) as response:
        content = await response.atext()
        lines = content.splitlines()
        for l in lines:
            if "NEBULA_BLUE_42" in l:
                try:
                    p = json.loads(l)
                    inner_str = p[0][2]
                    inner_obj = json.loads(inner_str)
                    cand_text = inner_obj[4][0][1][0]
                    print("EXACT STEP 722 OUTPUT:", repr(cand_text))
                except Exception as e:
                    pass

asyncio.run(test_step722_again())

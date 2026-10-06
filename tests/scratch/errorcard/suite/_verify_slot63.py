"""Confirm the action code reaches the wire, and that nothing else shifts.

Builds the request body the way _generate() does and asserts slot 63 is the only
difference between the bare and action-code forms.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))

from gemini_webapi.constants import ACTION_CODE_INDEX, TRY_AGAIN_ACTION_CODE


def build(action_code=None):
    inner = [None] * 81
    inner[0] = ["prompt", 0, None, None, None, None, 0]
    inner[1] = ["en"]
    inner[2] = ["", "", "", None, None, None, None, None, None, ""]
    inner[6] = [1]
    inner[7] = 1
    inner[10] = 1
    inner[11] = 0
    inner[17] = [[0]]
    inner[18] = 0
    inner[27] = 1
    inner[30] = [4]
    inner[41] = [1]
    inner[53] = 0
    inner[61] = []
    inner[68] = 1
    inner[79] = 1
    inner[80] = 1
    if action_code is not None:
        inner[ACTION_CODE_INDEX] = [action_code, None, 0]
    return inner


bare = build()
action = build(TRY_AGAIN_ACTION_CODE)

assert bare[ACTION_CODE_INDEX] is None, "bare form must leave slot 63 unset"
assert action[ACTION_CODE_INDEX] == [1001, None, 0], action[ACTION_CODE_INDEX]

diff = [i for i in range(81) if bare[i] != action[i]]
assert diff == [ACTION_CODE_INDEX], f"only slot 63 may differ, got {diff}"

# It must survive the real f.req encoding the client uses.
f_req = json.dumps([None, json.dumps(action)])
inner_rt = json.loads(json.loads(f_req)[1])
assert inner_rt[ACTION_CODE_INDEX] == [1001, None, 0], inner_rt[ACTION_CODE_INDEX]

print(f"ACTION_CODE_INDEX = {ACTION_CODE_INDEX}")
print(f"bare   slot 63 : {bare[ACTION_CODE_INDEX]!r}")
print(f"action slot 63 : {action[ACTION_CODE_INDEX]!r}")
print(f"slots differing: {diff}")
print("survives f.req round-trip: True")
print("ASSERTIONS PASS")

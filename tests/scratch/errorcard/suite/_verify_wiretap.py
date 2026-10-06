"""Unit-test the probe's WireTap against both real request-body shapes.

The tap is what makes the A/B trustworthy, so it needs its own check: it must
recognise a StreamGenerate body (including one that leaves slot 63 unset) and
reject the ancillary batchexecute bodies that share the f.req key.

Run:  python _verify_wiretap.py
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "probe_action_code", os.path.join(HERE, "..", "tools", "probe_action_code.py")
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
WireTap = probe.WireTap

sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))
from gemini_webapi.constants import ACTION_CODE_INDEX, TRY_AGAIN_ACTION_CODE  # noqa: E402


def generation_body(inner):
    """The dict the client hands curl_cffi as request data."""
    return {"at": "token", "f.req": json.dumps([None, json.dumps(inner)])}


def bare_inner():
    inner = [None] * 81
    inner[0] = ["prompt", 0, None, None, None, None, 0]
    inner[7] = 1
    return inner


# Real ancillary body captured from _generate()'s usage-info call.
USAGE_INFO = {"f.req": json.dumps([["jSf9Qc", "[]", None, "generic"]])}

checks = []

# 1. generation with slot 63 unset -> recognised, value None
ok, val = WireTap.parse(generation_body(bare_inner()))
checks.append(("bare generation recognised", ok is True and val is None))

# 2. generation with the action code -> recognised, value [1001, None, 0]
inner = bare_inner()
inner[ACTION_CODE_INDEX] = [TRY_AGAIN_ACTION_CODE, None, 0]
ok, val = WireTap.parse(generation_body(inner))
checks.append(("action generation recognised", ok is True and val == [1001, None, 0]))

# 3. ancillary batchexecute body -> NOT a generation
ok, val = WireTap.parse(USAGE_INFO)
checks.append(("usage-info rejected", ok is False and val is None))

# 4. non-dict / missing key / malformed json -> rejected, never raises
checks.append(("None body rejected", WireTap.parse(None) == (False, None)))
checks.append(("empty dict rejected", WireTap.parse({}) == (False, None)))
checks.append(("bad json rejected", WireTap.parse({"f.req": "{not json"}) == (False, None)))

# 5. right outer shape, wrong inner length -> rejected
checks.append((
    "short inner rejected",
    WireTap.parse({"f.req": json.dumps([None, json.dumps([1, 2, 3])])}) == (False, None),
))

# 6. a generation body where slot 63 is falsy-but-present must not be confused
inner = bare_inner()
inner[ACTION_CODE_INDEX] = []
ok, val = WireTap.parse(generation_body(inner))
checks.append(("empty-list slot63 kept distinct from absent", ok is True and val == []))

failed = [name for name, passed in checks if not passed]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'}  {name}")
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
if failed:
    sys.exit(1)
print("ASSERTIONS PASS")

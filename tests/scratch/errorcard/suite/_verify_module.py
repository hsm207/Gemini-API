"""Verify src/gemini_webapi/error_card.py against the labelled corpus.

Runs the real module over the real payloads, not the scratch detector, so the
number reported here is what client.py will see.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))
from analyze import payloads, candidates
from gemini_webapi.error_card import error_summary, is_error_card, is_rejected

with open(os.path.join(HERE, "..", "corpus", "error_labels.json"), encoding="utf-8") as f:
    ERRORS = set(json.load(f)["errors"])

runs = sorted(glob.glob(os.path.join(HERE, "..", "corpus", "runs", "batch_*", "*.bin")))
tp = fp = tn = fn = 0
flag_only_tp = flag_only_fp = 0

for path in runs:
    key = "/".join(path.replace("\\", "/").split("/")[-2:])
    body = open(path, "rb").read().decode("utf-8", "replace")
    truth = key in ERRORS

    detected = False
    rejected = False
    for pl in payloads(body):
        texts = [c[1][0] if len(c) > 1 and isinstance(c[1], list) and c[1] else ""
                 for c in candidates(pl)]
        if is_rejected(pl):
            rejected = True
        for t in texts:
            if is_error_card(pl, t):
                detected = True

    if rejected:
        if truth:
            flag_only_tp += 1
        else:
            flag_only_fp += 1

    if truth and detected:
        tp += 1
    elif truth:
        fn += 1
        print(f"  MISSED {key}")
    elif detected:
        fp += 1
        print(f"  FALSE POSITIVE {key}")
    else:
        tn += 1

print(f"error_card module over {len(runs)} responses")
print(f"  TP={tp} FN={fn} FP={fp} TN={tn}   accuracy={(tp + tn)}/{len(runs)}")
print(f"  flag path alone: TP={flag_only_tp} FP={flag_only_fp}")
print()
for key in sorted(ERRORS):
    body = open(os.path.join(HERE, "..", "corpus", "runs", *key.split("/")), "rb").read().decode("utf-8", "replace")
    reason = None
    for pl in payloads(body):
        texts = [c[1][0] if len(c) > 1 and isinstance(c[1], list) and c[1] else ""
                 for c in candidates(pl)]
        reason = error_summary(pl, texts[-1] if texts else None) or reason
    print(f"  {key:<22} {reason}")
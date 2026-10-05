"""Scores anomaly_detector.py against hand-read ground truth in error_labels.json.

    python test_anomaly_detector.py

Exits 0 if the detector agrees with every label, 1 otherwise.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anomaly_detector import StreamAnomalyDetector

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "error_labels.json"), encoding="utf-8") as f:
    ERROR_LABELS = set(json.load(f)["errors"])

RUNS = sorted(
    glob.glob(os.path.join(HERE, "runs", "batch_*", "*.bin"))
)

detector = StreamAnomalyDetector()
wrong = []

for path in RUNS:
    key = "/".join(path.replace("\\", "/").split("/")[-2:])
    body = open(path, "rb").read().decode("utf-8", "replace")
    expected = key in ERROR_LABELS
    actual = detector.detect(body).has_error
    if expected != actual:
        wrong.append((key, expected, actual))

print(f"checked {len(RUNS)} responses against {len(ERROR_LABELS)} error labels")
for key, expected, actual in wrong:
    print(f"  WRONG {key}: labelled error={expected}, detector said {actual}")

if wrong:
    print(f"\nFAIL: {len(wrong)} disagreements")
    sys.exit(1)

print("PASS: detector agrees with every label")

"""Corpus reporting for the captured StreamGenerate responses.

Reports sizes, payload counts, text lengths, and which detection rules fired.

Classification is delegated entirely to anomaly_detector; this module holds no
opinion of its own. An earlier version classified by scanning for known message
substrings, but that list missed 3 of the 5 real errors in this corpus, so it
was removed rather than kept as a cross-check.

Offline only - no network, no library import.

    python analyze.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anomaly_detector import StreamAnomalyDetector

DETECTOR = StreamAnomalyDetector()


def frames(body):
    """Decode the length-prefixed anti-XSSI stream into chunk objects."""
    i = body.find(")]}'")
    if i == -1:
        return []
    i += 5
    while i < len(body) and body[i] in "\r\n":
        i += 1
    dec, out = json.JSONDecoder(), []
    while i < len(body):
        nl = body.find("\n", i)
        if nl == -1:
            break
        head = body[i:nl].strip()
        if not head.isdigit():
            i += 1
            continue
        n = int(head)
        try:
            obj, _ = dec.raw_decode(body[nl + 1:nl + 1 + n])
        except ValueError:
            i = nl + 1 + n
            continue
        out.append(obj)
        i = nl + 1 + n
    return out


def payloads(body):
    """Yield each decoded StreamGenerate payload (the wrb.fr inner array)."""
    for obj in frames(body):
        row = obj[0] if isinstance(obj, list) and obj and isinstance(obj[0], list) else obj
        if isinstance(row, list) and len(row) > 2 and isinstance(row[2], str):
            try:
                yield json.loads(row[2])
            except Exception:
                pass


def candidates(pl):
    """Pull candidate arrays out of payload slot 4 (rcid, text, indicator...)."""
    slot = pl[4] if isinstance(pl, list) and len(pl) > 4 else None
    if not isinstance(slot, list):
        return []
    out = []
    for c in slot:
        if isinstance(c, list) and c and isinstance(c[0], str) and c[0].startswith("rc_"):
            out.append(c)
    return out


def text_len(pl):
    best = 0
    for c in candidates(pl):
        t = c[1][0] if len(c) > 1 and isinstance(c[1], list) and c[1] else ""
        best = max(best, len(t or ""))
    return best


def _rule_name(result):
    """Short rule label, e.g. 'TextBlockFlag' from its diagnostic."""
    message = result.diagnostic_message or ""
    if "rejection flag" in message:
        return "TextBlockFlag"
    if "replaced, not extended" in message:
        return "PayloadCollapse"
    if "known error message" in message:
        return "ExplicitMessage"
    return type(result).__name__


def analyse(path):
    body = open(path, "rb").read().decode("utf-8", "replace")
    pls = list(payloads(body))
    lens = [text_len(p) for p in pls]
    nz = set()
    for p in pls:
        if isinstance(p, list):
            nz |= {j for j, v in enumerate(p) if v is not None}
    # shrinkage: text got shorter than something already seen in this run
    peak, shrink = 0, []
    for i, ln in enumerate(lens):
        if ln and ln < peak:
            shrink.append((i, peak, ln))
        peak = max(peak, ln)
    # Classification is delegated to anomaly_detector, the single source of
    # truth for "is this an error".
    verdict = DETECTOR.detect(body)
    return {"file": os.path.relpath(path, os.path.dirname(__file__)).replace("\\", "/"),
            "bytes": len(body),
            "is_error": verdict.has_error,
            "rules": [_rule_name(r) for r in DETECTOR.detect_all(body)],
            "n_payloads": len(pls), "slots": sorted(nz), "max_text": max(lens or [0]),
            "shrinks": shrink}


def run_files():
  """All captured responses, across every batch directory."""
  root = os.path.join(os.path.dirname(__file__), "runs")
  return sorted(glob.glob(os.path.join(root, "batch_*", "*.bin")))


def main():
    rows = [analyse(f) for f in run_files()]
    if not rows:
        print("no runs found")
        return

    print(f"{'file':<24}{'bytes':>9} {'error':<7}{'payl':>5}{'maxtext':>8}"
          f"{'shrinks':>8}  rules")
    for r in rows:
        print(f"{r['file']:<24}{r['bytes']:>9} {str(r['is_error']):<7}"
              f"{r['n_payloads']:>5}{r['max_text']:>8}{len(r['shrinks']):>8}"
              f"  {','.join(r['rules'])}")

    errs = [r for r in rows if r["is_error"]]
    oks = [r for r in rows if not r["is_error"]]
    print(f"\nERRORS {len(errs)}  CLEAN {len(oks)}")
    if errs:
        print(f"\nerror runs and the rules that caught them:")
        for r in errs:
            print(f"  {r['file']:<24} {','.join(r['rules'])}")

    if errs and oks:
        e = set().union(*[set(r["slots"]) for r in errs])
        c = set().union(*[set(r["slots"]) for r in oks])
        print(f"\nerror-only slots : {sorted(e - c)}")
        print(f"clean-only slots : {sorted(c - e)}")
        print(f"shared slots     : {len(e & c)} -> {sorted(e & c)}")

    print("\n=== shrinkage rule: 'text shrank after growing' ===")
    fp = [r["file"] for r in oks if r["shrinks"]]
    tp = [r["file"] for r in errs if r["shrinks"]]
    print(f"  fires on ERROR runs : {len(tp)}/{len(errs)} {tp}")
    print(f"  fires on CLEAN runs : {len(fp)}/{len(oks)} {fp}")
    for r in errs + oks:
        if r["shrinks"]:
            print(f"    {r['file']}: {r['shrinks'][:4]} (peak->len at frame idx)")


if __name__ == "__main__":
    main()

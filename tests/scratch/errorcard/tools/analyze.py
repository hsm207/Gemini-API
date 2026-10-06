"""Corpus reporting for the captured StreamGenerate responses.

Reports sizes, payload counts, text lengths, and which detection signals fired.

Classification is delegated entirely to gemini_webapi.error_card - the same
module client.py uses, so this report can never disagree with the library. This
module used to delegate to a scratch copy of the rules instead; that copy was a
second implementation of the same idea and has been deleted.

Offline only - no network. Imports the library from the repo's src/.

    python analyze.py
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "src"))
from gemini_webapi.error_card import (  # noqa: E402
    error_summary,
    is_error_card,
    is_rejected,
    matches_known_message,
)


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
    # Classification is delegated to gemini_webapi.error_card, the single
    # source of truth for "is this an error". The per-text loop mirrors
    # _verify_module.py so the report and the test can never disagree.
    signals, reasons, detected = set(), [], False
    for pl in pls:
        texts = [c[1][0] if len(c) > 1 and isinstance(c[1], list) and c[1] else ""
                 for c in candidates(pl)]
        if is_rejected(pl):
            signals.add("RejectionFlag")
        for text in texts:
            if matches_known_message(text):
                signals.add("KnownMessage")
            if is_error_card(pl, text):
                detected = True
        reason = error_summary(pl, texts[-1] if texts else None)
        if reason and reason not in reasons:
            reasons.append(reason)
    return {"file": os.path.relpath(path, os.path.join(HERE, "..")).replace("\\", "/"),
            "bytes": len(body),
            "is_error": detected,
            "signals": sorted(signals), "reasons": reasons,
            "n_payloads": len(pls), "slots": sorted(nz), "max_text": max(lens or [0]),
            "shrinks": shrink}


def run_files():
  """All captured responses, across every batch directory."""
  root = os.path.join(os.path.dirname(__file__), "..", "corpus", "runs")
  return sorted(glob.glob(os.path.join(root, "batch_*", "*.bin")))


def main():
    rows = [analyse(f) for f in run_files()]
    if not rows:
        print("no runs found")
        return

    print(f"{'file':<24}{'bytes':>9} {'error':<7}{'payl':>5}{'maxtext':>8}"
          f"{'shrinks':>8}  signals")
    for r in rows:
        print(f"{r['file']:<24}{r['bytes']:>9} {str(r['is_error']):<7}"
              f"{r['n_payloads']:>5}{r['max_text']:>8}{len(r['shrinks']):>8}"
              f"  {','.join(r['signals'])}")

    errs = [r for r in rows if r["is_error"]]
    oks = [r for r in rows if not r["is_error"]]
    print(f"\nERRORS {len(errs)}  CLEAN {len(oks)}")
    if errs:
        print("\nerror runs and the signal that caught each:")
        for r in errs:
            print(f"  {r['file']:<24} {','.join(r['signals'])}  "
                  f"{'; '.join(r['reasons'])}")

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

# Gemini error-card corpus

Evidence for detecting the failure mode where Gemini abandons a partially
generated answer and substitutes a canned apology, plus a detector that finds it
on the raw wire.

Everything here is offline analysis of captured responses. Nothing in this
directory imports `gemini_webapi` or touches the network.

## The failure mode

Gemini's HTTP response is a clean `200`. The headers say nothing is wrong. The
stream terminates normally. But mid-answer the server **discards the text it
generated** and replaces it with a short apology.

Four distinct wordings have been observed:

| Length | Message |
| --- | --- |
| 65 | "I encountered an error doing what you asked. Could you try again?" |
| 59 | "Sorry, something went wrong. Please try your request again." |
| 91 | "I'm having a hard time fulfilling your request. Can I help you with something else instead?" |
| 69 | "I seem to be encountering an error. Can I try something else for you?" |

None of them signal failure in the transport, and only one contains the word
"error" in a position a keyword heuristic would reliably catch. The list is a
catalogue of what has been seen, not a complete set.

## How the corpus was collected

`collect.py` runs inside the `gemini-proxy` container. It sends N identical
requests and tees every raw response body to disk before any parsing happens,
so nothing is lost to interpretation.

```
# from the container, per batch
python /app/collect.py     with BATCH=batch_04 N=10
```

`BATCH` makes the script read `runs/<batch>/prompt.md` and write to
`runs/<batch>/`, so each batch directory is reproducible on its own with no
shared prompt file. That was a deliberate fix: an earlier version hardcoded
`/app/prompt.md`, which made every batch irreproducible once the scratch-level
prompt was deleted.

Authentication: cookies go stale within minutes. A run that returns
`account_status=1016` needs a refresh followed immediately by the run, in the
same shell invocation:

```
python -c "import httpx; httpx.post('http://gemini-reauth:9000/refresh', timeout=200.0)"
BATCH=batch_04 N=10 nohup python /app/collect.py > /tmp/log 2>&1 &
```

## The corpus

40 responses across 4 batches, 4 prompts.

| Batch | Runs | Prompt | Errors |
| --- | --- | --- | --- |
| `batch_01` | 10 | SpaceX valuation analysis (213 B) | `run07` |
| `batch_02` | 10 | same prompt, later session | `run01` |
| `batch_03` | 10 | agent-session transcript, 53,907 B | `run01`, `run04`, `run05` |
| `batch_04` | 10 | agent-session transcript, 41,865 B | `run02`, `run03` |

Each batch directory holds its own `prompt.md` (with a SHA-256 recorded in its
`MANIFEST.md`), its `run01..N.bin` captures, and a manifest describing what was
found. Batches 01-03 were trimmed from 20 runs to 10, keeping every error and
preferring varied response shapes; the discarded runs are in
`runs_trimmed/`, which is not part of the corpus.

Batches 01 and 02 have poor shape diversity: that prompt only ever produces
long-form valuation prose. Batches 03 and 04 exercise short replies, JSON tool
calls, and permission requests, which is where the false-positive risk lives.

## Ground truth

`error_labels.json` is the oracle. Each of the 40 responses was labelled by
reading what the model actually said, and the 5 error wordings plus 3 near-miss
clean examples are recorded there with the reasoning.

It is deliberately not derived from any detection logic. An earlier version
computed "truth" using the same shrink and message-matching the detector uses,
which made the test agree with the detector by construction and unable to fail.

The near-misses matter as much as the errors:

- `batch_03/run03` — 65 chars, a legitimate permission request
- `batch_04/run06` — 294 chars, a `google:search` tool call
- `batch_03/run11` — 209 chars, an `ipython` tool call

Short is not the signal.

## Detection

`anomaly_detector.py` walks the length-prefixed anti-XSSI framing sequentially
and reads text from decoded JSON. Both details matter: frame boundaries cannot
be found by regex because digits appear inside payloads too, and the payload is
double-encoded so candidate text arrives escaped (`\"rc_...\"`).

Three rules, OR'd, in priority order:

**`TextBlockFlagRule`** — structural, and the one that generalises. A text block
is nested as `[[[[None, [None, 0, "<text>"]]]]]`; five slots later the server
sets a boolean when it rejects the generation:

```
[[[[None, [None, 0, "<text>"]]]]], None, None, None, None, True, ...
```

**`PayloadCollapseRule`** — structural. A healthy stream only appends, so text
that shrinks without being a prefix-extension means the answer was discarded.
Threshold-free on purpose: size thresholds only catch failures that happen to
be large.

**`ExplicitErrorMessageRule`** — literal, an exact-match list of known wordings.

The flag rule is a strict superset of the collapse rule. Across the corpus it
fires on 7 of 7 errors; collapse fires on 4 of 7. The 3 it misses are the ones
where the backend failed *before generating anything* — a single frame, with no
prior text to shrink from. That shape is why the flag rule exists.

The offset of 5 is empirical. It has only ever been observed at payload index
26, so the implementation anchors on the block and steps forward rather than
hardcoding index 31.

## Running it

```
python analyze.py                  # corpus report: sizes, rule attribution
python test_anomaly_detector.py    # scores the detector against the labels
```

The test loads `error_labels.json`, runs the detector over every capture, and
exits non-zero on any disagreement. Roughly 15 seconds over 40 responses.

## What this does not do

This is investigation tooling. It is **not** wired into `gemini_webapi`. The
library still detects these responses with
`CARD_CONTENT_RE` in `client.py`, which matches a URL pattern that does not
appear in any capture here.
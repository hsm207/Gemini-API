# Gemini error-card corpus

Evidence for detecting the failure mode where Gemini abandons a partially
generated answer and substitutes a canned apology, plus a detector that finds it
on the raw wire.

Offline work here is analysis of captured responses. The `_verify_*.py` scripts
import `gemini_webapi` but never touch the network; the `*_live.py` scripts
cost real credits and need fresh cookies.

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
requests and tees both the raw request and the raw response body to disk before
any parsing happens, so nothing is lost to interpretation. The request side is
what makes a retry verifiable offline: the cid/rcid/action-code invariants live
in `f.req`, while the error-card signal lives in the response. Headers are
captured on both sides, with credential values replaced by `<REDACTED>` -
`cookie`, `set-cookie`, `authorization`, `proxy-authorization`, the api-key
headers, and the `at` access-token form field. Every other header survives
verbatim, because that is what contextualises the body: `content-type` says
which endpoint answered, `content-length` and `content-encoding` explain a
saved file whose size does not match the advertised one. Header names are kept
even when the value is dropped, so you can still see that the server rotated a
cookie.

```
# from inside gemini-proxy, per batch
BATCH=batch_04 N=10 python /app/collect.py
```

`BATCH` makes the script read `runs/<batch>/prompt.md` and write to
`runs/<batch>/`, so each batch directory is reproducible on its own with no
shared prompt file. That was a deliberate fix: an earlier version hardcoded
`/app/prompt.md`, which made every batch irreproducible once the scratch-level
prompt was deleted.

| env | default | meaning |
| --- | --- | --- |
| `BATCH` | *(empty)* | batch directory; empty reads `/app/prompt.md`, writes `/app/runs` |
| `N` | `20` | how many sends |
| `OUTDIR` | `/app/runs/<batch>` | where the files land |
| `PROMPT_PATH` | `/app/runs/<batch>/prompt.md` | overrides the prompt location |
| `GEMINI_COOKIES_PATH` | `/data/cookies/gemini_cookies.json` | the reauth bind mount |
| `CAPTURE_REQUESTS` | `1` | `0` writes only the response body, no sidecar |

Each send writes two files:

```
runs/<batch>/runNN.bin             raw response body, unmodified anti-XSSI stream
runs/<batch>/runNN.request.json    one record per HTTP call: method, url, params,
                                   redacted request headers, the form body
                                   (`f.req` verbatim), redacted response headers
```

A request that fails is still recorded: its entry is appended before the
response is awaited, so a timeout or a 401 leaves the request side behind.

The sidecars are what make a retry testable offline. The corpus captures above
predate this, so a new batch (e.g. `batch_05`) is needed before anything can
assert cid/rcid/action-code continuity against real traffic.

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
`MANIFEST.md`), its `run01..N.bin` captures (plus, for collections made after
2026-10-06, a `run01..N.request.json` sidecar per send), and a manifest
describing what was found. Batches 01-03 were trimmed from 20 runs to 10, keeping every error and
preferring varied response shapes; the 30 discarded runs (former
`runs_trimmed/`, never part of the corpus) were deleted in the 2026-10-06
cleanup after the detector scored 0 false positives on all of them.

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

Detection lives in `gemini_webapi/error_card.py` (see "Where detection now
lives"). The scratch prototype that first found the structural rule has been
deleted - it was a second implementation of the same rules, and `analyze.py`
now classifies with the production module so the report cannot drift from the
library. This section records how the rule was found. The prototype walked the
length-prefixed anti-XSSI framing sequentially and read text from decoded JSON.
Both details matter: frame boundaries cannot be found by regex because digits
appear inside payloads too, and the payload is double-encoded so candidate text
arrives escaped (`\"rc_...\"`).

Three rules were tried, OR'd, in priority order (the first and third shipped as
`error_card.is_rejected` and `error_card.matches_known_message`):

**`TextBlockFlagRule`** — structural, and the one that generalises. A text block
is nested as `[[[[None, [None, 0, "<text>"]]]]]`; five slots later the server
sets a boolean when it rejects the generation:

```
[[[[None, [None, 0, "<text>"]]]]], None, None, None, None, True, ...
```

**`PayloadCollapseRule`** — structural, analysis-only, never shipped. A
healthy stream only appends, so text that shrinks without being a
prefix-extension means the answer was discarded. Threshold-free on purpose: size
thresholds only catch failures that happen to be large. `analyze.py` still
reports the raw shrinkage signal (4 of 7 errors, 0 of 33 clean) without the
rule.

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
python tools/analyze.py            # corpus report: sizes, rule attribution
```

`_verify_module.py` loads `error_labels.json`, runs the real
`gemini_webapi.error_card` module over every capture, and exits non-zero on any
disagreement.

## Where detection now lives

`gemini_webapi/error_card.py` implements the flag rule plus the known-wording
fallback, and `client.py` applies it to every candidate in `_generate()` (the
per-candidate `is_error_card` flag). `generate_content()` retries rejected
generations in-conversation: up to 3 retries with exponential backoff, each one
regenerating the failed turn via the server's "Try again" action code
(1001, wire-verified 2026-10-05). `_verify_module.py` re-scores the detector
against this corpus on every change.

`CARD_CONTENT_RE` in `client.py` is an older, separate signal (a URL pattern
that does not appear in any capture here) and is untouched by this work.

## Layout

```
README.md
suite/     regression + acceptance tests (offline except sanity_10x_live)
tools/     collection & analysis toolkit (collect, retry probe, WireTap, corpus report)
corpus/    runs/ (the 40 labelled captures) + error_labels.json
```

## Scripts

Offline - safe to run anywhere, no network, no cookies:

```
python tools/analyze.py                 # corpus report: sizes, signal attribution
python suite/_verify_module.py          # error_card.py vs the whole corpus (40/40)
python suite/_verify_slot63.py          # action code lands in slot 63, nothing else shifts
python suite/_verify_retry_loop.py      # retry/backoff/exhaustion paths, mocked _generate
python suite/_verify_retry_identity.py  # retry reuses caller's chat, preserves rcid
python suite/_verify_wiretap.py         # WireTap body classification, both real shapes
python suite/_verify_request_capture.py  # collect.py's tap: body kept, cookies dropped
```

Live - need fresh cookies (see "Authentication" above) and cost credits:

```
python suite/sanity_10x_live.py    # 10x batch_03 trigger; every error card must recover
```

In-container tools (run inside gemini-proxy; paths are container-side):

```
python tools/collect.py              # N sends, tees raw request + response bodies
python tools/probe_action_code.py    # A/B: bare re-send vs action-code retry
```
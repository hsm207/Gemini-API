# batch_04

- **Prompt:** `prompt.md` in this directory — the authoritative copy for this
  batch. Verify with `sha256sum prompt.md`.
- **Prompt SHA-256:** `e2e6af6946474965bb2a13a875b4acbe9c4077f4cd0bb47d1fd143b0bb18167e`
- **Collected:** 2026-10-05, via `collect.py` inside `gemini-proxy` (`BATCH=batch_04 N=10`)
- **Responses:** 10 raw bodies, 1,053,552 bytes total
- **Prompt differs from batches 01-03:** yes (41,865 bytes; batches 01/02 were
  213, batch_03 was 53,907)

## Error cards found: 2 of 10 (20%)

| Run | Frames | Message |
| --- | --- | --- |
| `run02.bin` | 1 | "I seem to be encountering an error. Can I try something else for you?" |
| `run03.bin` | 1 | "I encountered an error doing what you asked. Could you try again?" |

## Notes

- **Both errors arrived with NO prior answer** — a single frame, so there was no
  text to replace. `PayloadCollapseRule` correctly did not fire on either.
- `TextBlockFlagRule` caught **both**, structurally, with no wording knowledge.
  This is the second batch in a row where the blind-spot shape showed up, and
  the second time the flag rule was the only structural signal available.
- 8 of 10 responses are legitimate tool-call payloads (`ipython`, `google:search`).
  Several are short — `run06` is a 294-char search call — and none are errors.
- No new error wording discovered; both messages were already catalogued.

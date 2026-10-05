# batch_03

- **Prompt:** `prompt.md` in this directory — the authoritative copy for this
  batch. Verify with `sha256sum prompt.md`.
- **Prompt SHA-256:** `b6ab91e1e1a54e2f24010e3c26b5af65da104a82fb16d650c2940dd3938f6ccf`
- **Collected:** 2026-10-05, via `collect.py` inside `gemini-proxy` (`BATCH=batch_03`)
- **Responses:** 10 (trimmed from 20; the other 10 are in `runs_trimmed/batch_03`)

## Error cards found: 3

| Run | Shape | Message |
| --- | --- | --- |
| `run01.bin` | **no prior answer** (single frame) | "I'm having a hard time fulfilling your request. Can I help you with something else instead?" |
| `run04.bin` | answer discarded, 1751 -> 69 | "I seem to be encountering an error. Can I try something else for you?" |
| `run05.bin` | answer discarded, 1534 -> 59 | "Sorry, something went wrong. Please try your request again." |

## Notes

- Original filenames are preserved so `error_labels.json` stays valid.
- All three errors were retained; the 7 clean runs cover JSON tool calls
  (long and short), short prose, and long prose.
- `run01.bin` is the important shape: the backend failed before generating
  anything, so there is no text to shrink FROM and `PayloadCollapseRule`
  cannot fire. Only `TextBlockFlagRule` catches it structurally.
- `run03.bin` is the matching near-miss: a 65-char legitimate permission reply
  that must NOT be flagged.

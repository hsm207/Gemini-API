# batch_01

- **Prompt:** `prompt.md` in this directory — the authoritative copy for this
  batch. Verify with `sha256sum prompt.md`.
- **Prompt SHA-256:** `13b740199c23595e933eef14672f3d70062f8c6d63b24a85c79775e1a3eedd79`
- **Collected:** 2026-10-05, via `collect.py` inside `gemini-proxy`
- **Responses:** 10 (trimmed from 20; the other 10 are in `runs_trimmed/batch_01`)

## Error cards found: 1

| Run | Shape | Message |
| --- | --- | --- |
| `run07.bin` | answer discarded, 3022 -> 65 | "I encountered an error doing what you asked. Could you try again?" |

## Notes

- Original filenames are preserved so `error_labels.json` stays valid.
- This prompt produces long-form valuation prose, so shape diversity is
  inherently low: 1 error card, 1 markdown-table answer, 1 heading-led answer,
  and 7 prose answers. Every non-error response in the trimmed-away pool was
  also prose, so no variety was left on the table.

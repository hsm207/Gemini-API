# batch_02

- **Prompt:** `prompt.md` in this directory — the authoritative copy for this
  batch. Verify with `sha256sum prompt.md`.
- **Prompt SHA-256:** `13b740199c23595e933eef14672f3d70062f8c6d63b24a85c79775e1a3eedd79`
- **Collected:** 2026-10-05, via `collect.py` inside `gemini-proxy`
- **Responses:** 10 (trimmed from 20; the other 10 are in `runs_trimmed/batch_02`)

## Error cards found: 1

| Run | Shape | Message |
| --- | --- | --- |
| `run01.bin` | answer discarded, 3996 -> 91 | "I'm having a hard time fulfilling your request. Can I help you with something else instead?" |

## Notes

- Original filenames are preserved so `error_labels.json` stays valid.
- Same prompt as batch_01, so shape diversity is similarly limited: 1 error
  card, 1 heading-led answer, 8 prose answers. Every non-error response in the
  trimmed-away pool was also prose.
- Revealed the third error wording, now in `KNOWN_ERROR_MESSAGES`.

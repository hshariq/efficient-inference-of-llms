# Phase 6 phrasing coverage

Generated: 2026-07-26 (Aire gpu012 mine after LMSYS sample)

| Task | Mined | ShareGPT | LMSYS | MOSS | Gap? |
|------|------:|---------:|------:|-----:|------|
| summarize_3_bullets | 404 | 0 | 404 | 0 | no (LMSYS only) |
| extract_entities | 221 | 0 | 221 | 0 | no (LMSYS only) |
| lone_wolf | 11181 | 0 | 11181 | 0 | no (LMSYS only) |

## Source notes

- **LMSYS:** ~20k streamed first-user turns from `lmsys/lmsys-chat-1m` →
  `raw_datasets/lmsys/lmsys_sample.jsonl`.
- **ShareGPT:** download/parse failed (`str` turn shape); not used.
- **MOSS:** download hung; not used.
- **No invented paraphrases.** Multi-source (ShareGPT/MOSS) deferred — would require
  remine + rebuild workloads + re-eval.

## Coverage gaps

- Multi-source diversity (ShareGPT / MOSS) still open — methodology currently
  **LMSYS-only**. Acceptable for ablation progress if stated in dissertation methods.

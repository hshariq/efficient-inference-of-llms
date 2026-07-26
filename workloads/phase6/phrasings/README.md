# Mined phrasings

JSONL files written by `python -m src.eval.mine_phrasings --write`:

- `summarize_3_bullets.jsonl`
- `extract_entities.jsonl`
- `lone_wolf.jsonl`

Each line: `{"mine_id", "source", "instruction", "raw"}` with `source` in
`sharegpt` | `lmsys` | `moss`.

**Do not hand-author these files.** Place dataset dumps under
`../raw_datasets/` and mine. Coverage gaps go in `docs/PHASE6_DECISIONS_LOG.md`.

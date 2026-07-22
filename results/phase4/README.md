# Phase 4 ablation results

Tracked copies of tagging ablation runs (113 paraphrased prompts, no vLLM).

Ephemeral Aire scratch stays in `logs/` (gitignored). After a run, copy artefacts here and commit.

## Expected files

| File | Condition | Notes |
|------|-----------|--------|
| `ablation_rules_only.txt` | `rules_only` | Full tee log (INPUT/OUTPUT/METRICS) |
| `ablation_rules_only.jsonl` | `rules_only` | One JSON object per prompt |
| `ablation_rules_plus_features.txt` | `rules_plus_features` | Full tee log |
| `ablation_rules_plus_features.jsonl` | `rules_plus_features` | Per-prompt JSON |
| `ablation_embed_minilm.*` | `embed_minilm` | After MiniLM verify on Aire |
| `ablation_embed_qwen3.*` | `embed_qwen3` | After Qwen verify on Aire |

Headline numbers also live in `docs/PHASE4_DECISIONS_LOG.md`.

## Copy from Aire after a run

```bash
mkdir -p results/phase4
cp logs/ablation_rules_only.txt results/phase4/
# if you also wrote jsonl:
cp logs/ablation_rules_only.jsonl results/phase4/ 2>/dev/null || true
```

Prefer writing straight into this folder:

```bash
python -m src.proxy.ablation.run_tag_ablation \
  --conditions rules_only \
  --jsonl results/phase4/ablation_rules_only.jsonl \
  --write-log results/phase4/ablation_rules_only.txt \
  --quiet
```

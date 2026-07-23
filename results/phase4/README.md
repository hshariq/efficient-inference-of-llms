# Phase 4 results

Tracked experiment artefacts for Phase 4 (tagging ablation + APC smoke).
Narrative summary and decisions: **`docs/PHASE4_DECISIONS_LOG.md`**.

## Tagging ablation (n=113, no vLLM)

| File | Condition |
|------|-----------|
| `ablation_rules_only.txt` | rules only |
| `ablation_rules_plus_features.{txt,jsonl}` | + Part 2 features |
| `ablation_embed_minilm.{txt,jsonl}` | + MiniLM fallback |
| `ablation_embed_qwen3.{txt,jsonl}` | + Qwen3-Embedding-0.6B |

Headline: rules bypass ~20.4%; MiniLM ~10.6% @ ~95 MiB; Qwen ~0% @ ~2.2 GiB.
Default proxy embed stays **`off`**; MiniLM preferred if enabled.

## APC smoke (vLLM + proxy)

| File | Mode |
|------|------|
| `smoke_apc_rewrite_off.txt` | `OPTIMIZER_REWRITE_MODE=off` (after warmup) |
| `smoke_apc_rewrite_on.txt` | `OPTIMIZER_REWRITE_MODE=on` (after warmup) |

Also log cold rewrite-on ~44× TTFT A/B from earlier gpu012 run in the decisions log
(may predate these tee files).

```bash
# Stronger smoke (longer docs + warmup + usage/cached if vLLM reports them)
# 1) proxy with REWRITE=off → tee off file; 2) restart proxy REWRITE=on → tee on file
export OPTIMIZER_REWRITE_MODE=off   # must match proxy process
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --long --warmup \
  2>&1 | tee results/phase4/smoke_apc_long_off.txt

export OPTIMIZER_REWRITE_MODE=on
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --long --warmup \
  2>&1 | tee results/phase4/smoke_apc_long_on.txt
```

## Not stored here

- Token Saving Ratio / full eval → Phase 6  
- TTL → Phase 5  

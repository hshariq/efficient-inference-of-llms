# Phase 4 results

Tracked experiment artefacts for Phase 4 (tagging ablation + APC smoke + MiniLM live).
**Narrative / decisions (source of truth):** `docs/PHASE4_DECISIONS_LOG.md`  
**Status:** Phase 4 **CLOSED** (2026-07-23).

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
| `smoke_apc_rewrite_off.txt` / `_on.txt` | Short docs (warm) |
| `smoke_apc_long_off.txt` / `_on.txt` | **Primary control:** `--long --warmup` — off A/B ≈ 1.05× |

```bash
export OPTIMIZER_REWRITE_MODE=off   # must match proxy process
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --long --warmup \
  2>&1 | tee results/phase4/smoke_apc_long_off.txt
```

## Live MiniLM

| Check | Result |
|-------|--------|
| Hard summarize paraphrase | `canonical_prefix_embed`, `embed_used=True` |
| Out-of-catalogue email draft | `bypass` after embed miss (`embed_used=False`) |

Optional client tee: `smoke_minilm_hard_prompt.txt`.

## Not Phase 4

- Token Saving Ratio / full eval → **Phase 6**  
- TTL → **Phase 5**  

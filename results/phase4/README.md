# Phase 4 results

Narrative / decisions: **`docs/PHASE4_DECISIONS_LOG.md`**  
**Status:** implementation complete; **APC latency benefit not shown** at ~400-token smoke.
Gate before Phase 5: Qwen draft-email probe + optional `--rag-scale` smoke.

## Tagging ablation (n=113, no vLLM)

| File | Condition |
|------|-----------|
| `ablation_rules_only.txt` | rules only |
| `ablation_rules_plus_features.{txt,jsonl}` | + Part 2 features |
| `ablation_embed_minilm.{txt,jsonl}` | + MiniLM (~10.6% bypass) |
| `ablation_embed_qwen3.{txt,jsonl}` | + Qwen (~0% bypass — **sanity-check before citing**) |

Default embed stays **`off`**; MiniLM preferred if enabled.  
Qwen uses Instruct+Query wrap; MiniLM does not (not pure weight swap).

```bash
PYTHONPATH=. python -m src.proxy.ablation.probe_embed_bypass
```

## APC smoke (vLLM + proxy)

| File | Scale | Read |
|------|-------|------|
| `smoke_apc_long_{on,off}.txt` | ~400 tok | Plumbing OK; **on≈off TTFT** — perf unverified |
| `smoke_apc_ragscale_{on,off}.txt` | ~5k tok | Preferred check for a detectable gap |

```bash
export OPTIMIZER_REWRITE_MODE=off   # must match proxy
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --rag-scale --warmup \
  2>&1 | tee results/phase4/smoke_apc_ragscale_off.txt

export OPTIMIZER_REWRITE_MODE=on
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --rag-scale --warmup \
  2>&1 | tee results/phase4/smoke_apc_ragscale_on.txt
```

## Not Phase 4

- Token Saving Ratio / full eval → **Phase 6**  
- TTL → **Phase 5** (after gate)  

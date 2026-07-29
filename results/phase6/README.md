# Phase 6 results

Spec: **`PHASE6_EVAL.md`** · Decisions: **`docs/PHASE6_DECISIONS_LOG.md`**

**Dissertation numbers:** **`RESULTS.md`** (living citeable log — update after every Aire run).

**Status:** ablation @ c=1 partial (2026-07-26); burst 2k @ c=8 in progress on gpu020 (2026-07-29).

## Artefact index

| Path | Meaning |
|------|---------|
| `run_<system>.jsonl` | Per-request logs from `python -m src.eval.run` |
| `run_<system>.summary.json` | Aggregate TSR / TTFT / percentiles |
| `aggregate_table.{md,csv}` | Dissertation table from `src.eval.aggregate` |
| `charts/*.png` + `captions.txt` | Six charts (bar, grouped, line, box, stacked, scatter) |
| `quality_spotcheck.md` | Sampled vanilla vs optimizer outputs |

## Quick commands (GPU node)

```bash
# GATE before any TSR run (vLLM+APC up) — harness ENFORCES this:
PYTHONPATH=. python -m src.eval.probe_cached_tokens
# writes results/phase6/.cached_tokens_probe_ok.json
# without it, apc/optimizer/gptcache eval exits with HARD GATE error

# Tiny harness smoke (proxy or vLLM up)
PYTHONPATH=. python -m src.eval.run --system optimizer \
  --workload workloads/phase6/smoke_tiny.jsonl

# TSR counter sanity (no GPU)
PYTHONPATH=. python -m src.eval.verify_tsr
PYTHONPATH=. python -m pytest tests/test_tsr_counters.py -q

# Mine phrasings (needs raw datasets under workloads/phase6/raw_datasets/)
PYTHONPATH=. python -m src.eval.mine_phrasings --write
# always writes workloads/phase6/phrasings_coverage.md

# Build burst workloads
PYTHONPATH=. python -m src.eval.build_workload --scale ablation
PYTHONPATH=. python -m src.eval.build_workload --scale full

# Charts (after c=1 + burst + ablation runs exist)
PYTHONPATH=. python -m src.eval.charts \
  --summaries results/phase6/burst_vanilla.summary.json \
              results/phase6/burst_apc.summary.json \
              results/phase6/burst_gptcache.summary.json \
              results/phase6/burst_optimizer_hold.summary.json \
  --ttft-c1 results/phase6/c1_vanilla.summary.json \
            results/phase6/c1_apc.summary.json \
            results/phase6/c1_gptcache.summary.json \
            results/phase6/c1_optimizer_hold.summary.json \
  --ttft-burst results/phase6/burst_vanilla.summary.json \
               results/phase6/burst_apc.summary.json \
               results/phase6/burst_gptcache.summary.json \
               results/phase6/burst_optimizer_hold.summary.json \
  --ablation-summaries results/phase6/ablation_vanilla.summary.json \
                       results/phase6/ablation_apc.summary.json \
                       results/phase6/ablation_gptcache.summary.json \
                       results/phase6/ablation_optimizer.summary.json \
                       results/phase6/ablation_optimizer_hold.summary.json \
  --jsonl results/phase6/burst_vanilla.jsonl \
          results/phase6/burst_apc.jsonl \
          results/phase6/burst_gptcache.jsonl \
          results/phase6/burst_optimizer_hold.jsonl

PYTHONPATH=. python -m src.eval.aggregate --summaries results/phase6/*.summary.json
```
## Honesty

- Simulated Leeds Student Assistant corpus — not real student data.
- Primary metric TSR; TTFT is cost (client-side).
- Phase 5 max_batch@hold=50 re-check belongs in the burst run (6f).


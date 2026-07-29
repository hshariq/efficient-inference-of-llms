# Phase 6 — Results (dissertation source)

> **Canonical** citeable Phase 6 numbers. Spec: `PHASE6_EVAL.md`.  
> Narrative / caveats: `docs/PHASE6_DECISIONS_LOG.md`.  
> Snapshot pointer: `ABLATION_C1_2026-07-26.md` (do not duplicate tables there).

**Primary metric:** Token Saving Ratio (TSR). TTFT / latency are secondary (cost).  
**Corpus:** simulated Leeds Student Assistant — not real student data.  
**Model:** `meta-llama/Llama-3.1-8B-Instruct` · vLLM 0.11.0

---

## How to use this file

After each Aire run: paste the harness summary into chat → get a short screenshot blurb → this file is updated with the full row (cite / do-not-cite flagged).

**Cite only** rows marked **OK**. Reject if `cached_tokens_call1` is large (warm KV; typically ≥96). Soft crumb (single-digit / low teens after probe) is noted but prefer cold restart.

**Always prefer per-tier TSR** over whole-workload aggregate when claiming Optimizer vs APC (see § Ablation).

---

## Session: 2026-07-29 — gpu020 · job `6913635`

### Gate

| Check | Result |
|-------|--------|
| Probe | **PASS** — call1=`0`, call2=`64` |
| Marker | `results/phase6/.cached_tokens_probe_ok.json` |
| Flags | APC on · `prompt_tokens_details` on · FlashInfer sampler off |

### Smoke (not for dissertation tables)

| System | Workload | n | TSR | mean TTFT ms | p50 lat ms | call1 | File | Cite? |
|--------|----------|---|-----|--------------|------------|-------|------|-------|
| apc | `smoke_tiny.jsonl` | 7/7 | 0.507 | 60 | 1071 | 16 (warm from probe) | `smoke_apc_gpu020.jsonl` | **No** — plumbing only |

### Burst 2k @ concurrency=8 (`burst_full.jsonl`)

| System | n | TSR | mean TTFT ms | p50 / p90 / p99 lat ms | hit_rate | call1 | File | Cite? | Notes |
|--------|---|-----|--------------|------------------------|----------|-------|------|-------|-------|
| apc | 2000/2000 | **0.775** | 122 | 1555 / 2342 / 2762 | 1.0* | 16 | `burst_apc.jsonl` | **OK** (soft crumb) | 2.37M/3.06M prompt toks cached; mode_mismatch false; BoN spread p50≈0.9ms |
| gptcache | — | — | — | — | — | — | `burst_gptcache.jsonl` | pending | next |
| optimizer (hold off) | — | — | — | — | — | — | `burst_optimizer.jsonl` | pending | proxy :9000; restart vLLM for cold |
| optimizer_hold (hold=50) | — | — | — | — | — | — | `burst_optimizer_hold.jsonl` | pending | max_batch@50 re-check |
| vanilla (APC off) | — | — | — | — | — | — | `burst_vanilla.jsonl` | pending | needs vLLM restart without APC |

\* `hit_rate=1.0` means `cached_tokens > 0` on every request (often chat-template crumbs) — **not** “100% full-prompt cache hits.” Use **TSR** as the claim.

**APC burst reading:** Under 2k@c=8, APC saved ~77.5% of prompt tokens. Mean TTFT ~122ms; end-to-end p50 ~1.6s. Higher whole-workload TSR than c=1 APC (0.693). `call1=16` is a soft probe crumb (not the warm-KV 96 reject).

---

## Ablation @ c=1 — 2026-07-26 · gpu012 · job `6882827`

Workload: `burst_ablation.jsonl` (200 req = exact 40 / semantic 80 / best_of_n 30 / lone_wolf 50).

### Whole-workload (secondary — do not over-claim from this alone)

| System | TSR | mean TTFT ms | p50 lat ms | call1 | File | Cite? |
|--------|-----|--------------|------------|-------|------|-------|
| vanilla | 0.00 | 101 | 1443 | 0 | `c1_vanilla.jsonl` | **OK** |
| apc | 0.693 | 98 | 1444 | — | `c1_apc.jsonl` | **OK** |
| gptcache | 0.857 | 25 | 15 | — | `c1_gptcache.jsonl` | **OK** (answer cache) |
| optimizer hold-on embed-off | 0.700 | 146 | 1506 | 0 | `c1_optimizer_hold.jsonl` | **OK** |
| optimizer hold-off minilm | 0.700 | 126 | 1454 | 16 | `c1_optimizer_holdoff_minilm.jsonl` | **OK** |
| optimizer hold-on minilm | 0.700 | 165 | 1507 | 0 | `c1_optimizer_holdon_minilm.jsonl` | **OK** |

### Per-tier TSR (primary comparison)

Computed from JSONL `tier` + `prompt_tokens` / `cached_tokens` (2026-07-29 audit).

| System | exact | semantic | best_of_n | lone_wolf | aggregate |
|--------|------:|---------:|----------:|----------:|----------:|
| vanilla | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| apc | 0.974 | **0.461** | 0.964 | 0.379 | 0.693 |
| optimizer (all three citeable configs) | 0.976 | **0.475** | 0.963 | ~0.35 | 0.700 |
| gptcache | 0.975 | 0.759 | 1.000 | 0.000 | 0.857 |

**Optimizer − APC on semantic tier only: +0.014** (0.475 − 0.461).  
Not a large hidden win — aggregate ≈0.007 gap is **not** masking a massive semantic-only gap. APC still gets substantial TSR on semantic (~0.46) via shared prefixes / template crumbs / repeated doc bodies across paraphrases, not “near zero.”

Exact + BoN dominate both systems (~0.96–0.98). Lone-wolf stays low (crumbs only). GPTCache’s semantic TSR is answer-memoization, not KV reuse.

### Identical aggregate TSR 0.700 across three optimizer configs — resolved

**Benign, not harness contamination.**

| Config | rewrite / bypass | catalogue | MiniLM evidence |
|--------|------------------|-----------|-----------------|
| hold-on embed-off | 150 / 50 | 150 `summarize_3_bullets`, 50 `unknown` | no embed path |
| hold-off minilm | 151 / 49 | 150 summarize, 49 unknown, **1** `extract_entities` | MiniLM fired **1×** |
| hold-on minilm | 151 / 49 | same as hold-off minilm | MiniLM fired **1×** |

- Semantic tier: **80/80 rewrite** on all three — rules alone matched every catalogue semantic request; MiniLM never needed there.
- The single MiniLM hit is `lone-156` (lone_wolf → `extract_entities`, 124 prompt toks, 16 cached) — negligible for aggregate TSR.
- Hold on vs off does not change prefix tokens → identical TSR expected at c=1; hold only moves TTFT/wait.
- Cold `call1` was 0 or 16 (soft crumb), not 96. The **0.995 / call1=96** run remains do-not-cite (`c1_optimizer.summary.json` warm KV).

**Harness gap:** Phase 6 JSONL logs `rewrite` as header string (`rewrite`|`bypass`) only — not `embed_used`. Inference above is from `catalogue_task` diffs. Prefer logging `embed_used` in a later harness tweak.

### Do not cite

- Any run with **TSR ≈ 0.995** and `cached_tokens_call1: 96` (warm KV after prior APC runs).

### Still missing (c=1 matrix)

- Cold **hold-off + embed-off** optimizer cell (rules+full, no MiniLM).

### Reading (for write-up)

1. Vanilla TSR=0 vs APC/Optimizer ~0.69–0.70 with similar TTFT → token saving, not TTFT win.
2. Aggregate Optimizer≈APC is real; **per-tier confirms** only a small semantic lift (+1.4 pp), not a buried headline win.
3. MiniLM barely engages on this workload slice — rules suffice for catalogue semantic/exact/BoN.
4. Hold at c=1 does not raise TSR; real test is burst co-arrival (6f).
5. GPTCache highest TSR via answer memoization — different mechanism; quality in 6h.

---

## Quality / charts / aggregate

| Step | Status |
|------|--------|
| Per-tier breakdown (c=1) | **done** (table above); use `python -m src.eval.aggregate --jsonl ...` |
| 6h quality spot-check | pending |
| 6i six charts | pending (need burst artefacts) |
| 6j aggregate tables | pending |

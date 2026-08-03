# Phase 6 — Dissertation tables (6j)

> **Paste-ready** citeable tables for the evaluation chapter.  
> Source of truth for narrative/caveats: `RESULTS.md`.  
> Figures: `results/phase6/charts/01–06_*.png` + `captions.txt` (§10).  
> Generated: 2026-08-03. Cite only **OK** rows.

---

## Figure ↔ table crosswalk

| Figure | Supports tables | Narrative beat |
|--------|-----------------|----------------|
| **01** TSR by system | **T1**, T2 | Main mix: Optimizer ≈ APC; vanilla 0; GPTCache higher (answers) |
| **02** Hit rate vs TSR | **T1** (hit_rate caveat) | Hit rate is a weak primary metric |
| **03** TTFT c=1→burst | **T2**, T1 (latency) | Load scaling / hold tax; main optimizer omitted (no c=1 hold-off) |
| **04** Latency boxplot | **T1**, T2 | Tails; GPTCache bimodal latency |
| **05** Uniqueness by n | **T5**, T6 | Rewrite gap under no exact repeats |
| **06** TSR histograms | **T3** | Tier-composition bimodality at **burst** scale (complement §2.5; does **not** depict T4 / c=1) |

---

## T1 — Main comparison: burst 2k @ concurrency=8

Workload: `burst_full.jsonl` (2000 = 400 exact / 800 semantic / 300 BoN / 500 lone_wolf).  
Primary metric: **TSR** = Σ cached / Σ prompt.

| System | n_ok | TSR | mean TTFT (ms) | p50 lat (ms) | p90 | p99 | hit_rate | Cite |
|--------|-----:|----:|---------------:|-------------:|----:|----:|---------:|:----:|
| vanilla (APC off) | 2000 | **0.000** | 308 | 2410 | 2961 | 3425 | 0.0 | OK |
| apc | 2000 | **0.775** | 122 | 1555 | 2342 | 2762 | 1.0* | OK |
| optimizer (hold off, embed off) | 2000 | **0.780** | 126 | 1641 | 2272 | 2738 | 1.0* | OK |
| optimizer_hold (hold 50, embed off) | 2000 | 0.780 | 200 | 1698 | 2387 | 2821 | 1.0* | OK |
| gptcache (c=8) | 2000 | 0.862 | 111 | 110 | 1523 | 2866 | 0.656 | OK† |

\* APC/optimizer `hit_rate`: weak “any cache” signal — prefer TSR (Fig 02).  
† GPTCache = answer memoization, not KV prefix reuse.

**Figures:** 01, 02, 04. **Source:** `RESULTS.md` §2.1, §3.

---

## T2 — Optimizer ablation (burst): hold × MiniLM

TSR flat; latency changes.

| Hold | MiniLM | TSR | mean TTFT (ms) | p50 lat (ms) | n_ok | Role |
|------|--------|----:|---------------:|-------------:|-----:|------|
| off | off | **0.780** | 126 | 1641 | 2000/2000 | Main Optimizer row |
| on (50 ms) | off | 0.780 | **200** | 1698 | 2000/2000 | Hold tax |
| off | on | 0.780 | **608** | 1813 | 1999/2000 | MiniLM tax (1 err) |
| on | on | 0.780 | **639** | 1851 | 2000/2000 | Worst latency |

**Figures:** 01 (flat TSR), 03 (`optimizer_hold` line only), 04. Hold vs hold-off TTFT also in §2.1/§2.2 text (126 vs 200 ms).

---

## T3 — Per-tier TSR: burst 2k @ c=8

| System | exact | semantic | best_of_n | lone_wolf | aggregate |
|--------|------:|---------:|----------:|----------:|----------:|
| vanilla | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| apc | 0.997 | **0.592** | 0.993 | 0.417 | 0.775 |
| optimizer (hold off/on, embed-off) | 0.997 | **0.602** | 0.992 | 0.419 | 0.780 |
| gptcache c=8 | 0.980 | 0.767 | 1.000 | 0.007 | 0.862 |

**Optimizer − APC (semantic) = +0.011.** No buried headline win on the main mix.  
**Figures:** 06 (pooled shape), 01. **Detail:** `RESULTS.md` §2.6.

---

## T4 — Per-tier TSR: ablation @ c=1 (n=200)

| System | exact | semantic | best_of_n | lone_wolf | aggregate |
|--------|------:|---------:|----------:|----------:|----------:|
| vanilla | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| apc | 0.974 | **0.461** | 0.964 | 0.379 | 0.693 |
| optimizer | 0.976 | **0.475** | 0.963 | ~0.35 | 0.700 |
| gptcache | 0.975 | 0.759 | 1.000 | 0.000 | 0.857 |

**Optimizer − APC (semantic) = +0.014.** Semantic mean is bimodal / recycle-inflated — see §2.5 (not Fig 06).  
**Figures:** none (table-only). Fig 06 is burst-pooled only and must not be cited for this c=1 table.

---

## T5 — Uniqueness / no-exact-repeat probes (APC vs Optimizer)

Design: unique mined `summarize_3_bullets` instructions + one short shared doc; no exact prompt repeats; hold off, embed off; c=1.  
**Not** an attack on rewrite; favorable single-doc sensitivity setup.

| Probe | n | APC TSR | Optimizer TSR | Δ | APC 95% CI | Opt 95% CI |
|-------|--:|--------:|--------------:|--:|------------|------------|
| LMSYS-only (§9) | 83 | **0.108** | **0.315** | **+0.207** | [0.098, 0.119] | [0.309, 0.322] |
| ShareGPT+LMSYS (§9b) | 224 | **0.110** | **0.313** | **+0.203** | [0.104, 0.115] | [0.309, 0.316] |
| XL open-dump yield (§9c) | 556 | **0.127** | **0.305**† | **+0.178** | [0.124, 0.130] | [0.303, 0.308] |

All CIs **non-overlapping**. MOSS scanned; 0 English summarize rows in probe (yield, not silent drop).  
† XL Optimizer TSR from printed cold **hold-off embed-off** summary (see `RESULTS.md` §9c overwrite note); later ablations reused the same out path.  
**Figure:** 05. **Sources:** `RESULTS.md` §9–9c; `aggregate --probe-stats`.

---

## T6 — When does rewrite help? (Optimizer − APC on semantic)

| Setting | Optimizer − APC | Interpretation |
|---------|----------------:|----------------|
| Main mix semantic @ c=1 (§2.4) | **+0.014** | Weak / noise; recycles inflate APC |
| Main mix semantic @ burst (§2.6) | **+0.011** | Same story at scale |
| Uniqueness n=83 / 224 / 556 (§9–9c) | **+0.18–0.21** | Clear under no exact repeats |

**Figures:** 01 vs 05. Report **both** main matrix and uniqueness — do not replace T1 with T5.

---

## T7 — TTL dispositions @ hold=50 (burst Optimizer hold-on)

| Disposition | Count | Share | Meaning |
|-------------|------:|------:|---------|
| `hold_window` | 1477 | 73.9% | Waited hold, then admitted |
| `skip` | 515 | 25.8% | Hold skipped |
| `max_batch` | 8 | 0.4% | Early flush at max batch |

Hold is active; `max_batch` rare. **Does not raise TSR** (T2). Phase 5 behaviour evidence.

---

## T8 — Quality spot-check (informal)

| Check | Result |
|-------|--------|
| Sample | 12 stratified (3× each tier); vanilla vs optimizer hold-off embed-off |
| Catalogue | `rewrite` + correct task; on-task summaries/bullets both sides |
| Lone wolf | `bypass`; outputs ≈ vanilla |
| Metrics | **Not** BLEU/ROUGE — task-meaning spot-check only |

Artefact: `quality_spotcheck.md`. **Cannot claim** proven answer-quality superiority.

---

## Claims (copy for discussion / conclusion)

**Can say**

1. Vanilla TSR=0 vs APC/Optimizer ~0.78 → prefix caching yields large token savings (T1, Fig 01).
2. On the main four-tier mix, Optimizer rewrite-only ≈ APC on aggregate TSR (T1, T3).
3. Semantic Opt−APC only +0.01 on that mix; uniqueness probes show +0.18–0.21 with non-overlapping CIs (T5, T6, Fig 05).
4. Hold / MiniLM raise TTFT (or MiniLM latency), not TSR (T2).
5. GPTCache is answer memoization — different mechanism (T1).
6. Strongest broad result: **TSR vs TTFT decoupling** (vanilla vs APC); rewrite helps when paraphrases are unique and the shared suffix is the doc.

**Cannot say**

1. Optimizer massively beats APC on the main burst.
2. TTFT win for Optimizer vs APC.
3. `hit_rate=1.0` = full-prompt hits.
4. Uniqueness probe replaces the main matrix, or generalizes to multi-doc production Leeds RAG without further evidence.
5. Fig 06 “proves” the §2.5 recycle mechanism (tier composition is the coarse driver; §2.5 is semantic-only).

---

## Regeneration notes

Numbers above are **curated from locked runs** in `RESULTS.md`, not auto-regenerated (burst/uniqueness JSONLs may live only on Aire).

On Aire, optional refresh of machine tables:

```bash
PYTHONPATH=. python -m src.eval.aggregate --jsonl \
  results/phase6/burst_vanilla.jsonl \
  results/phase6/burst_apc.jsonl \
  results/phase6/burst_gptcache_c8.jsonl \
  results/phase6/burst_optimizer_holdoff_embedoff.jsonl \
  results/phase6/burst_optimizer_holdon_embedoff.jsonl

PYTHONPATH=. python -m src.eval.aggregate --probe-stats \
  results/phase6/adv_sem_apc.jsonl \
  results/phase6/adv_sem_optimizer.jsonl
# … multi + xl similarly
```

If a regenerated number disagrees with this file, **prefer `RESULTS.md` OK rows** and update both.

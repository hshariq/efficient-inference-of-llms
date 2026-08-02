# Phase 6 — Evaluation Harness

> **Goal:** Repeatable evaluation comparing Vanilla vLLM / APC / GPTCache / Optimizer Box
> under an identical simulated RAG workload. Primary metric: **Token Saving Ratio (TSR)**.
> Final phase before dissertation write-up.

Read first: `project-context.md`, `TODO.md`, `PHASE4_SEMANTIC.md`,
`docs/PHASE4_DECISIONS_LOG.md`, `PHASE5_TTL.md`, `docs/PHASE5_DECISIONS_LOG.md`,
`docs/PHASE6_DECISIONS_LOG.md`.

---

## Critical framing

Phase 4/5 showed **TTFT is not a reliable proxy** for benefit at current catalogue
design (shared prefix short vs unique RAG docs; TTFT on≈off≈1×). Primary metric is:

```text
TSR = tokens_saved / total_tokens_that_would_have_been_processed_without_the_system
```

TTFT, throughput, hit rate, VRAM, and quality are **secondary**. TSR↑ with TTFT flat
is an expected, correctly explained finding. Do **not** report TBT/TPOT as headline
results (prefill-scope system; decode deferred — `project-context.md` §4).

---

## Metrics (per system, per run)

| Kind | Metric | Notes |
|------|--------|-------|
| Primary | **TSR** | Proxy-side counters `total_tokens_processed` / `total_tokens_saved`; cross-check vLLM cached tokens |
| Secondary | Cache hit rate % | Context for TSR only (vanity alone) |
| Secondary | Throughput | Generated tokens/sec |
| Secondary | P50 / P90 / P99 latency | Burst; starvation/TTL claim |
| Secondary | TTFT (mean) | **Client-side** (includes hold); cost metric |
| Secondary | GPU VRAM | `nvidia-smi` / vLLM stats |
| Secondary | Quality spot-check | Sampled vs vanilla outputs |

---

## Four systems

1. **Vanilla vLLM** — no prefix caching
2. **vLLM + APC** — exact-match only; no rewrite
3. **GPTCache** — semantic **output** cache (speed vs flexibility comparator)
4. **Optimizer Box** — Phase 4 rewrite + Phase 5 hold in front of vLLM

Ablation (no Trimmer cell):
- (a) Semantic + canonical prefixes only (`OPTIMIZER_TTL_MODE=off`)
- (b) Semantic + TTL hold (`OPTIMIZER_TTL_MODE=on`)
- (c) Baselines for reference

---

## Workload — simulated "University of Leeds Student Assistant"

**Simulated scenario for evaluation only** — not real student data, not a deployed
Leeds system. State this in methodology.

- **Docs:** 8–12 long synthetic university-style documents (handbook / assessment /
  programme / policy style), 1,500–5,000 words each.
- **Tasks:** reuse catalogue (`summarize_3_bullets`, `extract_entities`); extend only
  via Phase 4 schema patterns.
- **Phrasing:** 100% mined from ShareGPT / LMSYS-Chat-1M / MOSS — no hand-authored
  fallback. Document coverage gaps in `docs/PHASE6_DECISIONS_LOG.md`.

### Four-tier burst (2,000 requests)

| Tier | Volume | Content | Tests |
|------|--------|---------|-------|
| 1 Exact duplicates | 400 | Identical prompt | Native APC baseline |
| 2 Semantic variations | 800 | Same task+doc family, mined phrasing | Core contribution |
| 3 Best-of-N simultaneous | 300 | N identical prefixes at once | Hold co-arrival |
| 4 Out-of-schema lone wolves | 500 | Non-catalogue unique queries | TTL / starvation |

Also: **concurrency=1** baseline; ablation at ~200 req with same tier mix.

---

## Charts (`results/phase6/charts/`)

Six charts, mixed types (not five identical bars):

| # | Chart | Type | Input |
|---|--------|------|-------|
| 1 | TSR by system | bar | `--summaries` |
| 2 | Hit rate vs TSR | grouped bar | `--summaries` |
| 3 | TTFT across load scenarios | **line** (c=1 → burst) | `--ttft-c1` + `--ttft-burst` |
| 4 | Latency distribution | **box plot** | `--jsonl` (burst) |
| 5 | Uniqueness probe TSR by n | **grouped bar** | `--uniqueness-summaries` |
| 6 | Per-request TSR distribution | **faceted histogram** | `--jsonl` |

**Dropped:** old SCALM-style stacked “semantic delta + TTL add-on” chart — mislabels APC savings as rewrite and implies hold raises TSR (false here). Story told by chart 1 + chart 5 + §2.6 instead.

**Also replaced:** crowded “TSR vs prompt tokens” scatter — hard to read; faceted TSR histograms show bimodality (crumbs vs near-full hits) more honestly.

matplotlib; one image + 1–2 sentence caption each (`captions.txt`).

---

## Build sequence

| Step | Deliverable |
|------|-------------|
| **6a** | Harness scaffold + JSONL logging |
| **6b** | TSR counters + controlled sanity test |
| **6c** | Four systems wired + smoke |
| **6d** | Corpus + mined phrasing + four-tier generator |
| **6e** | Concurrency=1, all systems |
| **6f** | Burst 2k + max_batch re-check at hold=50 |
| **6g** | Ablation (reduced scale) |
| **6h** | Quality spot-check |
| **6i** | Six charts + captions (mixed types) |
| **6j** | Aggregate tables for dissertation |

---

## Done checklist

- [x] 6a harness scaffold + structured logging (`src/eval/`)
- [x] 6b TSR counters + controlled-workload sanity test (`metrics_tsr`, `tests/test_tsr_counters.py`)
      + **hard gate** `probe_cached_tokens` → marker file; harness refuses apc/optimizer/gptcache without it
- [x] 6c all four systems wired (vanilla/APC/gptcache/optimizer[+hold]); smoke via harness + `PHASE6_SYSTEMS.md`
- [x] 6d workload corpus builders (docs + mine/build scripts + four-tier + Best-of-N); **mined phrasing files pending dataset download on Aire**
- [ ] 6e concurrency=1 run, all systems
- [ ] 6f burst run (2,000 req, four-tier), all systems; max_batch under real burst
- [ ] 6g ablation runs (four-tier, reduced scale)
- [ ] 6h quality spot-check
- [ ] 6i six required charts + captions (bar / grouped / line / box / stacked / scatter)
- [ ] 6j aggregate tables ready for dissertation

Scripts for 6h–6j exist (`quality_spotcheck`, `charts`, `aggregate`); they need run artefacts from 6e–6g.

---

## Honesty constraints

- No TTFT win claim unless data shows one.
- TSR↑ / TTFT flat → say so plainly.
- Log null/negative results.
- Simulated university-assistant corpus; not real student data.
- Phase 5 hold=500 max_batch PASS ≠ default hold=50; re-validate in 6f.

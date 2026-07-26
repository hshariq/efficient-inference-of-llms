# Phase 6 — Decisions & Progress Log

Evaluation harness. Spec: `PHASE6_EVAL.md`.

**Last updated:** 2026-07-26 — reviewer fixes: cached_tokens probe gate, doc quality,
chart ablation split, APC audit probe, BoN send-spread logging, coverage auto-write

---

## Status

| Layer | State |
|-------|--------|
| **Spec** | `PHASE6_EVAL.md` |
| **Harness** | `src/eval/` |
| **TSR counters** | `src/proxy/metrics_tsr.py` + `GET /metrics` |
| **cached_tokens gate** | `python -m src.eval.probe_cached_tokens` — **must PASS on Aire before scale runs** |
| **Workload** | Varied RAG docs via `regen_docs`; phrasing mine TBD |
| **Charts / tables** | scripts ready; chart 5 requires `--ablation-summaries` |
| **Aire full runs** | Pending (6e–6h) |
| **Phrasing mine** | See `workloads/phase6/phrasings_coverage.md` |

Scaffold complete locally. **Do not trust TSR until `probe_cached_tokens` passes** against
the same vLLM build used for eval (`vllm` pin + `--enable-prefix-caching`).

---

## Reviewer fixes (2026-07-26)

1. **cached_tokens field verification (HARD GATE)** — `probe_cached_tokens` on PASS
   writes `results/phase6/.cached_tokens_probe_ok.json`. Harness **refuses**
   `apc` / `optimizer` / `optimizer_hold` / `gptcache` runs without a fresh marker
   (`RuntimeError`, exit 2). Match key is **upstream vLLM URL fingerprint**
   (`localhost:8000`), not Slurm hostname — so probe on :8000 unlocks proxy :9000
   on the same node; re-probe after new allocations (12h max age + soft SLURM_JOB_ID note).
   `--skip-cached-tokens-gate` prints a loud UNVERIFIED banner and sets
   `cached_tokens_gate_skipped` / `cite_warning` in the summary.
   Mode mismatches likewise banner + `mode_mismatch` (exit 3).
2. **RAG doc quality** — removed repeated "Additional guidance note N" filler; docs
   regenerated with varied university-style prose (`src.eval.regen_docs`).
3. **Charts** — six mixed types (not five bars): TSR bar; hit vs TSR grouped;
   TTFT **line** across c=1→burst; latency **box plot**; ablation **stacked** bar;
   TSR vs prompt-tokens **scatter**. Chart 5 requires `--ablation-summaries`;
   charts 4/6 need `--jsonl`.
4. **Vanilla vs APC audit** — each run logs `server_capabilities` / `apc_probe` into
   `*.summary.json`; warns on mode mismatch.
5. **Best-of-N simultaneity** — logs `client_send_ts` and per-group `bon_group_spread_ms`
   (observed dispatch spread, not assumed).
6. **Coverage gaps** — `mine_phrasings` always writes `phrasings_coverage.md` + decisions-log pointer.

## Locked decisions

1. **Primary metric = TSR**; TTFT is client-side **cost** (includes admission hold).
2. No TBT/TPOT as headline results (prefill-scope).
3. Ablation: semantic-only vs semantic+TTL vs baselines — **no Trimmer cell**.
4. Catalogue tasks from Phase 4; no invented paraphrases (ShareGPT / LMSYS / MOSS only).
5. Simulated Leeds Student Assistant scenario — **not** real student data.
6. Proxy-side TSR counters are source of truth for Optimizer Box; harness logs
   per-request usage for all systems. Cross-check vLLM `cached_tokens` when present.
7. Phase 5 open item: **`max_batch` at default `hold_ms=50` re-validated under Phase 6
   burst load**, not the synthetic hold=500 smoke workaround.

---

## TSR accounting rule (6b)

On each non-stream `/v1/chat/completions` response from upstream:

- `total_tokens_processed += usage.prompt_tokens` (fallback 0 if missing).
- `total_tokens_saved += cached_tokens` where `cached_tokens` comes from
  `usage.prompt_tokens_details.cached_tokens` (vLLM) when present; else 0.
- **TSR** = `saved / processed` when `processed > 0`, else 0.

Harness-side: same formula from JSONL `prompt_tokens` / `cached_tokens` for
vanilla / APC / GPTCache (GPTCache hit → `cached_tokens = prompt_tokens`,
`hit=true`). Documented so examiner can recompute.

Controlled sanity: `tests/test_tsr_counters.py` + `python -m src.eval.verify_tsr`.

---

## Phrasing coverage (fill after mine)

| Catalogue task | Mined count | ShareGPT | LMSYS | MOSS | Gap notes |
|----------------|-------------|----------|-------|------|-----------|
| summarize_3_bullets | 0 | — | — | — | **Gap** — place dumps under `workloads/phase6/raw_datasets/`, run `mine_phrasings --write` |
| extract_entities | 0 | — | — | — | **Gap** — same |
| lone_wolf (tier 4) | 0 | — | — | — | **Gap** — same |

No hand-authored paraphrases. Semantic / lone-wolf tiers stay empty until mine succeeds.

---

## Phase 5 → 6 forward reference

max_batch at hold=50 failed in Phase 5 smoke (client dispatch latency); passed at
hold=500. That was a **smoke methodology** limitation. Phase 6 burst (2k, real
arrival) re-checks whether `OPTIMIZER_TTL_BATCH_PEERS=8` fires at default hold=50.

---

## Run log (Aire)

| Date | Step | Node | Notes |
|------|------|------|-------|
| — | 6e–6h | — | Pending |

<!-- phrasings-coverage-auto -->
### Phrasing coverage auto-update

See latest table in `workloads/phase6/phrasings_coverage.md` (2026-07-26).

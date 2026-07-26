# Phase 6 — Decisions & Progress Log

Evaluation harness. Spec: `PHASE6_EVAL.md`.

**Last updated:** 2026-07-26 (evening) — Aire `gpu012` ablation @ c=1 session logged
(probe gate, LMSYS mine, warm-cache pitfall, optimizer 2×2 partial, vanilla baseline)

---

## Status

| Layer | State |
|-------|--------|
| **Spec** | `PHASE6_EVAL.md` |
| **Harness** | `src/eval/` |
| **TSR counters** | `src/proxy/metrics_tsr.py` + `GET /metrics` |
| **cached_tokens gate** | PASS on Aire when APC + `--enable-prompt-tokens-details` |
| **Workload** | Docs + LMSYS-mined phrasings; `burst_ablation.jsonl` (200) + `burst_full.jsonl` (2000) built |
| **Charts / tables** | scripts ready; need full burst artefacts |
| **Aire ablation c=1** | **Partial — see run table below** (cite only cold/`call1≈0` rows) |
| **Aire full / burst (6f)** | Pending |
| **Phrasing mine** | LMSYS only (ShareGPT/MOSS deferred) — see coverage section |

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
8. **Cold KV between citeable system runs** — restart vLLM (not just the proxy) before
   each fair TSR comparison; require `server_capabilities.cached_tokens_call1 ≈ 0`.
   Restarting proxy alone does **not** clear APC KV.
9. **Optimizer embed matrix (Phase 6):** prefer MiniLM if embed on; skip Qwen for main
   matrix (Phase 4). Default proxy remains rules+full features with embed off unless
   explicitly `OPTIMIZER_EMBEDDING_BACKEND=minilm`.
10. **Hit rate is secondary** — harness `hit = cached_tokens > 0` (often chat-template
    crumbs). Do not read APC `hit_rate=1.0` as “100% exact full-prompt duplicates.”

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

## Aire session 2026-07-26 — infra & probe

**Node / job:** `gpu012`, Slurm job `6882827`, user `bgxj0542`.  
**Model:** `meta-llama/Llama-3.1-8B-Instruct`. **vLLM:** `0.11.0`.

### Gate / APC reporting

1. First probe **FAIL**: `prompt_tokens_details: null` despite APC working
   (engine log showed `Prefix cache hit rate: 45.1%`).
2. Root cause: launcher had `--enable-prefix-caching` but **not**
   `--enable-prompt-tokens-details` (required for usage schema on this build).
3. One-shot without `VLLM_USE_FLASHINFER_SAMPLER=0` crashed (FlashInfer JIT / no nvcc).
4. Working APC launch:
   ```bash
   export VLLM_USE_FLASHINFER_SAMPLER=0
   python -m vllm.entrypoints.openai.api_server \
     --model meta-llama/Llama-3.1-8B-Instruct \
     --host 0.0.0.0 --port 8000 \
     --dtype bfloat16 --gpu-memory-utilization 0.90 \
     --max-model-len 8192 \
     --enable-prefix-caching \
     --enable-prompt-tokens-details
   ```
5. Probe **PASS**: call2 `cached_tokens=64`. Marker written under
   `results/phase6/.cached_tokens_probe_ok.json`.
6. Local repo fix pending push: add `--enable-prompt-tokens-details` to
   `src/engine/run_vllm.sh`; skip `#` comments in `load_workload` (`smoke_tiny.jsonl`).

### Vanilla launch (APC off)

Omit both prefix-caching and prompt-tokens-details flags; keep FlashInfer sampler off.

---

## Phrasing mine & workloads (Aire)

### Raw data

- **LMSYS:** streamed ~20k first-user turns → `workloads/phase6/raw_datasets/lmsys/lmsys_sample.jsonl`
  (gated Hub dataset; access accepted on HF account).
- **ShareGPT:** attempted `RyokoAI/ShareGPT52K` — failed (`'str' object has no attribute 'get'`).
- **MOSS:** hung after README download — aborted.
- **Decision:** proceed with **LMSYS-only** for this ablation corpus; document gap;
  do **not** invent phrasings. ShareGPT/MOSS optional later (implies remine + rebuild + re-eval).

### Mine counts (`mine_phrasings --write`)

| Task | Mined | Source |
|------|------:|--------|
| summarize_3_bullets | 404 | lmsys |
| extract_entities | 221 | lmsys |
| lone_wolf | 11181 | lmsys |

Classifier: regex buckets (summarize / extract first; else short &lt;200 chars without
catalogue keywords → lone_wolf). Light domain noun swap only — no invented instructions.

### Built workloads

| File | Requests | Mix |
|------|----------|-----|
| `burst_ablation.jsonl` | 200 | exact 40 / semantic 80 / best_of_n 30 / lone_wolf 50 |
| `burst_full.jsonl` | 2000 | 400 / 800 / 300 / 500 |

**Construction note:** workloads are **assembled**, not “2k LMSYS chats.” Exact/BoN use
fixed catalogue instructions + synthetic Leeds RAG docs; semantic/lone_wolf **cycle**
mined LMSYS instruction strings.

`--concurrency 1` serialises solo tiers; **Best-of-N groups are always co-dispatched**
(thread pool = group size). `best_of_n_spread_ms` = max−min client send time within group.

---

## Ablation @ concurrency=1 — results (cite carefully)

Workload: `workloads/phase6/burst_ablation.jsonl` (200 req).  
Artefacts on Aire under `results/phase6/`.

### Citeable / usable

| System | Proxy config | TSR | mean TTFT (ms) | p50 lat (ms) | call1 cached | Out file | Notes |
|--------|--------------|-----|----------------|--------------|--------------|----------|-------|
| **vanilla** | (none; APC off) | **0.00** | 101 | 1443 | 0 | `c1_vanilla.jsonl` | Probe `field_present_but_zero`; mode_mismatch false |
| **apc** | direct `:8000` APC on | **0.693** | 98 | 1444 | (early run) | `c1_apc.jsonl` | 200/200; hit_rate 1.0 = weak signal |
| **gptcache** | in-process over `:8000` | **0.857** | 25 | 15 | — | `c1_gptcache.jsonl` | hit_rate **0.65** = real output-cache hits; different metric |
| **optimizer_hold** | rewrite on, hold **on**, embed **off** | **0.700** | 146 | 1506 | **0** | `c1_optimizer.jsonl` → prefer name `c1_optimizer_hold.jsonl` on disk | Cold after vLLM restart; hold ≈ rewrite TSR |
| **optimizer** | rewrite on, hold **off**, MiniLM **on** | **0.700** | 126 | 1454 | 16 | `c1_optimizer_holdoff_minilm.jsonl` | Cold-ish; MiniLM no TSR lift vs ~0.70 |
| **optimizer_hold** | rewrite on, hold **on**, MiniLM **on** | **0.700** | 165 | 1507 | **0** | `c1_optimizer_holdon_minilm.jsonl` | Cold; hold+embed add latency only |

Smoke (not dissertation): `smoke_tiny.jsonl` → `run_apc.jsonl`, n=7, TSR≈0.51 (plumbing only).

### Invalid — do **not** cite (warm KV)

| Symptom | TSR | Evidence | Cause |
|---------|-----|----------|--------|
| optimizer / optimizer_hold “miracle” | **~0.995** | `cached_tokens_call1: 96` | Same vLLM process after prior ablation; proxy restart ≠ cold cache |

**Rule:** after any ablation on APC, **restart vLLM** before the next citeable system run.
Accept only if `cached_tokens_call1 ≈ 0` (single-digit from probe crumb OK; 96 = contaminated).

### Still missing for clean 2×2

| Cell | Hold | Embed | Status |
|------|------|-------|--------|
| A | off | off (rules+full) | Need **cold** re-run → e.g. `c1_optimizer_holdoff_embedoff.jsonl` |
| B | off | minilm | **Done** (`c1_optimizer_holdoff_minilm.jsonl`) |
| C | on | off | **Done** (cold hold-on embed-off, TSR 0.70) |
| D | on | minilm | **Done** (`c1_optimizer_holdon_minilm.jsonl`) |

### Reading the numbers (honesty)

1. **Vanilla TSR=0** vs **APC/Optimizer ~0.69–0.70** with **similar TTFT/latency** —
   primary claim is token saving, not a TTFT win (aligns with Phase 4/5).
2. **Optimizer ≈ APC on TSR** at this scale — rewrite/MiniLM do not move overall TSR much;
   exact+BoN already feed APC; unique RAG tails dominate. Flat TSR is a valid finding.
3. **Hold** at c=1 does not raise TSR; it raises TTFT/p50 slightly (admission wait on BoN).
   Hold’s real test is **burst / co-arrival** (6f), not serial ablation.
4. **GPTCache** highest TSR + tiny p50 — **answer memoization**, not KV prefix reuse.
   Not “best answers”; quality/flexibility tradeoff for 6h spot-check.
5. **APC hit_rate=1.0** ≠ exact full-prompt match rate (`cached_tokens > 0` only).

Default optimizer proxy when embed unset: **`OPTIMIZER_EMBEDDING_BACKEND=off`**,
`OPTIMIZER_SCHEMA_FEATURES=full` → **rules + rich features**, not bare rules_only,
not instruction-embedding. MiniLM is opt-in fallback (Phase 4: prefer MiniLM over Qwen;
default off).

---

## Phase 5 → 6 forward reference

max_batch at hold=50 failed in Phase 5 smoke (client dispatch latency); passed at
hold=500. That was a **smoke methodology** limitation. Phase 6 burst (2k, real
arrival) re-checks whether `OPTIMIZER_TTL_BATCH_PEERS=8` fires at default hold=50.

---

## Run log (Aire)

| Date | Step | Node | Notes |
|------|------|------|-------|
| 2026-07-26 | Probe FAIL→PASS | gpu012 | Need `--enable-prompt-tokens-details` + FlashInfer sampler off |
| 2026-07-26 | Mine LMSYS | gpu012 | 404 / 221 / 11181; ShareGPT/MOSS deferred |
| 2026-07-26 | Build ablation+full | gpu012 | 200 + 2000 JSONL |
| 2026-07-26 | Smoke apc | gpu012 | 7/7 OK |
| 2026-07-26 | Ablation c=1 suite | gpu012 | See tables above; discard TSR≈0.995 warm runs |
| — | 6f full/burst | — | Pending (cold APC restart; re-probe) |
| — | 6h–6j | — | Quality / charts / aggregate pending |

### Next actions

1. Cold **hold-off + embed-off** optimizer cell (complete 2×2).
2. Restart APC vLLM → probe → **full 2k / burst** per system (6f); cold between systems.
3. Optional ShareGPT/MOSS only if willing to remine/rebuild/re-run.
4. Push local fixes: `run_vllm.sh` prompt-tokens-details; `load_workload` `#` skip.
5. Log per-tier TSR for semantic vs exact when writing up.

<!-- phrasings-coverage-auto -->
### Phrasing coverage auto-update

See latest table in `workloads/phase6/phrasings_coverage.md`. Aire mine 2026-07-26:
LMSYS-only (summarize 404, extract 221, lone_wolf 11181); ShareGPT/MOSS not in corpus yet.

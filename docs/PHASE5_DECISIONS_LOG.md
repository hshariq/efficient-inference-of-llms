# Phase 5 — Decisions & Progress Log

Micro-admission hold + TTL escape. Spec: `PHASE5_TTL.md`.

**Last updated:** 2026-07-24 — Aire smokes PASS on gpu014; Phase 5 closed

---

## Status

| Layer | State |
|-------|--------|
| **Design** | Group micro-hold (`ADMISSION_HOLD_MS`) + max batch + max TTL escape |
| **Implementation** | `src/proxy/ttl/` — `_flush_locked` pops under `asyncio.Lock` |
| **Default** | `OPTIMIZER_TTL_MODE=off` |
| **Unit tests** | `tests/test_ttl_queue.py` (incl. simultaneous max_batch + cross-task) |
| **Aire smoke** | **Done** — artefacts in `results/phase5/` |

---

## Locked decisions

1. Hold is **opt-in**; default off = 0 ms pass-through baseline.
2. Only **rewritten** requests with known `catalogue_task` enter the buffer.
3. **Group timer** on first arrival (not only per-request TTL) — collects co-arrivals for APC.
4. Flush reasons: `hold_window` | `max_batch` | `ttl_escape` | `skip`.
5. After wake, each FastAPI handler still calls vLLM (concurrent handlers ≈ co-arrival); we do not merge HTTP responses in the buffer.
6. Priority injection optional / best-effort (**deferred / inert** unless vLLM started with `--scheduling-policy priority` — see below).

---

## Design note vs first draft

First draft used per-waiter TTL only (`batch_peers=2`). Reviewer feedback: without a
**collection window**, co-arrival is weak. Current code matches micro-admission hold
semantics (hold window + max batch + max TTL).

---

## Reviewer flags (2026-07-24) — how we treat them

### 1. Flush race (double-pop / double-dispatch)

The **pasted design snippet** spawned a flush task and popped outside the lock.
**Our implementation does not:** `_flush_locked` always `pop`s the bucket under
`async with self._lock`, and the group timer also re-acquires the lock before flush.
Empty-bucket no-op + timer cancel prevent a second dispatch.

Unit coverage: `test_max_batch_simultaneous_exactly_one_flush` — N concurrent admits at
`batch_peers=N` → exactly one `batch_flushes` increment.

### 2. `OPTIMIZER_TTL_SET_PRIORITY` is best-effort / currently inert

Setting `priority=0` on TTL-escaped bodies only affects scheduling if vLLM was launched
with `--scheduling-policy priority`. `src/engine/run_vllm.sh` does **not** set that flag
today → priority injection is **explicitly deferred / documented as best-effort-only**.
Default `OPTIMIZER_TTL_SET_PRIORITY=0` (off). Do not claim priority scheduling in eval.

### 3. Honesty: hold is not a TTFT speed win at current catalogue design

Phase 4 APC smokes (~400-tok and ~4.5k RAG-scale) showed **TTFT on≈off≈1×** because the
shared catalogue system prefix is short relative to the unique document. Therefore a
50 ms micro-hold to improve co-arrival odds may **add latency with no offsetting TTFT
APC win** at current prefixes.

**Phase 5 framing:** hold/TTL is a **co-arrival + fairness/starvation** mechanism, not a
speed optimization. Cost (added wait) vs benefit (cache-hit / Token Saving Ratio) is
what Phase 6 measures — not TTFT.

### 4. Starvation / independence is the dissertation proof point

Cross-task buckets flush on **independent** group timers. A lonely differently-tasked
request must not wait on another group's batch size. Hard ceiling: wait ≤ `MAX_TTL_MS`
(+ small slack). With default `HOLD_MS < MAX_TTL_MS`, the common disposition is
`hold_window` (~hold_ms); `ttl_escape` appears when age ≥ max TTL at flush (e.g. hold
meets max TTL, or event-loop delay).

Smoke (`smoke_ttl.py`) now covers:

| Scenario | Expect |
|----------|--------|
| Lonely same-task | `hold_window`, wait ≈ hold_ms |
| 2 concurrent same-task | both `hold_window` (peers default 8) |
| Same-task batch + lonely **extract_entities** | different `X-Optimizer-Task`; off-task wait ≤ max_ttl |
| Optional `--max-batch-peers N` | all `max_batch` (proxy peers must = N) |
| Control `--expect-hold-off` | `skip`, wait ≈ 0 |

### 5. Global lock note (optional / Phase 6)

One process-wide `asyncio.Lock` serializes enqueue across **all** task groups. Fine at
current smoke scale; if Phase 6 2k-burst shows contention, consider per-task locks.

---

## Aire smoke checklist (live)

Three runs close Phase 5 — **all PASS** on `gpu014` (2026-07-24):

1. [x] Hold **on** ×3: `hold_window` ≈50 ms; summarize vs extract independence (`results/phase5/smoke_hold_on_r{1,2,3}.txt`)
2. [x] max_batch ×8: PASS with hold=500 / max_ttl=1000 (`results/phase5/smoke_max_batch.txt`)
3. [x] Hold **off** control: `skip`, wait 0.00 (`results/phase5/smoke_hold_off.txt`)

### Smoke notes

- **Hold-off control is intentionally loose:** asserts `skip` + wait ≈ 0 only. No
  `X-Optimizer-Task` check — control path is disposition/timing, not tagging.
- **Hold-on jitter:** 3× at hold=50 showed stable ~49–51 ms waits; no boundary flake near 200.
- **max_batch at hold=50:** first attempt failed (`hold_window`) — 8 HTTP admits did not
  all reach the bucket inside 50 ms. Re-ran with hold=500 → all eight `max_batch`,
  waits ~0–40 ms (early flush). Documented limitation of **smoke methodology** (client
  dispatch latency vs short window), not a queue logic bug / silent goalpost move.
  **`max_batch` behavior under realistic default `hold_ms` (50) to be re-validated under
  Phase 6 burst load, not just this synthetic peers=8 retry.**
- Assertions use `MAX_TTL_MS + 40 ms` slack.

### Phase 5 → Phase 6

Phase 5 plumbing verified. Next: **Token Saving Ratio / cached-token counts** under
hold on vs off (cost = added wait_ms; benefit ≠ TTFT at current catalogue design).

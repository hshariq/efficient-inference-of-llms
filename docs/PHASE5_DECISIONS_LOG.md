# Phase 5 — Decisions & Progress Log

Micro-admission hold + TTL escape. Spec: `PHASE5_TTL.md`.

**Last updated:** 2026-07-23 — aligned with group hold-window design

---

## Status

| Layer | State |
|-------|--------|
| **Design** | Group micro-hold (`ADMISSION_HOLD_MS`) + max batch + max TTL escape |
| **Implementation** | `src/proxy/ttl/` |
| **Default** | `OPTIMIZER_TTL_MODE=off` |
| **Unit tests** | `tests/test_ttl_queue.py` |
| **Aire smoke** | Pending |

---

## Locked decisions

1. Hold is **opt-in**; default off = 0 ms pass-through baseline.
2. Only **rewritten** requests with known `catalogue_task` enter the buffer.
3. **Group timer** on first arrival (not only per-request TTL) — collects co-arrivals for APC.
4. Flush reasons: `hold_window` | `max_batch` | `ttl_escape` | `skip`.
5. After wake, each FastAPI handler still calls vLLM (concurrent handlers ≈ co-arrival); we do not merge HTTP responses in the buffer.
6. Priority injection optional / best-effort.

---

## Design note vs first draft

First draft used per-waiter TTL only (`batch_peers=2`). Reviewer feedback: without a
**collection window**, co-arrival is weak. Current code matches micro-admission hold
semantics (hold window + max batch + max TTL).

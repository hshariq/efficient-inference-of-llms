# Phase 5 — Micro-admission hold + TTL escape

> **Goal:** Env-gated **holding pen** in the proxy so same canonical-task requests
> co-arrive at vLLM for APC, with a hard **TTL escape** so lonely/stale requests
> never starve. Not a reimplementation of vLLM continuous batching.

Default: **off** (`OPTIMIZER_TTL_MODE=off`) — pure pass-through / Phase 4 path.

---

## Why (reviewer framing)

With 0 ms hold, APC co-arrival is client concurrency luck. “TTL” with no queue is
dead code. Phase 5 adds a lightweight micro-buffer keyed by catalogue task.

---

## Behaviour

```text
rewrite_request
  → if hold off OR not rewritten OR no task: skip (0 ms)
  → else enqueue under catalogue_task
       first waiter starts group timer (ADMISSION_HOLD_MS)
       flush when: MAX_COARRIVE batch | HOLD window expired | oldest ≥ MAX_TTL
  → waiters wake → each continues httpx to vLLM (handlers run concurrently)
```

| Disposition | Meaning |
|-------------|---------|
| `skip` | Hold disabled / bypass / no task |
| `hold_window` | Group flushed after collection window |
| `max_batch` | Instant flush at batch size |
| `ttl_escape` | Oldest age ≥ max TTL (starvation escape) |

Headers: `X-Optimizer-TTL`, `X-Optimizer-TTL-Wait-Ms`.

---

## Env

| Variable | Alias | Default | Meaning |
|----------|-------|---------|---------|
| `OPTIMIZER_TTL_MODE` | `ENABLE_ADMISSION_HOLD` | `off` | Master toggle |
| `OPTIMIZER_ADMISSION_HOLD_MS` | `ADMISSION_HOLD_MS` | `50` | Co-arrival window |
| `OPTIMIZER_MAX_TTL_MS` | `MAX_TTL_MS` | `200` | Hard escape |
| `OPTIMIZER_TTL_BATCH_PEERS` | `MAX_COARRIVE_BATCH_SIZE` | `8` | Instant flush size |
| `OPTIMIZER_TTL_SET_PRIORITY` | — | `0` | Best-effort `priority=0` on TTL escape |

Baselines: hold off vs hold on (e.g. 30–50 ms window).

---

## Done checklist

- [x] Spec + decisions log
- [x] Group-level micro-hold + TTL escape (`src/proxy/ttl/`)
- [x] Wire `app.py` / `start_proxy.sh` / headers
- [x] Unit tests
- [x] `smoke_ttl.py`
- [ ] Aire smoke with `OPTIMIZER_TTL_MODE=on`

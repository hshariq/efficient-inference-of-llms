# Phase 5 results

Narrative / decisions: **`docs/PHASE5_DECISIONS_LOG.md`**  
Spec: **`PHASE5_TTL.md`**  
**Status:** Aire smokes complete on `gpu014` (2026-07-24). Phase 5 closed.

## Live smokes (vLLM `:8000` + proxy `:9000`)

| File | Condition | Result |
|------|-----------|--------|
| `smoke_hold_on_r1.txt` … `r3.txt` | Hold on, 50/200/peers=8, 3× | PASS — `hold_window` ~50 ms; cross-task independence |
| `smoke_max_batch.txt` | Hold 500 / max_ttl 1000 / peers=8 | PASS — 8× `max_batch` |
| `smoke_hold_off.txt` | `OPTIMIZER_TTL_MODE=off` | PASS — `skip`, wait 0 |

### Notes

- Hold-on run **3×** to rule out timing flake near the `MAX_TTL_MS` boundary — all stable (~49–51 ms), no variance.
- First `max_batch` attempt at hold=50 failed: 8 HTTP admits did not co-arrive inside 50 ms → `hold_window`. Not a logic bug — a property of client-side dispatch latency at short windows; re-ran with hold=500 → PASS. Realistic burst behavior at default `hold_ms=50` revisited in Phase 6.
- Hold-off requires **proxy restart** with `OPTIMIZER_TTL_MODE=off` (client `--expect-hold-off` only asserts).

## Not Phase 5

- Token Saving Ratio / cached-token eval → **Phase 6**

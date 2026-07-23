"""
Async micro-admission hold keyed by catalogue task.

Group-level collection window (co-arrival for APC), with:
  - flush when MAX_COARRIVE batch size hit
  - flush when HOLD_MS window expires (dispatch whoever is waiting)
  - TTL escape if oldest waiter exceeds MAX_TTL_MS
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from src.proxy.ttl.config import TtlConfig

logger = logging.getLogger("optimizer_box.ttl")


@dataclass
class TtlDecision:
    disposition: str  # skip | hold_window | max_batch | ttl_escape
    wait_ms: float
    ttl_escalated: bool
    catalogue_task: str | None = None

    def header_value(self) -> str:
        return self.disposition


@dataclass
class _Waiter:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    enqueued_at: float = 0.0
    disposition: str | None = None
    ttl_escalated: bool = False


class AdmissionHold:
    """
    Micro-admission hold (Phase 5).

    First waiter for a task starts a group timer (admission_hold_ms). Peers that
    arrive in that window flush together → near-simultaneous vLLM handoff for APC.
    Lonely / late requests still leave via hold-window expiry or max TTL escape.
    """

    def __init__(self, config: TtlConfig | None = None) -> None:
        self.config = config or TtlConfig.from_env()
        self._lock = asyncio.Lock()
        self._buckets: dict[str, list[_Waiter]] = {}
        self._timers: dict[str, asyncio.Task] = {}
        self.holds = 0
        self.hold_window_flushes = 0
        self.batch_flushes = 0
        self.ttl_flushes = 0
        self.skips = 0

    def reload_config(self, config: TtlConfig | None = None) -> None:
        self.config = config or TtlConfig.from_env()

    async def admit(
        self,
        catalogue_task: str | None,
        *,
        rewritten: bool,
    ) -> TtlDecision:
        cfg = self.config
        if not cfg.enabled or not rewritten or not catalogue_task:
            self.skips += 1
            return TtlDecision(
                disposition="skip",
                wait_ms=0.0,
                ttl_escalated=False,
                catalogue_task=catalogue_task,
            )

        waiter = _Waiter(enqueued_at=time.perf_counter())
        self.holds += 1

        async with self._lock:
            bucket = self._buckets.setdefault(catalogue_task, [])
            first = len(bucket) == 0
            bucket.append(waiter)

            if first:
                self._timers[catalogue_task] = asyncio.create_task(
                    self._group_timer(catalogue_task),
                    name=f"hold-{catalogue_task}",
                )

            if len(bucket) >= cfg.batch_peers:
                self._flush_locked(catalogue_task, reason="max_batch", escalated=False)

        await waiter.event.wait()
        wait_ms = (time.perf_counter() - waiter.enqueued_at) * 1000.0
        decision = TtlDecision(
            disposition=waiter.disposition or "hold_window",
            wait_ms=wait_ms,
            ttl_escalated=waiter.ttl_escalated,
            catalogue_task=catalogue_task,
        )
        logger.info(
            "ttl admit task=%s disposition=%s wait_ms=%.2f escalated=%s",
            catalogue_task,
            decision.disposition,
            decision.wait_ms,
            decision.ttl_escalated,
        )
        return decision

    async def _group_timer(self, task: str) -> None:
        cfg = self.config
        hold_s = max(0.0, cfg.admission_hold_ms) / 1000.0
        try:
            await asyncio.sleep(hold_s)
        except asyncio.CancelledError:
            return

        async with self._lock:
            bucket = self._buckets.get(task)
            if not bucket:
                self._timers.pop(task, None)
                return
            oldest = min(w.enqueued_at for w in bucket)
            age_ms = (time.perf_counter() - oldest) * 1000.0
            if age_ms >= cfg.max_ttl_ms:
                reason = "ttl_escape"
                escalated = True
            else:
                reason = "hold_window"
                escalated = False
            self._flush_locked(task, reason=reason, escalated=escalated)

    def _flush_locked(self, task: str, *, reason: str, escalated: bool) -> None:
        bucket = self._buckets.pop(task, [])
        timer = self._timers.pop(task, None)
        if timer is not None and not timer.done():
            timer.cancel()
        if not bucket:
            return
        if reason == "max_batch":
            self.batch_flushes += 1
        elif reason == "ttl_escape":
            self.ttl_flushes += 1
        else:
            self.hold_window_flushes += 1
        for w in bucket:
            if w.disposition is not None:
                continue
            w.disposition = reason
            w.ttl_escalated = escalated
            w.event.set()


_hold: AdmissionHold | None = None


def get_admission_hold(config: TtlConfig | None = None) -> AdmissionHold:
    global _hold
    if _hold is None:
        _hold = AdmissionHold(config)
    elif config is not None:
        _hold.reload_config(config)
    return _hold


def reset_admission_hold_for_tests() -> None:
    global _hold
    _hold = None

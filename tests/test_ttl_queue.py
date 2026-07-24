"""Unit tests for Phase 5 micro-admission hold (no vLLM, no pytest-asyncio)."""

from __future__ import annotations

import asyncio

from src.proxy.ttl.config import TtlConfig
from src.proxy.ttl.queue import AdmissionHold, reset_admission_hold_for_tests


def setup_function() -> None:
    reset_admission_hold_for_tests()


def teardown_function() -> None:
    reset_admission_hold_for_tests()


def test_mode_off_skips() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="off", admission_hold_ms=50, max_ttl_ms=200, batch_peers=8)
        )
        d = await hold.admit("summarize_3_bullets", rewritten=True)
        assert d.disposition == "skip"
        assert d.wait_ms == 0.0
        assert hold.skips == 1

    asyncio.run(_run())


def test_bypass_skips_even_when_on() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=50, max_ttl_ms=200, batch_peers=8)
        )
        d = await hold.admit("summarize_3_bullets", rewritten=False)
        assert d.disposition == "skip"

    asyncio.run(_run())


def test_hold_window_flush_lonely() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=30, max_ttl_ms=200, batch_peers=8)
        )
        d = await hold.admit("summarize_3_bullets", rewritten=True)
        assert d.disposition == "hold_window"
        assert d.ttl_escalated is False
        assert d.wait_ms >= 25.0
        assert hold.hold_window_flushes == 1

    asyncio.run(_run())


def test_max_batch_flush() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=500, max_ttl_ms=1000, batch_peers=2)
        )

        async def one() -> str:
            d = await hold.admit("summarize_3_bullets", rewritten=True)
            return d.disposition

        d1, d2 = await asyncio.gather(one(), one())
        assert d1 == "max_batch"
        assert d2 == "max_batch"
        assert hold.batch_flushes == 1

    asyncio.run(_run())


def test_max_batch_simultaneous_exactly_one_flush() -> None:
    """Race guard: N simultaneous admits at batch_peers → one flush, no double-dispatch."""

    async def _run() -> None:
        n = 8
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=2000, max_ttl_ms=5000, batch_peers=n)
        )

        async def one() -> str:
            return (await hold.admit("summarize_3_bullets", rewritten=True)).disposition

        dispositions = list(await asyncio.gather(*[one() for _ in range(n)]))
        assert dispositions == ["max_batch"] * n
        assert hold.batch_flushes == 1
        assert hold.hold_window_flushes == 0
        assert hold.ttl_flushes == 0
        assert "summarize_3_bullets" not in hold._buckets

    asyncio.run(_run())


def test_coarrive_two_within_hold_window() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=40, max_ttl_ms=200, batch_peers=8)
        )

        async def a() -> str:
            return (await hold.admit("summarize_3_bullets", rewritten=True)).disposition

        async def b() -> str:
            await asyncio.sleep(0.01)
            return (await hold.admit("summarize_3_bullets", rewritten=True)).disposition

        dispositions = list(await asyncio.gather(a(), b()))
        assert dispositions == ["hold_window", "hold_window"]
        assert hold.hold_window_flushes == 1

    asyncio.run(_run())


def test_independent_task_groups_not_blocked() -> None:
    """Cross-task: off-task lonely request flushes on its own timer, not behind another group."""

    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=40, max_ttl_ms=200, batch_peers=8)
        )

        async def batch_a() -> float:
            return (await hold.admit("summarize_3_bullets", rewritten=True)).wait_ms

        async def batch_b() -> float:
            await asyncio.sleep(0.005)
            return (await hold.admit("summarize_3_bullets", rewritten=True)).wait_ms

        async def lonely() -> tuple[str, float]:
            await asyncio.sleep(0.01)
            d = await hold.admit("extract_entities", rewritten=True)
            return d.disposition, d.wait_ms

        wa, wb, (lonely_disp, lonely_wait) = await asyncio.gather(
            batch_a(), batch_b(), lonely()
        )
        assert lonely_disp == "hold_window"
        assert lonely_wait <= 200.0 + 30.0
        assert wa <= 200.0 + 30.0
        assert wb <= 200.0 + 30.0
        # Two groups → two hold-window flushes (not one shared batch).
        assert hold.hold_window_flushes == 2

    asyncio.run(_run())


def test_ttl_escape_when_hold_meets_max_ttl() -> None:
    async def _run() -> None:
        hold = AdmissionHold(
            TtlConfig(mode="on", admission_hold_ms=40, max_ttl_ms=40, batch_peers=8)
        )
        d = await hold.admit("summarize_3_bullets", rewritten=True)
        assert d.disposition == "ttl_escape"
        assert d.ttl_escalated is True
        assert hold.ttl_flushes == 1

    asyncio.run(_run())

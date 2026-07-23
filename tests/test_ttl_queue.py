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

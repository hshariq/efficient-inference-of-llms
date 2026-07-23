"""Unit tests for Phase 5 micro-admission hold (no vLLM)."""

from __future__ import annotations

import asyncio

import pytest

from src.proxy.ttl.config import TtlConfig
from src.proxy.ttl.queue import AdmissionHold, reset_admission_hold_for_tests


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_admission_hold_for_tests()
    yield
    reset_admission_hold_for_tests()


@pytest.mark.asyncio
async def test_mode_off_skips() -> None:
    hold = AdmissionHold(
        TtlConfig(mode="off", admission_hold_ms=50, max_ttl_ms=200, batch_peers=8)
    )
    d = await hold.admit("summarize_3_bullets", rewritten=True)
    assert d.disposition == "skip"
    assert d.wait_ms == 0.0
    assert hold.skips == 1


@pytest.mark.asyncio
async def test_bypass_skips_even_when_on() -> None:
    hold = AdmissionHold(
        TtlConfig(mode="on", admission_hold_ms=50, max_ttl_ms=200, batch_peers=8)
    )
    d = await hold.admit("summarize_3_bullets", rewritten=False)
    assert d.disposition == "skip"


@pytest.mark.asyncio
async def test_hold_window_flush_lonely() -> None:
    hold = AdmissionHold(
        TtlConfig(mode="on", admission_hold_ms=30, max_ttl_ms=200, batch_peers=8)
    )
    d = await hold.admit("summarize_3_bullets", rewritten=True)
    assert d.disposition == "hold_window"
    assert d.ttl_escalated is False
    assert d.wait_ms >= 25.0
    assert hold.hold_window_flushes == 1


@pytest.mark.asyncio
async def test_max_batch_flush() -> None:
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


@pytest.mark.asyncio
async def test_coarrive_two_within_hold_window() -> None:
    """Two peers in the same window should flush together on hold expiry (batch=8)."""
    hold = AdmissionHold(
        TtlConfig(mode="on", admission_hold_ms=40, max_ttl_ms=200, batch_peers=8)
    )

    async def staggered() -> list[str]:
        async def a() -> str:
            return (await hold.admit("summarize_3_bullets", rewritten=True)).disposition

        async def b() -> str:
            await asyncio.sleep(0.01)
            return (await hold.admit("summarize_3_bullets", rewritten=True)).disposition

        return list(await asyncio.gather(a(), b()))

    dispositions = await staggered()
    assert dispositions == ["hold_window", "hold_window"]
    assert hold.hold_window_flushes == 1

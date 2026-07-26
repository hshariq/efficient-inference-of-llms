"""Unit tests for Phase 6 TSR counters (no vLLM)."""

from __future__ import annotations

from src.proxy.metrics_tsr import TsrCounters, extract_usage_tokens


def test_extract_usage_tokens() -> None:
    prompt, cached = extract_usage_tokens(
        {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 40}}
    )
    assert prompt == 100
    assert cached == 40


def test_extract_missing() -> None:
    assert extract_usage_tokens(None) == (0, 0)
    assert extract_usage_tokens({"prompt_tokens": 10}) == (10, 0)


def test_tsr_hand_computed() -> None:
    """Controlled workload: known processed/saved → expected TSR."""
    c = TsrCounters()
    # Request A: 100 prompt, 0 cached
    c.record(prompt_tokens=100, cached_tokens=0)
    # Request B: 100 prompt, 40 cached (prefix hit)
    c.record(prompt_tokens=100, cached_tokens=40)
    # Request C: 50 prompt, 50 cached
    c.record(prompt_tokens=50, cached_tokens=50)
    snap = c.snapshot()
    assert snap["total_tokens_processed"] == 250
    assert snap["total_tokens_saved"] == 90
    assert abs(snap["tsr"] - (90 / 250)) < 1e-9


def test_cached_cannot_exceed_prompt() -> None:
    c = TsrCounters()
    c.record(prompt_tokens=10, cached_tokens=99)
    assert c.snapshot()["total_tokens_saved"] == 10


def test_reset() -> None:
    c = TsrCounters()
    c.record(prompt_tokens=5, cached_tokens=1)
    c.reset()
    assert c.snapshot()["total_tokens_processed"] == 0
    assert c.snapshot()["tsr"] == 0.0

"""Harness summary helpers (no network)."""

from __future__ import annotations

from src.eval.runner import summarize_results
from src.eval.schemas import RequestResult


def test_summarize_tsr() -> None:
    results = [
        RequestResult(
            req_id="a",
            system="apc",
            tier="exact",
            task="summarize_3_bullets",
            doc_id="d",
            prompt_chars=10,
            ttft_ms=10,
            latency_ms=20,
            prompt_tokens=100,
            completion_tokens=5,
            cached_tokens=0,
            hit=False,
            disposition="ok",
        ),
        RequestResult(
            req_id="b",
            system="apc",
            tier="exact",
            task="summarize_3_bullets",
            doc_id="d",
            prompt_chars=10,
            ttft_ms=12,
            latency_ms=22,
            prompt_tokens=100,
            completion_tokens=5,
            cached_tokens=40,
            hit=True,
            disposition="ok",
        ),
    ]
    s = summarize_results(results)
    assert s["prompt_tokens"] == 200
    assert s["cached_tokens"] == 40
    assert abs(s["tsr"] - 0.2) < 1e-9
    assert abs(s["hit_rate"] - 0.5) < 1e-9

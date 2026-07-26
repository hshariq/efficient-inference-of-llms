#!/usr/bin/env python3
"""
Controlled TSR sanity: hand-computed expected ratio vs TsrCounters.

  PYTHONPATH=. python -m src.eval.verify_tsr
"""

from __future__ import annotations

from src.proxy.metrics_tsr import TsrCounters


def main() -> None:
    # Hand scenario matching tests/test_tsr_counters.py::test_tsr_hand_computed
    expected_processed = 250
    expected_saved = 90
    expected_tsr = expected_saved / expected_processed

    c = TsrCounters()
    c.record(prompt_tokens=100, cached_tokens=0)
    c.record(prompt_tokens=100, cached_tokens=40)
    c.record(prompt_tokens=50, cached_tokens=50)
    snap = c.snapshot()

    assert snap["total_tokens_processed"] == expected_processed
    assert snap["total_tokens_saved"] == expected_saved
    assert abs(snap["tsr"] - expected_tsr) < 1e-9
    print("verify_tsr: PASS")
    print(snap)


if __name__ == "__main__":
    main()

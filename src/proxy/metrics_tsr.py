"""
Phase 6 — proxy-side Token Saving Ratio counters.

TSR = total_tokens_saved / total_tokens_processed

processed: sum of prompt_tokens from upstream usage
saved: sum of cached_tokens from usage.prompt_tokens_details.cached_tokens
"""

from __future__ import annotations

import threading
from typing import Any


class TsrCounters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_tokens_processed = 0
        self.total_tokens_saved = 0
        self.requests = 0

    def record(self, *, prompt_tokens: int, cached_tokens: int) -> None:
        pt = max(0, int(prompt_tokens))
        ct = max(0, int(cached_tokens))
        if ct > pt:
            ct = pt
        with self._lock:
            self.total_tokens_processed += pt
            self.total_tokens_saved += ct
            self.requests += 1

    def reset(self) -> None:
        with self._lock:
            self.total_tokens_processed = 0
            self.total_tokens_saved = 0
            self.requests = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            processed = self.total_tokens_processed
            saved = self.total_tokens_saved
            n = self.requests
        tsr = (saved / processed) if processed else 0.0
        return {
            "total_tokens_processed": processed,
            "total_tokens_saved": saved,
            "requests": n,
            "tsr": tsr,
        }


_counters = TsrCounters()


def get_tsr_counters() -> TsrCounters:
    return _counters


def extract_usage_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    if not usage:
        return 0, 0
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = 0
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        try:
            cached = int(details["cached_tokens"])
        except (TypeError, ValueError):
            cached = 0
    return prompt, cached

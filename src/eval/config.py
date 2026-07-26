"""Eval harness configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SYSTEMS = ("vanilla", "apc", "gptcache", "optimizer", "optimizer_hold")

DEFAULT_URLS: dict[str, str] = {
    "vanilla": "http://localhost:8000/v1",
    "apc": "http://localhost:8000/v1",
    # GPTCache is in-process; base_url is upstream vLLM
    "gptcache": "http://localhost:8000/v1",
    "optimizer": "http://localhost:9000/v1",
    "optimizer_hold": "http://localhost:9000/v1",
}

MODEL = os.environ.get("EVAL_MODEL", "meta-llama/Llama-3.1-8B-Instruct")


@dataclass
class EvalConfig:
    system: str
    base_url: str
    workload_path: Path
    out_path: Path
    concurrency: int = 1
    max_tokens: int = 64
    temperature: float = 0.0
    model: str = MODEL
    timeout_s: float = 300.0
    proxy_metrics_url: str | None = None  # e.g. http://localhost:9000/metrics
    skip_cached_tokens_gate: bool = False

    @classmethod
    def from_args(
        cls,
        *,
        system: str,
        workload: str | Path,
        out: str | Path | None = None,
        concurrency: int = 1,
        base_url: str | None = None,
        max_tokens: int = 64,
        skip_cached_tokens_gate: bool = False,
    ) -> EvalConfig:
        system = system.strip().lower()
        if system not in SYSTEMS:
            raise ValueError(f"system must be one of {SYSTEMS}, got {system!r}")
        url = (base_url or os.environ.get("EVAL_BASE_URL") or DEFAULT_URLS[system]).rstrip(
            "/"
        )
        wl = Path(workload)
        if not wl.is_absolute():
            wl = ROOT / wl
        if out is None:
            out_path = ROOT / "results" / "phase6" / f"run_{system}.jsonl"
        else:
            out_path = Path(out)
            if not out_path.is_absolute():
                out_path = ROOT / out_path
        metrics = None
        if system.startswith("optimizer"):
            # Proxy root (not /v1)
            root = url.replace("/v1", "").rstrip("/")
            metrics = f"{root}/metrics"
        return cls(
            system=system,
            base_url=url,
            workload_path=wl,
            out_path=out_path,
            concurrency=max(1, concurrency),
            max_tokens=max_tokens,
            proxy_metrics_url=metrics,
            skip_cached_tokens_gate=skip_cached_tokens_gate,
        )

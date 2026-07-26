"""
Hard gate: TSR-dependent systems require a recent successful probe_cached_tokens.

Marker file: results/phase6/.cached_tokens_probe_ok.json
Written only on PASS by `python -m src.eval.probe_cached_tokens`.

Matching is by **upstream vLLM URL fingerprint** (not Slurm hostname), so a probe
against http://localhost:8000/v1 unlocks:
  - apc/gptcache runs hitting :8000
  - optimizer runs hitting :9000 on the same node (proxy → local vLLM)

Re-run the probe after each new GPU allocation / vLLM restart (enforced by max age).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.eval.config import ROOT

MARKER_PATH = ROOT / "results" / "phase6" / ".cached_tokens_probe_ok.json"

SYSTEMS_REQUIRING_CACHED_TOKENS_GATE = frozenset(
    {"apc", "optimizer", "optimizer_hold", "gptcache"}
)

DEFAULT_MAX_AGE_H = 12.0
DEFAULT_VLLM_UPSTREAM = "http://localhost:8000/v1"


def upstream_vllm_fingerprint(url: str) -> str:
    """
    Canonical key for 'which vLLM did we probe / are we measuring'.

    - Explicit :8000 (or non-9000) URLs → that host:port
    - Proxy :9000 URLs → VLLM_BASE_URL env or localhost:8000 (the real engine)
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raw = DEFAULT_VLLM_UPSTREAM
    if "://" not in raw:
        raw = f"http://{raw}"
    u = urlparse(raw)
    host = (u.hostname or "localhost").lower()
    port = u.port
    path = (u.path or "").rstrip("/")

    # Optimizer proxy listen port → map to upstream vLLM
    if port == 9000 or path.endswith("/proxy"):
        upstream = os.environ.get("VLLM_BASE_URL", DEFAULT_VLLM_UPSTREAM).rstrip("/")
        return upstream_vllm_fingerprint(upstream)

    if port is None:
        port = 443 if u.scheme == "https" else 80
    # Normalize default vLLM OpenAI path
    if path in ("", "/v1"):
        path = "/v1"
    return f"{u.scheme}://{host}:{port}{path}"


def write_probe_pass_marker(
    *,
    base_url: str,
    model: str,
    cached_tokens_call2: int,
    usage_call2: dict[str, Any],
) -> Path:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fp = upstream_vllm_fingerprint(base_url)
    payload = {
        "ok": True,
        "ts_unix": time.time(),
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url.rstrip("/"),
        "upstream_vllm": fp,
        "model": model,
        "cached_tokens_call2": cached_tokens_call2,
        "usage_call2": usage_call2,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "hostname": os.environ.get("HOSTNAME") or os.environ.get("COMPUTERNAME"),
    }
    MARKER_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return MARKER_PATH


def read_probe_marker() -> dict[str, Any] | None:
    if not MARKER_PATH.exists():
        return None
    try:
        return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def check_cached_tokens_gate(
    *,
    system: str,
    base_url: str,
    max_age_h: float = DEFAULT_MAX_AGE_H,
    skip: bool = False,
) -> dict[str, Any] | None:
    """
    Raise RuntimeError if system needs the gate and no fresh PASS marker exists.

    Returns marker dict when gate passes (or None when skipped / not required).
    """
    if system not in SYSTEMS_REQUIRING_CACHED_TOKENS_GATE:
        return None

    if skip:
        return {"ok": False, "skipped": True}

    marker = read_probe_marker()
    help_cmd = (
        "PYTHONPATH=. python -m src.eval.probe_cached_tokens "
        "--base-url http://localhost:8000/v1"
    )
    if not marker or not marker.get("ok"):
        raise RuntimeError(
            f"HARD GATE: system={system!r} requires a successful "
            f"probe_cached_tokens pass before eval.\n"
            f"  Missing/invalid marker: {MARKER_PATH}\n"
            f"  Run on THIS GPU allocation (vLLM+APC up):\n    {help_cmd}\n"
            f"  (Override only if you accept silent TSR=0 risk: "
            f"--skip-cached-tokens-gate)"
        )

    age_h = (time.time() - float(marker.get("ts_unix") or 0)) / 3600.0
    if age_h > max_age_h:
        raise RuntimeError(
            f"HARD GATE: probe_cached_tokens marker is stale "
            f"({age_h:.1f}h old > {max_age_h}h).\n"
            f"  Re-run after (re)starting vLLM+APC on this allocation:\n    {help_cmd}"
        )

    marker_fp = marker.get("upstream_vllm") or upstream_vllm_fingerprint(
        str(marker.get("base_url") or "")
    )
    run_fp = upstream_vllm_fingerprint(base_url)
    if marker_fp != run_fp:
        raise RuntimeError(
            f"HARD GATE: probe upstream {marker_fp!r} != run upstream {run_fp!r}.\n"
            f"  Probe the same vLLM the eval will use (not Slurm hostname — "
            f"URL fingerprint).\n    {help_cmd}"
        )

    # Soft note if Slurm job changed (shared NFS marker) — still URL-matched
    marker_job = marker.get("slurm_job_id")
    cur_job = os.environ.get("SLURM_JOB_ID")
    if marker_job and cur_job and marker_job != cur_job:
        print(
            f"NOTE: probe marker from SLURM_JOB_ID={marker_job}, "
            f"current job={cur_job}. URL fingerprint matches; "
            f"re-probe if this allocation's vLLM is newly started.",
            flush=True,
        )
    return marker

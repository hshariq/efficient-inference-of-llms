"""TTL / micro-admission-hold configuration from env."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@dataclass(frozen=True)
class TtlConfig:
    """
    Micro-admission hold knobs.

    Env (Optimizer Box names; aliases accepted):
      OPTIMIZER_TTL_MODE / ENABLE_ADMISSION_HOLD
      OPTIMIZER_ADMISSION_HOLD_MS / ADMISSION_HOLD_MS   — co-arrival window
      OPTIMIZER_MAX_TTL_MS / MAX_TTL_MS                 — starvation escape
      OPTIMIZER_TTL_BATCH_PEERS / MAX_COARRIVE_BATCH_SIZE
      OPTIMIZER_TTL_SET_PRIORITY
    """

    mode: str = "off"  # off | on
    admission_hold_ms: float = 50.0
    max_ttl_ms: float = 200.0
    batch_peers: int = 8
    set_priority: bool = False

    @classmethod
    def from_env(cls) -> TtlConfig:
        # Master toggle: OPTIMIZER_TTL_MODE or ENABLE_ADMISSION_HOLD
        if "OPTIMIZER_TTL_MODE" in os.environ:
            mode_raw = os.environ.get("OPTIMIZER_TTL_MODE", "off").strip().lower()
            mode = "on" if mode_raw in ("on", "1", "true", "yes") else "off"
        elif _truthy("ENABLE_ADMISSION_HOLD", "false"):
            mode = "on"
        else:
            mode = "off"

        hold = _float_env(
            "OPTIMIZER_ADMISSION_HOLD_MS",
            _float_env("ADMISSION_HOLD_MS", 50.0),
        )
        # Backward compat: OPTIMIZER_TTL_MS was old per-request TTL; map to hold if new unset
        if "OPTIMIZER_ADMISSION_HOLD_MS" not in os.environ and "ADMISSION_HOLD_MS" not in os.environ:
            if "OPTIMIZER_TTL_MS" in os.environ:
                hold = _float_env("OPTIMIZER_TTL_MS", hold)

        max_ttl = _float_env(
            "OPTIMIZER_MAX_TTL_MS",
            _float_env("MAX_TTL_MS", _float_env("OPTIMIZER_MAX_HOLD_MS", 200.0)),
        )
        if max_ttl < hold:
            max_ttl = hold

        peers = max(
            1,
            _int_env(
                "OPTIMIZER_TTL_BATCH_PEERS",
                _int_env("MAX_COARRIVE_BATCH_SIZE", 8),
            ),
        )
        prio = _truthy("OPTIMIZER_TTL_SET_PRIORITY", "0")
        return cls(
            mode=mode,
            admission_hold_ms=hold,
            max_ttl_ms=max_ttl,
            batch_peers=peers,
            set_priority=prio,
        )

    @property
    def enabled(self) -> bool:
        return self.mode == "on"

    # Aliases used by older app.py print / tests
    @property
    def ttl_ms(self) -> float:
        return self.admission_hold_ms

    @property
    def max_hold_ms(self) -> float:
        return self.max_ttl_ms

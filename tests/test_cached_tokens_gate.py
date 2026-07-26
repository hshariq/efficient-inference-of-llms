"""Unit tests for cached_tokens hard gate (no network)."""

from __future__ import annotations

import json
import time

import pytest

from src.eval import cached_tokens_gate as gate


def test_fingerprint_maps_proxy_to_vllm(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    assert gate.upstream_vllm_fingerprint("http://localhost:8000/v1") == (
        "http://localhost:8000/v1"
    )
    assert gate.upstream_vllm_fingerprint("http://localhost:9000/v1") == (
        "http://localhost:8000/v1"
    )


def test_gate_skips_vanilla(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gate, "MARKER_PATH", tmp_path / "marker.json")
    assert (
        gate.check_cached_tokens_gate(
            system="vanilla", base_url="http://localhost:8000/v1"
        )
        is None
    )


def test_gate_blocks_without_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gate, "MARKER_PATH", tmp_path / "marker.json")
    with pytest.raises(RuntimeError, match="HARD GATE"):
        gate.check_cached_tokens_gate(
            system="optimizer", base_url="http://localhost:9000/v1"
        )


def test_gate_accepts_fresh_marker_across_proxy_port(tmp_path, monkeypatch) -> None:
    marker = tmp_path / "marker.json"
    monkeypatch.setattr(gate, "MARKER_PATH", marker)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    gate.write_probe_pass_marker(
        base_url="http://localhost:8000/v1",
        model="m",
        cached_tokens_call2=40,
        usage_call2={"prompt_tokens": 100},
    )
    gate.check_cached_tokens_gate(system="apc", base_url="http://localhost:8000/v1")
    gate.check_cached_tokens_gate(
        system="optimizer", base_url="http://localhost:9000/v1"
    )


def test_gate_rejects_stale(tmp_path, monkeypatch) -> None:
    marker = tmp_path / "marker.json"
    monkeypatch.setattr(gate, "MARKER_PATH", marker)
    payload = {
        "ok": True,
        "ts_unix": time.time() - 48 * 3600,
        "upstream_vllm": "http://localhost:8000/v1",
        "base_url": "http://localhost:8000/v1",
    }
    marker.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        gate.check_cached_tokens_gate(
            system="apc", base_url="http://localhost:8000/v1", max_age_h=12
        )


def test_skip_returns_skipped_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gate, "MARKER_PATH", tmp_path / "marker.json")
    out = gate.check_cached_tokens_gate(
        system="apc", base_url="http://localhost:8000/v1", skip=True
    )
    assert out == {"ok": False, "skipped": True}

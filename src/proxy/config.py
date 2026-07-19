"""Proxy configuration via environment variables."""

from __future__ import annotations

import os


def vllm_base_url() -> str:
    """Upstream OpenAI-compatible root, e.g. http://localhost:8000/v1"""
    return os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")


def proxy_host() -> str:
    return os.environ.get("PROXY_HOST", "0.0.0.0")


def proxy_port() -> int:
    return int(os.environ.get("PROXY_PORT", "9000"))

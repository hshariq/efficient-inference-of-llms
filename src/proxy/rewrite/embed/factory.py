"""Swappable embedding backend factory (config flag, no code edits for ablation)."""

from __future__ import annotations

import os
from functools import lru_cache

from src.proxy.rewrite.embed.base import EmbeddingBackend

_BACKENDS = ("off", "minilm", "qwen3")


def list_backends() -> tuple[str, ...]:
    return _BACKENDS


def embedding_backend_name() -> str:
    return os.environ.get("OPTIMIZER_EMBEDDING_BACKEND", "off").strip().lower()


@lru_cache(maxsize=4)
def get_embedding_backend(name: str | None = None) -> EmbeddingBackend | None:
    """
    Return a backend instance, or None when off/unknown.

    OPTIMIZER_EMBEDDING_BACKEND=off|minilm|qwen3
    """
    key = (name or embedding_backend_name()).strip().lower()
    if key in ("off", "none", "0", "false", ""):
        return None
    if key == "minilm":
        from src.proxy.rewrite.embed.minilm_backend import MiniLMBackend

        return MiniLMBackend()
    if key in ("qwen3", "qwen", "qwen3-embedding"):
        from src.proxy.rewrite.embed.qwen_backend import Qwen3EmbeddingBackend

        return Qwen3EmbeddingBackend()
    raise ValueError(f"Unknown embedding backend {key!r}; choose from {list_backends()}")


def clear_backend_cache() -> None:
    get_embedding_backend.cache_clear()

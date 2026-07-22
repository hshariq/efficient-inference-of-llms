"""Embedding fallback backends (local weights only; never primary classifier)."""

from __future__ import annotations

from src.proxy.rewrite.embed.base import EmbeddingBackend, FallbackMatch
from src.proxy.rewrite.embed.factory import get_embedding_backend, list_backends

__all__ = [
    "EmbeddingBackend",
    "FallbackMatch",
    "get_embedding_backend",
    "list_backends",
]

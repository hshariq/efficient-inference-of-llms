"""Shared interface for local embedding fallback backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.proxy.rewrite.schema import Task


@dataclass(frozen=True)
class FallbackMatch:
    task: Task
    score: float  # cosine similarity in [-1, 1] typically
    backend: str


class EmbeddingBackend(ABC):
    name: str
    model_id: str

    @abstractmethod
    def load(self) -> None:
        """Load weights into memory (idempotent). Local HF cache only."""

    @abstractmethod
    def match_task(self, text: str, *, min_score: float) -> FallbackMatch | None:
        """
        Nearest Task among FIXED exemplars. Returns None if below min_score
        or only UNKNOWN would apply.
        """

    def vram_bytes(self) -> int | None:
        """Best-effort CUDA allocated bytes attributable to this process; None if CPU."""
        try:
            import torch

            if not torch.cuda.is_available():
                return None
            return int(torch.cuda.memory_allocated())
        except Exception:  # noqa: BLE001
            return None

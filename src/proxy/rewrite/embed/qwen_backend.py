"""Backend B — Qwen3-Embedding-0.6B (local HF weights only)."""

from __future__ import annotations

import logging

import numpy as np

from src.proxy.rewrite.embed.base import EmbeddingBackend, FallbackMatch
from src.proxy.rewrite.exemplars import TASK_EXEMPLARS
from src.proxy.rewrite.schema import Task

logger = logging.getLogger("optimizer_box.embed.qwen3")

# Confirmed HF card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class Qwen3EmbeddingBackend(EmbeddingBackend):
    name = "qwen3"
    model_id = MODEL_ID

    def __init__(self) -> None:
        self._model = None
        self._exemplar_vecs: dict[Task, np.ndarray] = {}

    def load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("loading embedding backend %s (%s)", self.name, self.model_id)
        # Prefer CPU/GPU auto; on Aire share node with vLLM — caller should
        # watch VRAM (see decisions log). device="cpu" via env if needed.
        import os

        device = os.environ.get("OPTIMIZER_EMBED_DEVICE", None)
        kwargs = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(self.model_id, **kwargs)
        for task, sentences in TASK_EXEMPLARS.items():
            vecs = self._model.encode(sentences, normalize_embeddings=True)
            self._exemplar_vecs[task] = np.asarray(vecs, dtype=np.float32)

    def match_task(self, text: str, *, min_score: float) -> FallbackMatch | None:
        self.load()
        assert self._model is not None
        # Instruction-aware models: use query prompt when available.
        encode_kwargs: dict = {"normalize_embeddings": True}
        try:
            q = self._model.encode([text], prompt_name="query", **encode_kwargs)[0]
        except Exception:  # noqa: BLE001 — some ST versions lack prompts
            q = self._model.encode([text], **encode_kwargs)[0]
        q = np.asarray(q, dtype=np.float32)
        best_task = Task.UNKNOWN
        best_score = -1.0
        for task, mat in self._exemplar_vecs.items():
            scores = mat @ q
            score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_task = task
        if best_task == Task.UNKNOWN or best_score < min_score:
            return None
        return FallbackMatch(task=best_task, score=best_score, backend=self.name)

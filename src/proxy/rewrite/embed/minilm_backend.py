"""Backend A — sentence-transformers MiniLM (local)."""

from __future__ import annotations

import logging

import numpy as np

from src.proxy.rewrite.embed.base import EmbeddingBackend, FallbackMatch
from src.proxy.rewrite.exemplars import TASK_EXEMPLARS
from src.proxy.rewrite.schema import Task

logger = logging.getLogger("optimizer_box.embed.minilm")

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class MiniLMBackend(EmbeddingBackend):
    name = "minilm"
    model_id = MODEL_ID

    def __init__(self) -> None:
        self._model = None
        self._exemplar_vecs: dict[Task, np.ndarray] = {}

    def load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("loading embedding backend %s (%s)", self.name, self.model_id)
        self._model = SentenceTransformer(self.model_id)
        for task, sentences in TASK_EXEMPLARS.items():
            vecs = self._model.encode(sentences, normalize_embeddings=True)
            self._exemplar_vecs[task] = np.asarray(vecs, dtype=np.float32)

    def match_task(self, text: str, *, min_score: float) -> FallbackMatch | None:
        self.load()
        assert self._model is not None
        q = np.asarray(
            self._model.encode([text], normalize_embeddings=True)[0],
            dtype=np.float32,
        )
        best_task = Task.UNKNOWN
        best_score = -1.0
        for task, mat in self._exemplar_vecs.items():
            # max-similarity across exemplars (not single-anchor fragile boundary)
            scores = mat @ q
            score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_task = task
        if best_task == Task.UNKNOWN or best_score < min_score:
            return None
        return FallbackMatch(task=best_task, score=best_score, backend=self.name)

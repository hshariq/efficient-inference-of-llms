"""Backend B — Qwen3-Embedding-0.6B (local HF weights only).

Instruction-aware usage (differs from MiniLM)
---------------------------------------------
Qwen3-Embedding is trained to take:
  Instruct: <task description>
  Query:<text>
on the *query* side; documents/exemplars are embedded without an instruct
(see HF model card). MiniLM has no such asymmetry — plain encode() is correct.

For our fallback we are doing *task classification against fixed exemplars*,
not web retrieval, so we use a classification-specific instruct rather than
the default Sentence-Transformers \"query\" retrieval prompt alone.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from src.proxy.rewrite.embed.base import EmbeddingBackend, FallbackMatch
from src.proxy.rewrite.exemplars import TASK_EXEMPLARS
from src.proxy.rewrite.schema import Task

logger = logging.getLogger("optimizer_box.embed.qwen3")

# Confirmed HF card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"

# Custom instruct for our dissertation use-case (fixed-label task match).
# Keep English — Qwen training instructions were mostly English.
TASK_CLASSIFY_INSTRUCT = (
    "Classify the user request into the closest RAG task type among: "
    "(1) summarize a document in exactly three bullet points, "
    "(2) extract named entities (people, organizations, locations). "
    "Match the query to the most similar task description."
)

# Qwen cosine scores run systematically higher than MiniLM on the same text
# (Instruct+Query wrap). Global default min_score=0.35 lets out-of-catalogue
# prompts force-match (e.g. draft-email → extract_entities at ~0.56). Floor
# calibrated 2026-07-23: draft-email nearest=0.56 must bypass; real rescues
# in ablation were typically well above this when Qwen fired.
QWEN_SCORE_FLOOR = 0.65


def _wrap_query(text: str) -> str:
    """HF-recommended asymmetric format: Instruct + Query on the query side only."""
    return f"Instruct: {TASK_CLASSIFY_INSTRUCT}\nQuery:{text}"


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
        device = os.environ.get("OPTIMIZER_EMBED_DEVICE", None)
        kwargs = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(self.model_id, **kwargs)
        # Exemplars = "documents" → encode WITHOUT instruct (model-card pattern).
        for task, sentences in TASK_EXEMPLARS.items():
            vecs = self._model.encode(sentences, normalize_embeddings=True)
            self._exemplar_vecs[task] = np.asarray(vecs, dtype=np.float32)

    def match_task(self, text: str, *, min_score: float) -> FallbackMatch | None:
        self.load()
        assert self._model is not None
        # Query side: classification instruct + user text.
        wrapped = _wrap_query(text)
        q = np.asarray(
            self._model.encode([wrapped], normalize_embeddings=True)[0],
            dtype=np.float32,
        )
        best_task = Task.UNKNOWN
        best_score = -1.0
        for task, mat in self._exemplar_vecs.items():
            scores = mat @ q
            score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_task = task
        if best_task == Task.UNKNOWN:
            return None
        # Apply QWEN_SCORE_FLOOR for real gates. min_score<=0 skips the floor
        # so diagnostics can read the raw nearest score.
        if min_score <= 0.0:
            effective_min = 0.0
        else:
            effective_min = max(min_score, QWEN_SCORE_FLOOR)
        if best_score < effective_min:
            return None
        return FallbackMatch(task=best_task, score=best_score, backend=self.name)

"""
Tagging orchestration: rules first, optional embedding fallback.

Timing is split: rule_ms vs embed_ms (never a single combined figure).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Literal

from src.proxy.rewrite.embed.factory import get_embedding_backend
from src.proxy.rewrite.schema import SchemaTags, Task, tag_user_text

DEFAULT_CONFIDENCE_THRESHOLD = 0.55
DEFAULT_EMBED_MIN_SCORE = 0.35

AblationCondition = Literal[
    "rules_only",
    "rules_plus_features",
    "embed_minilm",
    "embed_qwen3",
]


@dataclass
class TagConfig:
    rich_features: bool = True
    embedding_backend: str = "off"  # off | minilm | qwen3
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    embed_min_score: float = DEFAULT_EMBED_MIN_SCORE

    @classmethod
    def from_env(cls) -> TagConfig:
        features = os.environ.get("OPTIMIZER_SCHEMA_FEATURES", "full").strip().lower()
        raw_thr = os.environ.get(
            "OPTIMIZER_REWRITE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD)
        )
        raw_min = os.environ.get(
            "OPTIMIZER_EMBED_MIN_SCORE", str(DEFAULT_EMBED_MIN_SCORE)
        )
        try:
            thr = float(raw_thr)
        except ValueError:
            thr = DEFAULT_CONFIDENCE_THRESHOLD
        try:
            emin = float(raw_min)
        except ValueError:
            emin = DEFAULT_EMBED_MIN_SCORE
        return cls(
            rich_features=features not in ("basic", "rules_only", "part1"),
            embedding_backend=os.environ.get("OPTIMIZER_EMBEDDING_BACKEND", "off")
            .strip()
            .lower(),
            confidence_threshold=thr,
            embed_min_score=emin,
        )

    @classmethod
    def for_ablation(cls, condition: AblationCondition) -> TagConfig:
        base = cls.from_env()
        if condition == "rules_only":
            return TagConfig(
                rich_features=False,
                embedding_backend="off",
                confidence_threshold=base.confidence_threshold,
                embed_min_score=base.embed_min_score,
            )
        if condition == "rules_plus_features":
            return TagConfig(
                rich_features=True,
                embedding_backend="off",
                confidence_threshold=base.confidence_threshold,
                embed_min_score=base.embed_min_score,
            )
        if condition == "embed_minilm":
            return TagConfig(
                rich_features=True,
                embedding_backend="minilm",
                confidence_threshold=base.confidence_threshold,
                embed_min_score=base.embed_min_score,
            )
        if condition == "embed_qwen3":
            return TagConfig(
                rich_features=True,
                embedding_backend="qwen3",
                confidence_threshold=base.confidence_threshold,
                embed_min_score=base.embed_min_score,
            )
        raise ValueError(f"Unknown ablation condition: {condition}")


@dataclass
class TagTimingResult:
    tags: SchemaTags
    rule_ms: float
    embed_ms: float
    embed_used: bool
    embed_backend: str | None
    embed_score: float | None
    would_bypass: bool  # task unknown or conf below threshold after all stages


def tag_with_timing(text: str, config: TagConfig | None = None) -> TagTimingResult:
    cfg = config or TagConfig.from_env()

    t0 = time.perf_counter()
    tags = tag_user_text(text, rich_features=cfg.rich_features)
    rule_ms = (time.perf_counter() - t0) * 1000.0

    embed_ms = 0.0
    embed_used = False
    embed_backend: str | None = None
    embed_score: float | None = None

    needs_fallback = tags.task == Task.UNKNOWN or tags.confidence < cfg.confidence_threshold
    if needs_fallback and cfg.embedding_backend not in ("off", "none", "", "false", "0"):
        backend = get_embedding_backend(cfg.embedding_backend)
        if backend is not None:
            t1 = time.perf_counter()
            try:
                match = backend.match_task(text, min_score=cfg.embed_min_score)
            except Exception:  # noqa: BLE001 — never break proxy/ablation path
                match = None
            embed_ms = (time.perf_counter() - t1) * 1000.0
            embed_backend = backend.name
            if match is not None:
                embed_used = True
                embed_score = match.score
                # Keep Part-2 metadata; only replace task + bump confidence for rewrite.
                tags = replace(
                    tags,
                    task=match.task,
                    confidence=max(tags.confidence, cfg.confidence_threshold),
                )

    would_bypass = tags.task == Task.UNKNOWN or tags.confidence < cfg.confidence_threshold
    return TagTimingResult(
        tags=tags,
        rule_ms=rule_ms,
        embed_ms=embed_ms,
        embed_used=embed_used,
        embed_backend=embed_backend,
        embed_score=embed_score,
        would_bypass=would_bypass,
    )

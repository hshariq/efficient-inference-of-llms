"""Schema enums and O(1) rule-based taggers (no runtime clustering)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Domain(str, Enum):
    LEGAL = "legal"
    GENERAL = "general"
    UNKNOWN = "unknown"


class Task(str, Enum):
    SUMMARIZE_3_BULLETS = "summarize_3_bullets"
    EXTRACT_ENTITIES = "extract_entities"
    UNKNOWN = "unknown"


class LengthClass(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass(frozen=True)
class SchemaTags:
    domain: Domain
    task: Task
    length_class: LengthClass
    confidence: float  # 0..1


_SUMMARIZE_PATTERNS = [
    re.compile(r"\bsummariz(?:e|e|ing)\b", re.I),
    re.compile(r"\bsummaris(?:e|ing)\b", re.I),
    re.compile(r"\b3\s*bullets?\b", re.I),
    re.compile(r"\bthree\s+bullets?\b", re.I),
    re.compile(r"\bkey\s+points?\b", re.I),
]

_ENTITY_PATTERNS = [
    re.compile(r"\bextract\b", re.I),
    re.compile(r"\bentit(?:y|ies)\b", re.I),
    re.compile(r"\bnamed\s+entities\b", re.I),
]

_LEGAL_PATTERNS = [
    re.compile(r"\bcontract\b", re.I),
    re.compile(r"\bagreement\b", re.I),
    re.compile(r"\bclause\b", re.I),
    re.compile(r"\blegal\b", re.I),
]


def _length_class(text: str) -> LengthClass:
    n = len(text)
    if n < 500:
        return LengthClass.SHORT
    if n < 4000:
        return LengthClass.MEDIUM
    return LengthClass.LONG


def _score_patterns(text: str, patterns: list[re.Pattern[str]]) -> int:
    return sum(1 for p in patterns if p.search(text))


def tag_user_text(text: str) -> SchemaTags:
    """Deterministic schema tags from the latest user message text."""
    summarize_hits = _score_patterns(text, _SUMMARIZE_PATTERNS)
    entity_hits = _score_patterns(text, _ENTITY_PATTERNS)
    legal_hits = _score_patterns(text, _LEGAL_PATTERNS)

    if summarize_hits > 0 and summarize_hits >= entity_hits:
        task = Task.SUMMARIZE_3_BULLETS
        conf = min(1.0, 0.55 + 0.15 * summarize_hits)
    elif entity_hits > 0:
        task = Task.EXTRACT_ENTITIES
        conf = min(1.0, 0.55 + 0.15 * entity_hits)
    else:
        task = Task.UNKNOWN
        conf = 0.0

    domain = Domain.LEGAL if legal_hits > 0 else (
        Domain.GENERAL if task != Task.UNKNOWN else Domain.UNKNOWN
    )
    if domain == Domain.LEGAL:
        conf = min(1.0, conf + 0.1)

    return SchemaTags(
        domain=domain,
        task=task,
        length_class=_length_class(text),
        confidence=conf,
    )

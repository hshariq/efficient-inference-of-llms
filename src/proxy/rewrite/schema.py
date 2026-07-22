"""Schema enums and O(1) rule-based taggers (no runtime clustering)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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


class EntityFocus(str, Enum):
    TEAM = "team"
    INDIVIDUAL = "individual"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    ANALYSIS = "analysis"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaTags:
    domain: Domain
    task: Task
    length_class: LengthClass
    confidence: float  # heuristic 0..1 — not a calibrated probability
    # Part 2 — metadata only; does NOT select canonical prefixes (see decisions log).
    entity_focus: EntityFocus = EntityFocus.UNKNOWN
    action_type: ActionType = ActionType.UNKNOWN
    excluded_terms: tuple[str, ...] = field(default_factory=tuple)


# On equal nonzero hit counts, earlier entry wins. Summarize is first because the
# primary dissertation / APC case is shared-instruction summarization traffic;
# entity extraction is secondary catalogue coverage.
TASK_PRIORITY: tuple[Task, ...] = (
    Task.SUMMARIZE_3_BULLETS,
    Task.EXTRACT_ENTITIES,
)

# Token buckets (Llama-3.1-8B-Instruct tokenizer). Logging only — not catalogue keys.
_LENGTH_SHORT_TOKENS = 128
_LENGTH_MEDIUM_TOKENS = 1024
_tokenizer_unavailable = False


def _token_len(text: str) -> int:
    """Serving-tokenizer length; falls back to ~chars/4 if gated model unavailable."""
    global _tokenizer_unavailable
    if _tokenizer_unavailable:
        return max(1, len(text) // 4)
    try:
        from src.proxy.rewrite.align import get_tokenizer

        return len(get_tokenizer().encode(text, add_special_tokens=False))
    except Exception:  # noqa: BLE001
        _tokenizer_unavailable = True
        return max(1, len(text) // 4)


def _length_class(text: str) -> LengthClass:
    """
    Token-length buckets using the serving tokenizer (Llama-3.1-8B-Instruct).

    Does NOT select the catalogue entry (catalogue is keyed by Task alone).
    """
    n = _token_len(text)
    if n < _LENGTH_SHORT_TOKENS:
        return LengthClass.SHORT
    if n < _LENGTH_MEDIUM_TOKENS:
        return LengthClass.MEDIUM
    return LengthClass.LONG


_SUMMARIZE_PATTERNS = [
    # US: summarize / summarizes / summarized / summarizing / summarization
    re.compile(r"\bsummariz(?:e|es|ed|ing|ation)\b", re.I),
    # GB: summarise / summarises / summarised / summarising / summarisation
    re.compile(r"\bsummaris(?:e|es|ed|ing|ation)\b", re.I),
    re.compile(r"\bsummary\b", re.I),
    re.compile(r"\b3\s*bullets?\b", re.I),
    re.compile(r"\bthree\s+bullets?\b", re.I),
    re.compile(r"\bbullet\s+points?\b", re.I),
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

# Orthogonal Part-2 fields — independent of task scoring.
_TEAM_PATTERNS = [
    re.compile(r"\bteam(?:s|'?s)?\b", re.I),
    re.compile(r"\bsquad\b", re.I),
    re.compile(r"\bdepartment\b", re.I),
    re.compile(r"\borgani[sz]ation\b", re.I),
    re.compile(r"\bgroup(?:s)?\b", re.I),
    re.compile(r"\bstaff\b", re.I),
]

_INDIVIDUAL_PATTERNS = [
    re.compile(r"\bindividual(?:s)?\b", re.I),
    re.compile(r"\bperson(?:s)?\b", re.I),
    re.compile(r"\bemployee(?:s)?\b", re.I),
    re.compile(r"\bauthor(?:s)?\b", re.I),
    re.compile(r"\bwho\s+(?:wrote|said|signed)\b", re.I),
    re.compile(r"\bpeople\b", re.I),
]

_ANALYSIS_PATTERNS = [
    re.compile(r"\banaly[sz]e\b", re.I),
    re.compile(r"\banaly[sz]is\b", re.I),
    re.compile(r"\bcompare\b", re.I),
    re.compile(r"\bevaluate\b", re.I),
    re.compile(r"\bassess\b", re.I),
    re.compile(r"\breview\b", re.I),
]

_RETRIEVAL_PATTERNS = [
    re.compile(r"\bfind\b", re.I),
    re.compile(r"\bretrieve\b", re.I),
    re.compile(r"\blist\b", re.I),
    re.compile(r"\bextract\b", re.I),
    re.compile(r"\blook\s+up\b", re.I),
    re.compile(r"\bget\s+(?:me\s+)?(?:all|the)\b", re.I),
]

_GENERATION_PATTERNS = [
    re.compile(r"\bwrite\b", re.I),
    re.compile(r"\bgenerate\b", re.I),
    re.compile(r"\bdraft\b", re.I),
    re.compile(r"\bcreate\b", re.I),
    re.compile(r"\bcompose\b", re.I),
    re.compile(r"\bproduce\b", re.I),
]

# Exclusion / negation cues → capture following term/phrase.
# Rule-based on purpose: embeddings collapse "with X" / "without X".
# Metadata only — user text still passes through light_normalize unchanged, so
# exclusion constraints are never stripped from what the LLM sees.
_EXCLUSION_CAPTURE = re.compile(
    r"(?:"
    r"\bwithout\b|"
    r"\bnot using\b|"
    r"\bexcluding\b|"
    r"\bavoid(?:ing)?\b|"
    r"\bdon'?t\s+(?:use|include)\b"
    r")\s+"
    r"([A-Za-z][\w.+#/-]*(?:\s+[A-Za-z][\w.+#/-]*){0,3})",
    re.I,
)


def _score_patterns(text: str, patterns: list[re.Pattern[str]]) -> int:
    return sum(1 for p in patterns if p.search(text))


def _select_task(hit_counts: dict[Task, int]) -> tuple[Task, int]:
    """Highest hit count wins; ties broken by TASK_PRIORITY order."""
    best_task = Task.UNKNOWN
    best_hits = 0
    for task in TASK_PRIORITY:
        hits = hit_counts.get(task, 0)
        if hits > best_hits:
            best_task = task
            best_hits = hits
    return best_task, best_hits


def _select_entity_focus(text: str) -> EntityFocus:
    team = _score_patterns(text, _TEAM_PATTERNS)
    indiv = _score_patterns(text, _INDIVIDUAL_PATTERNS)
    if team == 0 and indiv == 0:
        return EntityFocus.UNKNOWN
    if team >= indiv:
        return EntityFocus.TEAM
    return EntityFocus.INDIVIDUAL


def _select_action_type(text: str) -> ActionType:
    scores = {
        ActionType.ANALYSIS: _score_patterns(text, _ANALYSIS_PATTERNS),
        ActionType.RETRIEVAL: _score_patterns(text, _RETRIEVAL_PATTERNS),
        ActionType.GENERATION: _score_patterns(text, _GENERATION_PATTERNS),
    }
    best = ActionType.UNKNOWN
    best_hits = 0
    # Deliberate order on ties: analysis > retrieval > generation (RAG-eval bias).
    for action in (ActionType.ANALYSIS, ActionType.RETRIEVAL, ActionType.GENERATION):
        hits = scores[action]
        if hits > best_hits:
            best = action
            best_hits = hits
    return best


def extract_excluded_terms(text: str) -> tuple[str, ...]:
    """
    Rule-based exclusion phrases after negation cues.

    Limitation: unusual phrasings not covered by the cue list are missed.
    Does not affect confidence or catalogue selection.
    """
    seen: list[str] = []
    for m in _EXCLUSION_CAPTURE.finditer(text):
        term = " ".join(m.group(1).split())
        if term and term.lower() not in {t.lower() for t in seen}:
            seen.append(term)
    return tuple(seen)


def tag_user_text(text: str, *, rich_features: bool = True) -> SchemaTags:
    """
    Deterministic schema tags from the latest user message text.

    rich_features=False → Part 1 fields only (ablation condition 1).
    Task-level negation remains a known limitation (see decisions log / Part 2).
    """
    summarize_hits = _score_patterns(text, _SUMMARIZE_PATTERNS)
    entity_hits = _score_patterns(text, _ENTITY_PATTERNS)
    legal_hits = _score_patterns(text, _LEGAL_PATTERNS)

    task, hits = _select_task(
        {
            Task.SUMMARIZE_3_BULLETS: summarize_hits,
            Task.EXTRACT_ENTITIES: entity_hits,
        }
    )
    conf = 0.0 if task == Task.UNKNOWN else min(1.0, 0.55 + 0.15 * hits)

    domain = Domain.LEGAL if legal_hits > 0 else (
        Domain.GENERAL if task != Task.UNKNOWN else Domain.UNKNOWN
    )
    if domain == Domain.LEGAL and task != Task.UNKNOWN:
        conf = min(1.0, conf + 0.1)

    entity_focus = EntityFocus.UNKNOWN
    action_type = ActionType.UNKNOWN
    excluded: tuple[str, ...] = ()

    if rich_features:
        entity_focus = _select_entity_focus(text)
        action_type = _select_action_type(text)
        excluded = extract_excluded_terms(text)
        # Additive confidence bumps (like legal) — excluded_terms never affect conf.
        if entity_focus != EntityFocus.UNKNOWN:
            conf = min(1.0, conf + 0.05)
        if action_type != ActionType.UNKNOWN:
            conf = min(1.0, conf + 0.05)

    return SchemaTags(
        domain=domain,
        task=task,
        length_class=_length_class(text),
        confidence=conf,
        entity_focus=entity_focus,
        action_type=action_type,
        excluded_terms=excluded,
    )

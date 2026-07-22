"""
Part 2 coverage: entity_focus, action_type, excluded_terms.

Also confirms exclusion does not change task tag vs the unconstrained twin.
"""

from __future__ import annotations

import pytest

from src.proxy.ablation.fixtures import (
    ACTION_ANALYSIS,
    ACTION_GENERATION,
    ACTION_RETRIEVAL,
    ENTITY_FOCUS_INDIVIDUAL,
    ENTITY_FOCUS_TEAM,
    EXCLUSION_PAIRS,
)
from src.proxy.rewrite.schema import (
    ActionType,
    EntityFocus,
    extract_excluded_terms,
    tag_user_text,
)


@pytest.mark.parametrize("prompt", ENTITY_FOCUS_TEAM)
def test_entity_focus_team(prompt: str):
    tags = tag_user_text(prompt)
    assert tags.entity_focus == EntityFocus.TEAM, prompt


@pytest.mark.parametrize("prompt", ENTITY_FOCUS_INDIVIDUAL)
def test_entity_focus_individual(prompt: str):
    tags = tag_user_text(prompt)
    assert tags.entity_focus == EntityFocus.INDIVIDUAL, prompt


@pytest.mark.parametrize("prompt", ACTION_ANALYSIS)
def test_action_analysis(prompt: str):
    assert tag_user_text(prompt).action_type == ActionType.ANALYSIS, prompt


@pytest.mark.parametrize("prompt", ACTION_RETRIEVAL)
def test_action_retrieval(prompt: str):
    assert tag_user_text(prompt).action_type == ActionType.RETRIEVAL, prompt


@pytest.mark.parametrize("prompt", ACTION_GENERATION)
def test_action_generation(prompt: str):
    assert tag_user_text(prompt).action_type == ActionType.GENERATION, prompt


@pytest.mark.parametrize("base,with_excl,term", EXCLUSION_PAIRS)
def test_exclusion_metadata_same_task(base: str, with_excl: str, term: str):
    """Exclusion is metadata; task tag must match the unconstrained twin."""
    a = tag_user_text(base)
    b = tag_user_text(with_excl)
    assert a.task == b.task, (base, with_excl, a.task, b.task)
    assert term.lower() in " ".join(t.lower() for t in b.excluded_terms)
    assert extract_excluded_terms(base) == ()


def test_rich_features_flag_off():
    text = "Write code without BeautifulSoup for the team."
    basic = tag_user_text(text, rich_features=False)
    rich = tag_user_text(text, rich_features=True)
    assert basic.entity_focus == EntityFocus.UNKNOWN
    assert basic.action_type == ActionType.UNKNOWN
    assert basic.excluded_terms == ()
    assert rich.excluded_terms


def test_excluded_terms_do_not_affect_confidence():
    """Spec: excluded_terms is informational — must not bump confidence."""
    base = "Write web scraping code for this site."
    with_excl = "Write web scraping code for this site without BeautifulSoup."
    a = tag_user_text(base)
    b = tag_user_text(with_excl)
    assert b.excluded_terms  # exclusion was detected
    assert a.confidence == b.confidence
    assert a.task == b.task

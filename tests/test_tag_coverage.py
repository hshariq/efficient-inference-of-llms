"""
Tagger coverage assets for Phase 4 paraphrase resilience.

Run (no HF token needed):
  python -m pytest tests/test_tag_coverage.py -q
"""

from __future__ import annotations

import pytest

from src.proxy.ablation.fixtures import SUMMARIZE_PARAPHRASES
from src.proxy.rewrite.schema import TASK_PRIORITY, Task, tag_user_text

DOC = "\n\nThe oak tree stood in the yard."


@pytest.mark.parametrize("prompt", SUMMARIZE_PARAPHRASES)
def test_summarize_paraphrase_coverage(prompt: str):
    tags = tag_user_text(prompt + DOC)
    assert tags.task == Task.SUMMARIZE_3_BULLETS, (
        f"missed paraphrase (would inflate bypass rate): {prompt!r} → {tags.task}"
    )
    assert tags.confidence >= 0.55


def test_task_priority_tie_prefers_summarize():
    """Equal nonzero hits → earlier TASK_PRIORITY entry (summarize) wins."""
    assert TASK_PRIORITY[0] == Task.SUMMARIZE_3_BULLETS
    # summarize_hits=1 ("summarize"), entity_hits=1 ("entities") → tie → summarize.
    tags = tag_user_text("Please summarize the entities mentioned below.")
    assert tags.task == Task.SUMMARIZE_3_BULLETS


def test_entity_wins_when_more_hits():
    tags = tag_user_text("Extract all named entities from this document.")
    assert tags.task == Task.EXTRACT_ENTITIES


def test_negation_is_a_known_failure_mode():
    """
    Keyword taggers ignore negation. On a hit-count tie, TASK_PRIORITY still
    picks summarize even when the user said not to — document for limitations.
    """
    # summarize: "summarize" + "3 bullets" = 2; entity: "extract" + "entities" = 2.
    text = "Don't summarize this in 3 bullets — extract the entities instead."
    tags = tag_user_text(text)
    assert tags.task == Task.SUMMARIZE_3_BULLETS, (
        "Negation handling changed — update dissertation limitations if intentional"
    )

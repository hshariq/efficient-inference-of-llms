"""
Task exemplars for embedding fallback (fixed catalogue labels only).

Multiple sentences per Task — max-similarity across exemplars at match time.
Never used for negation/exclusion detection.
"""

from __future__ import annotations

from src.proxy.rewrite.schema import Task

TASK_EXEMPLARS: dict[Task, list[str]] = {
    Task.SUMMARIZE_3_BULLETS: [
        "Please summarize the following document in three bullet points.",
        "I need a short summary with exactly 3 bullets.",
        "Give me the key points of this text as three bullets.",
        "Summarise this report in bullet form (three items).",
        "Produce a three-bullet summary of the passage below.",
        "Can you write a summarized version in 3 bullets?",
    ],
    Task.EXTRACT_ENTITIES: [
        "Extract all named entities from this document.",
        "List people, organizations, and locations mentioned in the text.",
        "Identify the entities present in the following passage.",
        "Pull out named entities grouped by type.",
        "Find every person and organisation name in this contract.",
        "Entity extraction: people, orgs, places only.",
    ],
}

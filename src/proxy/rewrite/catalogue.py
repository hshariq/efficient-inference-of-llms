"""
Fixed catalogue of Canonical Task Prefixes.

Pad policy
----------
Padding is real model context (not attention-mask padding). Prefer:
  1) Wording crafted so the *chat-template–rendered* shared span lands on a
     block multiple (see align.py).
  2) If residual pad is required, use only the inert trailer PAD_TRAILER
     (newlines) — never arbitrary / random tokens.

Serving model id (locked): meta-llama/Llama-3.1-8B-Instruct
"""

from __future__ import annotations

from src.proxy.rewrite.schema import Task

# Semantically inert residual pad (align.py may append repeats of this).
PAD_TRAILER = "\n"

# Instruction bodies placed in the *system* role so different user documents
# still share an identical rendered prefix through the system turn.
CANONICAL_SYSTEM: dict[Task, str] = {
    Task.SUMMARIZE_3_BULLETS: (
        "You are a careful analyst. When given a document, respond with "
        "exactly three concise bullet points that capture the main ideas. "
        "Do not add a preamble or closing remarks—bullets only."
    ),
    Task.EXTRACT_ENTITIES: (
        "You are an information-extraction assistant. When given a document, "
        "list named entities grouped as People, Organizations, and Locations. "
        "Use short bullet lists; do not invent entities that are not present."
    ),
}


def system_text_for_task(task: Task) -> str | None:
    return CANONICAL_SYSTEM.get(task)

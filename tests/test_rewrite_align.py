"""
Unit tests for Phase-4 rewrite (schema + chat-template block alignment).

Run (needs transformers + model tokenizer cached or downloadable):
  python -m pytest tests/test_rewrite_align.py -q
"""

from __future__ import annotations

import pytest

from src.proxy.rewrite.align import (
    BLOCK_SIZE,
    MODEL_ID,
    align_system_content,
    get_tokenizer,
    light_normalize,
    shared_prefix_token_len,
)
from src.proxy.rewrite.catalogue import CANONICAL_SYSTEM
from src.proxy.rewrite.pipeline import rewrite_request
from src.proxy.rewrite.schema import Task, tag_user_text


@pytest.fixture(scope="module")
def tokenizer_ready():
    """Alignment tests need the gated Llama tokenizer (HF_TOKEN or local cache)."""
    try:
        get_tokenizer()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"tokenizer unavailable (set HF_TOKEN or run on Aire): {exc}")


def test_model_id_locked():
    assert MODEL_ID == "meta-llama/Llama-3.1-8B-Instruct"


def test_light_normalize_does_not_strip_filler():
    # Trimmer would remove "please"; we must keep wording.
    raw = "  Please   summarize   this  "
    out = light_normalize(raw)
    assert "Please" in out
    assert "summarize" in out
    assert "  " not in out


def test_tag_summarize_and_unknown():
    tags = tag_user_text("Please summarize the following contract in 3 bullets.\n\nDoc...")
    assert tags.task == Task.SUMMARIZE_3_BULLETS
    assert tags.confidence >= 0.55

    tags2 = tag_user_text("What is the weather in Leeds today?")
    assert tags2.task == Task.UNKNOWN


@pytest.mark.parametrize("task", list(CANONICAL_SYSTEM.keys()))
def test_catalogue_block_aligned_via_chat_template(task: Task, tokenizer_ready):
    """Pad against rendered chat-template LCP — not raw string encode."""
    proto = CANONICAL_SYSTEM[task]
    aligned = align_system_content(proto)
    lcp = shared_prefix_token_len(
        aligned,
        "DOCUMENT_A_UNIQUE_BODY_xxx",
        "DOCUMENT_B_UNIQUE_BODY_yyy",
    )
    assert lcp > 0
    assert lcp % BLOCK_SIZE == 0, f"{task}: LCP={lcp} not multiple of {BLOCK_SIZE}"


def test_shared_instruction_different_data_same_system(tokenizer_ready):
    """Two different docs → identical aligned system → same shared prefix length."""
    proto = CANONICAL_SYSTEM[Task.SUMMARIZE_3_BULLETS]
    aligned = align_system_content(proto)
    doc_a = "Alpha corporation quarterly revenue rose 12 percent in Europe."
    doc_b = "Beta municipality approved a new zoning ordinance downtown."
    lcp = shared_prefix_token_len(aligned, doc_a, doc_b)
    assert lcp > 0 and lcp % BLOCK_SIZE == 0


def test_rewrite_on_summarize(monkeypatch, tokenizer_ready):
    monkeypatch.setenv("OPTIMIZER_REWRITE_MODE", "on")
    body = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": "Summarize in three bullets:\n\nThe oak tree stood in the yard.",
            }
        ],
        "stream": True,
    }
    new_body, decision = rewrite_request(body)
    assert decision.action == "rewrite"
    assert new_body["messages"][0]["role"] == "system"
    assert new_body["messages"][1]["role"] == "user"
    assert "oak tree" in new_body["messages"][1]["content"]


def test_rewrite_bypass_unknown(monkeypatch):
    monkeypatch.setenv("OPTIMIZER_REWRITE_MODE", "on")
    body = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "Tell me a joke about penguins."}],
    }
    new_body, decision = rewrite_request(body)
    assert decision.action == "bypass"
    assert new_body is body or new_body["messages"] == body["messages"]


def test_tag_only_identity(monkeypatch):
    monkeypatch.setenv("OPTIMIZER_REWRITE_MODE", "tag_only")
    body = {
        "messages": [
            {"role": "user", "content": "Summarize this agreement in 3 bullets.\n\nHello"}
        ]
    }
    new_body, decision = rewrite_request(body)
    assert decision.action == "identity"
    assert decision.tags is not None
    assert new_body["messages"] == body["messages"]

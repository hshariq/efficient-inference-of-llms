"""
Block alignment against chat-template–rendered prompts (not raw strings).

vLLM APC hashes blocks of the final rendered token sequence. Counting tokens on
the raw canonical prefix alone will mis-align block boundaries.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Any

from src.proxy.rewrite.catalogue import PAD_TRAILER

# vLLM / PagedAttention default block size on our stack
BLOCK_SIZE = 16
MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"


def light_normalize(text: str) -> str:
    """
    Allowed Phase-4 normalization only (NOT Trimmer):
    NFKC + trim + squeeze whitespace. Does not remove filler or paraphrase.
    """
    text = unicodedata.normalize("NFKC", text)
    text = " ".join(text.split())
    return text.strip()


@lru_cache(maxsize=1)
def get_tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(MODEL_ID)


def render_chat_token_ids(messages: list[dict[str, Any]]) -> list[int]:
    """Render messages with the same chat template path we expect vLLM to use."""
    tok = get_tokenizer()
    rendered = tok.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    # Avoid adding extra special tokens beyond what the template already emitted.
    return tok.encode(rendered, add_special_tokens=False)


def longest_common_prefix_len(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def shared_prefix_token_len(system_content: str, user_a: str, user_b: str) -> int:
    """Token length of the APC-shared span for two different user payloads."""
    ids_a = render_chat_token_ids(
        [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_a},
        ]
    )
    ids_b = render_chat_token_ids(
        [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_b},
        ]
    )
    return longest_common_prefix_len(ids_a, ids_b)


@lru_cache(maxsize=32)
def align_system_content(system_content: str) -> str:
    """
    Append inert PAD_TRAILER until the rendered shared prefix length (across two
    distinct dummy user docs) is a multiple of BLOCK_SIZE.
    """
    # Two fixed different docs so LCP stops before user divergence.
    user_a = "DOCUMENT_A_PLACEHOLDER_FOR_ALIGNMENT_ONLY"
    user_b = "DOCUMENT_B_PLACEHOLDER_FOR_ALIGNMENT_ONLY"

    content = system_content
    # Bound iterations so a tokenizer quirk cannot loop forever.
    for _ in range(BLOCK_SIZE * 4):
        lcp = shared_prefix_token_len(content, user_a, user_b)
        if lcp > 0 and lcp % BLOCK_SIZE == 0:
            return content
        content = content + PAD_TRAILER
    raise RuntimeError(
        f"Failed to block-align system content to {BLOCK_SIZE} tokens "
        f"(last LCP={shared_prefix_token_len(content, user_a, user_b)})"
    )


def warm_alignment_cache() -> None:
    """Load tokenizer + pre-align every catalogue entry (call at proxy startup)."""
    from src.proxy.rewrite.catalogue import CANONICAL_SYSTEM

    get_tokenizer()
    for proto in CANONICAL_SYSTEM.values():
        align_system_content(proto)

#!/usr/bin/env python3
"""
Sanity-check embed fallbacks on an out-of-catalogue prompt.

The ablation showed Qwen bypass=0% on n=113 while MiniLM still bypassed 10.6%.
This probe runs the same ``Generate a draft email…`` string that correctly
bypassed under live MiniLM, and prints raw best score + whether ``match_task``
returns None (bypass) or a Task (force-match risk).

  PYTHONPATH=. python -m src.proxy.ablation.probe_embed_bypass
  PYTHONPATH=. python -m src.proxy.ablation.probe_embed_bypass --backends minilm,qwen3

Needs ``sentence-transformers`` (+ GPU/CPU). On Aire use the project .venv.
"""

from __future__ import annotations

import argparse
import sys

from src.proxy.rewrite.embed.factory import clear_backend_cache, get_embedding_backend
from src.proxy.rewrite.tagging import DEFAULT_EMBED_MIN_SCORE, TagConfig, tag_with_timing

DRAFT_EMAIL = "Generate a draft email based on the notes."


def _probe_backend(name: str, text: str, min_score: float) -> None:
    clear_backend_cache()
    backend = get_embedding_backend(name)
    if backend is None:
        print(f"[{name}] backend unavailable")
        return
    print(f"\n=== backend={name} model={backend.model_id} min_score={min_score} ===")
    if name == "qwen3":
        from src.proxy.rewrite.embed.qwen_backend import QWEN_SCORE_FLOOR

        print(f"  (Qwen effective floor = max(min_score, {QWEN_SCORE_FLOOR}))")
    backend.load()
    # Expose raw best score even when below threshold (duplicate match loop lightly).
    match = backend.match_task(text, min_score=min_score)
    # Also score with min_score=0 to see nearest catalogue entry.
    nearest = backend.match_task(text, min_score=0.0)
    if nearest is None:
        print("  nearest: None (unexpected)")
    else:
        print(
            f"  nearest_task={nearest.task.value}  nearest_score={nearest.score:.4f}  "
            f"(ignoring threshold)"
        )
    if match is None:
        print(f"  match_task(@{min_score}): None → would BYPASS (threshold held)")
    else:
        print(
            f"  match_task(@{min_score}): task={match.task.value} score={match.score:.4f} "
            f"→ would REWRITE (force-match risk if out-of-catalogue)"
        )

    cfg = TagConfig(
        rich_features=True,
        embedding_backend=name,
        confidence_threshold=0.55,
        embed_min_score=min_score,
    )
    timed = tag_with_timing(text, cfg)
    print(
        f"  tag_with_timing: task={timed.tags.task.value} conf={timed.tags.confidence:.3f} "
        f"embed_used={timed.embed_used} embed_score={timed.embed_score} "
        f"would_bypass={timed.would_bypass} embed_ms={timed.embed_ms:.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backends",
        default="minilm,qwen3",
        help="Comma-separated: minilm,qwen3",
    )
    parser.add_argument(
        "--text",
        default=DRAFT_EMAIL,
        help="Prompt to probe (default: draft-email out-of-catalogue)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_EMBED_MIN_SCORE,
        help=f"Embed min cosine (default {DEFAULT_EMBED_MIN_SCORE})",
    )
    args = parser.parse_args()

    print(f"probe text: {args.text!r}")
    print(
        "Note: Qwen uses Instruct+Query wrap; MiniLM plain encode — "
        "not a pure weight-only comparison."
    )
    names = [x.strip() for x in args.backends.split(",") if x.strip()]
    failed = 0
    for name in names:
        try:
            _probe_backend(name, args.text, args.min_score)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

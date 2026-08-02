#!/usr/bin/env python3
"""
Build an adversarial semantic-only probe for Phase 6.

Stresses the Phase 4 hypothesis: varied mined instructions + short shared doc,
with **no exact prompt repeats** (unlike burst_full semantic cycling).

Design:
  - Unique LMSYS-mined instructions that rules-tag as summarize_3_bullets
  - One short shared university-style doc (instruction mass matters vs doc mass)
  - Deduped full prompts — first occurrence only

Expected signal:
  - APC: median cached/prompt near crumbs (instruction differs every time)
  - Optimizer rewrite: after first hit, canonical instruction + same doc shares prefix

  PYTHONPATH=. python -m src.eval.build_adversarial_semantic
  PYTHONPATH=. python -m src.eval.build_adversarial_semantic --limit 80
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.proxy.rewrite.schema import Task, tag_user_text
from src.proxy.rewrite.tagging import DEFAULT_CONFIDENCE_THRESHOLD

ROOT = Path(__file__).resolve().parents[2]
PHRASE_PATH = ROOT / "workloads" / "phase6" / "phrasings" / "summarize_3_bullets.jsonl"
OUT_DIR = ROOT / "workloads" / "phase6"
DOC_ID = "doc_adversarial_short"
DOC_PATH = OUT_DIR / "docs" / f"{DOC_ID}.txt"

# Short on purpose: leave headroom for instruction unification to matter.
SHORT_DOC = """\
Assessment Late-Penalty Note (Simulated — adversarial probe)

This short excerpt is for Phase 6 adversarial semantic evaluation only.
It is not an official University of Leeds publication.

Late coursework without an approved extension attracts a penalty of five
percentage points of the module mark per calendar day late, up to five days.
After five days a mark of zero is recorded unless extension or mitigating
circumstances apply.

Short extensions of up to five working days may be granted by a module leader
with supporting evidence. Longer adjustments require a mitigating-circumstances
application, ideally before the original deadline.

Appeals must cite procedural irregularity or bias within published time limits.
Disagreement with academic judgement alone is not grounds for appeal.
""".strip()

_BLOCKLIST = re.compile(
    r"(ignore all (the )?instructions|DAN mode|developer mode|jailbreak|"
    r"\bNSFW\b|tampon|cum\b|BDSM|hacked)",
    re.I,
)


def _load_unique_instructions() -> list[dict]:
    rows = [
        json.loads(line)
        for line in PHRASE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        instr = (row.get("instruction") or "").strip()
        if not instr or instr in seen:
            continue
        if _BLOCKLIST.search(instr):
            continue
        if len(instr) > 400:
            continue
        tags = tag_user_text(instr, rich_features=True)
        if tags.task != Task.SUMMARIZE_3_BULLETS:
            continue
        if tags.confidence < DEFAULT_CONFIDENCE_THRESHOLD:
            continue
        seen.add(instr)
        out.append(
            {
                "instruction": instr,
                "source": row.get("source"),
                "mine_id": row.get("mine_id"),
                "tag_confidence": tags.confidence,
            }
        )
    return out


def build(*, limit: int | None) -> tuple[list[dict], dict]:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(SHORT_DOC + "\n", encoding="utf-8")

    candidates = _load_unique_instructions()
    if limit is not None:
        candidates = candidates[: max(1, limit)]

    items: list[dict] = []
    prompts_seen: set[str] = set()
    for i, row in enumerate(candidates, start=1):
        prompt = f"{row['instruction']}\n\n{SHORT_DOC}"
        if prompt in prompts_seen:
            continue
        prompts_seen.add(prompt)
        items.append(
            {
                "req_id": f"adv-sem-{i}",
                "tier": "semantic",
                "task": "summarize_3_bullets",
                "doc_id": DOC_ID,
                "prompt": prompt,
                "phrasing_source": row.get("source"),
                "mine_id": row.get("mine_id"),
                "tag_confidence": row.get("tag_confidence"),
                "probe": "adversarial_semantic",
            }
        )

    meta = {
        "n": len(items),
        "n_candidates_rules_matched": len(candidates),
        "doc_id": DOC_ID,
        "doc_chars": len(SHORT_DOC),
        "unique_prompts": len(prompts_seen),
        "exact_prompt_duplicates_dropped": 0,
        "design": (
            "unique mined summarize instructions + one short shared doc; "
            "no exact prompt repeats; rules-matched only (embed off)"
        ),
    }
    return items, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max unique instructions (default 100)",
    )
    ap.add_argument(
        "--out",
        default=str(OUT_DIR / "adversarial_semantic.jsonl"),
    )
    args = ap.parse_args()

    items, meta = build(limit=args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    meta_path = out.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "meta": meta}, indent=2))
    if len(items) < 30:
        print(
            "WARNING: fewer than 30 items — mine more summarize phrasings "
            "or lower the confidence filter."
        )


if __name__ == "__main__":
    main()

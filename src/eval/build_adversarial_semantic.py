#!/usr/bin/env python3
"""
Build an adversarial semantic-only probe for Phase 6.

Stresses the Phase 4 hypothesis: varied mined instructions + shared doc(s),
with **no exact prompt repeats** (unlike burst_full semantic cycling).

Design:
  - Unique mined instructions (LMSYS / ShareGPT / MOSS) that rules-tag as
    summarize_3_bullets
  - Doc mode:
      * single — one short shared doc (original §9 probe)
      * corpus — round-robin across the 8 Leeds-style docs (multi-doc sensitivity)
  - Deduped full prompts — first occurrence only

Expected signal (single short doc):
  - APC: median cached/prompt near crumbs
  - Optimizer: canonical prefix + same doc → higher TSR

Multi-doc sensitivity:
  - Shared *instruction* template still unifies under rewrite; docs differ
  - Tests whether §9 win survives longer / varied suffixes (not more n on one doc)

  PYTHONPATH=. python -m src.eval.build_adversarial_semantic
  PYTHONPATH=. python -m src.eval.build_adversarial_semantic --limit 200 \\
      --doc-mode corpus --probe-name adversarial_semantic_multidoc \\
      --out workloads/phase6/adversarial_semantic_multidoc.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from src.proxy.rewrite.schema import Task, tag_user_text
from src.proxy.rewrite.tagging import DEFAULT_CONFIDENCE_THRESHOLD

ROOT = Path(__file__).resolve().parents[2]
PHRASE_PATH = ROOT / "workloads" / "phase6" / "phrasings" / "summarize_3_bullets.jsonl"
OUT_DIR = ROOT / "workloads" / "phase6"
DOCS_DIR = OUT_DIR / "docs"
DOC_ID = "doc_adversarial_short"
DOC_PATH = DOCS_DIR / f"{DOC_ID}.txt"

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

# Full Leeds-style corpus (exclude the short adversarial-only stub).
_CORPUS_DOC_IDS = (
    "doc_assess_regs",
    "doc_lib_services",
    "doc_mod_comp101",
    "doc_mod_math105",
    "doc_policy_attendance",
    "doc_policy_extensions",
    "doc_prog_bsc_cs",
    "doc_wellbeing",
)


def _load_corpus_docs() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for doc_id in _CORPUS_DOC_IDS:
        path = DOCS_DIR / f"{doc_id}.txt"
        if not path.exists():
            raise FileNotFoundError(f"missing corpus doc: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"empty corpus doc: {path}")
        out.append((doc_id, text))
    return out


def _load_unique_instructions(
    *,
    sources: set[str] | None = None,
) -> list[dict]:
    rows = [
        json.loads(line)
        for line in PHRASE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        src = (row.get("source") or "unknown").strip().lower()
        if sources is not None and src not in sources:
            continue
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
                "source": src,
                "mine_id": row.get("mine_id"),
                "tag_confidence": tags.confidence,
            }
        )
    return out


def build(
    *,
    limit: int | None,
    sources: set[str] | None = None,
    probe_name: str = "adversarial_semantic",
    doc_mode: str = "single",
) -> tuple[list[dict], dict]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(SHORT_DOC + "\n", encoding="utf-8")

    if doc_mode == "corpus":
        docs = _load_corpus_docs()
    elif doc_mode == "single":
        docs = [(DOC_ID, SHORT_DOC)]
    else:
        raise ValueError(f"unknown doc_mode {doc_mode!r}; use single|corpus")

    candidates = _load_unique_instructions(sources=sources)
    # Prefer diversity: round-robin by source when multi-source
    if sources is None or len(sources) > 1:
        by_src: dict[str, list[dict]] = {}
        for row in candidates:
            by_src.setdefault(row["source"], []).append(row)
        if len(by_src) > 1:
            ordered: list[dict] = []
            while any(by_src.values()):
                for s in sorted(by_src.keys()):
                    if by_src[s]:
                        ordered.append(by_src[s].pop(0))
            candidates = ordered

    if limit is not None:
        candidates = candidates[: max(1, limit)]

    items: list[dict] = []
    prompts_seen: set[str] = set()
    doc_counts: Counter[str] = Counter()
    for i, row in enumerate(candidates):
        doc_id, doc_text = docs[i % len(docs)]
        prompt = f"{row['instruction']}\n\n{doc_text}"
        if prompt in prompts_seen:
            continue
        prompts_seen.add(prompt)
        doc_counts[doc_id] += 1
        items.append(
            {
                "req_id": f"adv-sem-{len(items) + 1}",
                "tier": "semantic",
                "task": "summarize_3_bullets",
                "doc_id": doc_id,
                "prompt": prompt,
                "phrasing_source": row.get("source"),
                "mine_id": row.get("mine_id"),
                "tag_confidence": row.get("tag_confidence"),
                "probe": probe_name,
            }
        )

    src_counts = Counter(it.get("phrasing_source") for it in items)
    meta = {
        "n": len(items),
        "n_candidates_rules_matched": len(candidates),
        "doc_mode": doc_mode,
        "doc_ids": list(doc_counts.keys()),
        "doc_counts": dict(doc_counts),
        "doc_chars": {d: len(t) for d, t in docs},
        "unique_prompts": len(prompts_seen),
        "exact_prompt_duplicates_dropped": 0,
        "sources": dict(src_counts),
        "design": (
            "unique mined summarize instructions + "
            + (
                "one short shared doc"
                if doc_mode == "single"
                else f"round-robin across {len(docs)} Leeds-style corpus docs"
            )
            + "; no exact prompt repeats; rules-matched only (embed off); "
            f"sources={sorted(sources) if sources else 'all'}"
        ),
    }
    return items, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max unique instructions (default 100; use 200 for multi-doc quick probe)",
    )
    ap.add_argument(
        "--sources",
        default="all",
        help="Comma list: lmsys,sharegpt,moss or 'all' (default)",
    )
    ap.add_argument(
        "--doc-mode",
        choices=("single", "corpus"),
        default="single",
        help="single=short shared doc (§9); corpus=8 Leeds-style docs (sensitivity)",
    )
    ap.add_argument(
        "--out",
        default=str(OUT_DIR / "adversarial_semantic.jsonl"),
    )
    ap.add_argument(
        "--probe-name",
        default="adversarial_semantic",
        help="Label stored on each row (e.g. adversarial_semantic_multidoc)",
    )
    args = ap.parse_args()

    if args.sources.strip().lower() == "all":
        sources = None
    else:
        sources = {s.strip().lower() for s in args.sources.split(",") if s.strip()}

    items, meta = build(
        limit=args.limit,
        sources=sources,
        probe_name=args.probe_name,
        doc_mode=args.doc_mode,
    )
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
            "WARNING: fewer than 30 items — fetch ShareGPT/MOSS, remine, "
            "or lower --limit / confidence filter."
        )


if __name__ == "__main__":
    main()

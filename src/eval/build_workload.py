#!/usr/bin/env python3
"""
Build Phase 6 four-tier workloads.

Phrasing templates come from workloads/phase6/phrasings/*.jsonl (mined).
If a task file is missing/empty, that task's semantic tier is skipped and a
coverage gap is printed (no invented paraphrases).

  PYTHONPATH=. python -m src.eval.build_workload --scale full
  PYTHONPATH=. python -m src.eval.build_workload --scale ablation
  PYTHONPATH=. python -m src.eval.build_workload --scale tiny
"""

from __future__ import annotations

import argparse
import json
import itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "workloads" / "phase6" / "docs"
PHRASE_DIR = ROOT / "workloads" / "phase6" / "phrasings"
OUT_DIR = ROOT / "workloads" / "phase6"

# Fallback ONLY for exact / best_of_n tiers (identical strings — not paraphrases).
# Semantic tier requires mined phrasings files.
EXACT_INSTRUCTION = {
    "summarize_3_bullets": "Please summarize the following in 3 bullets.",
    "extract_entities": "Extract all named entities from the following text.",
}


def _load_docs() -> dict[str, str]:
    docs: dict[str, str] = {}
    for p in sorted(DOCS_DIR.glob("doc_*.txt")):
        docs[p.stem] = p.read_text(encoding="utf-8").strip()
    return docs


def _load_phrasings(task: str) -> list[dict]:
    path = PHRASE_DIR / f"{task}.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _prompt(instruction: str, doc: str) -> str:
    return f"{instruction}\n\n{doc}"


def build(
    *,
    n_exact: int,
    n_semantic: int,
    n_bon: int,
    n_lone: int,
    bon_n: int = 5,
) -> tuple[list[dict], list[str]]:
    docs = _load_docs()
    doc_ids = list(docs.keys())
    gaps: list[str] = []
    items: list[dict] = []
    rid = 0

    def next_id(prefix: str) -> str:
        nonlocal rid
        rid += 1
        return f"{prefix}-{rid}"

    # Tier 1 — exact duplicates (same instruction + same doc)
    task = "summarize_3_bullets"
    doc_id = doc_ids[0]
    exact_prompt = _prompt(EXACT_INSTRUCTION[task], docs[doc_id])
    for _ in range(n_exact):
        items.append(
            {
                "req_id": next_id("exact"),
                "tier": "exact",
                "task": task,
                "doc_id": doc_id,
                "prompt": exact_prompt,
                "phrasing_source": None,
            }
        )

    # Tier 2 — semantic variations (mined phrasings only)
    tasks = ["summarize_3_bullets", "extract_entities"]
    mined_by_task = {t: _load_phrasings(t) for t in tasks}
    for t, rows in mined_by_task.items():
        if not rows:
            gaps.append(
                f"{t}: 0 mined phrasings — semantic tier under-filled "
                f"(run mine_phrasings; do not invent)"
            )

    sem_cycle = []
    for t in tasks:
        for row in mined_by_task[t]:
            for doc_id in doc_ids[:4]:  # doc family subset
                sem_cycle.append((t, row, doc_id))
    if not sem_cycle:
        gaps.append("semantic tier empty — no mined phrasings available")
    else:
        for i, (t, row, doc_id) in zip(range(n_semantic), itertools.cycle(sem_cycle)):
            instr = row["instruction"]
            items.append(
                {
                    "req_id": next_id("sem"),
                    "tier": "semantic",
                    "task": t,
                    "doc_id": doc_id,
                    "prompt": _prompt(instr, docs[doc_id]),
                    "phrasing_source": row.get("source"),
                    "meta": {"mine_id": row.get("mine_id")},
                }
            )

    # Tier 3 — Best-of-N simultaneous identical prefixes
    n_groups = max(1, n_bon // bon_n)
    bon_doc = doc_ids[min(1, len(doc_ids) - 1)]
    bon_prompt = _prompt(EXACT_INSTRUCTION["summarize_3_bullets"], docs[bon_doc])
    written = 0
    for g in range(n_groups):
        gid = f"bon-{g}"
        for j in range(bon_n):
            if written >= n_bon:
                break
            items.append(
                {
                    "req_id": next_id("bon"),
                    "tier": "best_of_n",
                    "task": "summarize_3_bullets",
                    "doc_id": bon_doc,
                    "prompt": bon_prompt,
                    "phrasing_source": None,
                    "best_of_n_group": gid,
                }
            )
            written += 1

    # Tier 4 — lone wolves (mined out-of-schema if available)
    lone_rows = _load_phrasings("lone_wolf")
    if not lone_rows:
        gaps.append(
            "lone_wolf: 0 mined phrasings — tier 4 under-filled "
            "(mine unrelated ShareGPT/LMSYS/MOSS queries)"
        )
        # Minimal non-invented placeholders forbidden — emit nothing if empty
    else:
        for i, row in zip(range(n_lone), itertools.cycle(lone_rows)):
            items.append(
                {
                    "req_id": next_id("lone"),
                    "tier": "lone_wolf",
                    "task": None,
                    "doc_id": None,
                    "prompt": row["instruction"],
                    "phrasing_source": row.get("source"),
                    "meta": {"mine_id": row.get("mine_id")},
                }
            )

    return items, gaps


SCALES = {
    "tiny": dict(n_exact=2, n_semantic=2, n_bon=2, n_lone=1, bon_n=2),
    "ablation": dict(n_exact=40, n_semantic=80, n_bon=30, n_lone=50, bon_n=5),
    "full": dict(n_exact=400, n_semantic=800, n_bon=300, n_lone=500, bon_n=5),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", choices=sorted(SCALES), default="ablation")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    items, gaps = build(**SCALES[args.scale])
    out = Path(args.out) if args.out else OUT_DIR / f"burst_{args.scale}.jsonl"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"wrote {len(items)} requests -> {out}")
    for g in gaps:
        print(f"COVERAGE GAP: {g}")
    # tier counts
    from collections import Counter

    print(dict(Counter(i["tier"] for i in items)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Peek raw dump shapes + test phrasing extraction (debug)."""

from __future__ import annotations

import json
from pathlib import Path

from src.eval.mine_phrasings import _extract_human, SUMMARIZE_RE, ENTITY_RE

RAW = Path(__file__).resolve().parents[2] / "workloads" / "phase6" / "raw_datasets"


def peek(path: Path, n: int = 3) -> None:
    print(f"\n=== {path} ===")
    if not path.exists():
        print("MISSING")
        return
    ok = 0
    summ = 0
    for i, line in enumerate(path.open(encoding="utf-8", errors="ignore")):
        if not line.strip():
            continue
        if i >= 2000 and i > n:  # scan first 2k for yield stats, print first n
            break
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if i < n:
            keys = list(obj.keys()) if isinstance(obj, dict) else type(obj).__name__
            print(f"row0 keys/type: {keys}")
            print(json.dumps(obj, ensure_ascii=False)[:600])
            text = _extract_human(obj)
            print(f"extracted: {text[:200]!r}" if text else "extracted: None")
        text = _extract_human(obj)
        if text:
            ok += 1
            if SUMMARIZE_RE.search(text):
                summ += 1
    # full file quick count
    total = 0
    extracted = 0
    summarize = 0
    for line in path.open(encoding="utf-8", errors="ignore"):
        if not line.strip():
            continue
        total += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _extract_human(obj)
        if text:
            extracted += 1
            if SUMMARIZE_RE.search(text):
                summarize += 1
    print(f"stats: total={total} extracted={extracted} summarize_re={summarize}")


def main() -> None:
    for rel in (
        "sharegpt/sharegpt_sample.jsonl",
        "moss/moss_sample.jsonl",
        "lmsys/lmsys_sample.jsonl",
    ):
        peek(RAW / rel)


if __name__ == "__main__":
    main()

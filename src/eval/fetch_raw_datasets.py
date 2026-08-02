#!/usr/bin/env python3
"""
Fetch sample ShareGPT / MOSS / extra LMSYS dumps for Phase 6 phrasing mining.

Writes under workloads/phase6/raw_datasets/{sharegpt,moss,lmsys}/.

  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source moss --max-rows 50000
  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source sharegpt --max-rows 80000
  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source lmsys --max-rows 50000
  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source all --max-rows 50000

Requires: pip install datasets
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "workloads" / "phase6" / "raw_datasets"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {path} ({len(rows)} rows)")


def _stream_rows(ds, max_rows: int, normalise) -> list[dict]:
    rows: list[dict] = []
    for i, ex in enumerate(ds):
        if i >= max_rows:
            break
        row = normalise(ex)
        if row:
            rows.append(row)
        if (i + 1) % 5000 == 0:
            print(f"  … scanned {i + 1}, kept {len(rows)}")
    return rows


def fetch_sharegpt(*, max_rows: int) -> Path:
    from datasets import load_dataset

    out = RAW / "sharegpt" / "sharegpt_sample.jsonl"

    def norm(ex: dict) -> dict | None:
        if "conversations" in ex:
            return {"conversations": ex["conversations"]}
        if "conversation" in ex:
            return {"conversations": ex["conversation"]}
        return dict(ex)

    # Prefer known JSON data files on the classic Vicuna ShareGPT dump
    attempts = [
        lambda: load_dataset(
            "anon8231489123/ShareGPT_Vicuna_unfiltered",
            data_files="ShareGPT_V3_unfiltered_cleaned_split.json",
            split="train",
            streaming=True,
        ),
        lambda: load_dataset(
            "Aeala/ShareGPT_Vicuna_unfiltered", split="train", streaming=True
        ),
    ]
    last_err: Exception | None = None
    for load in attempts:
        try:
            print(f"trying ShareGPT via {load.__name__ if hasattr(load, '__name__') else load} …")
            ds = load()
            rows = _stream_rows(ds, max_rows, norm)
            if rows:
                _write_jsonl(out, rows)
                return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  failed: {exc}")
    raise RuntimeError(f"ShareGPT fetch failed; last error: {last_err}")


def fetch_moss(*, max_rows: int) -> Path:
    from datasets import load_dataset

    out = RAW / "moss" / "moss_sample.jsonl"

    def norm(ex: dict) -> dict | None:
        # YeungNLP / MOSS: often {"chat":[{"human":...,"assistant":...}, ...]}
        if "chat" in ex and isinstance(ex["chat"], list):
            conv = []
            for turn in ex["chat"]:
                if not isinstance(turn, dict):
                    continue
                if "human" in turn:
                    conv.append({"from": "human", "value": str(turn["human"])})
                if "assistant" in turn:
                    conv.append({"from": "gpt", "value": str(turn["assistant"])})
            if conv:
                return {"conversations": conv}
        if "conversation" in ex:
            return {"conversations": ex["conversation"]}
        if "conversations" in ex:
            return {"conversations": ex["conversations"]}
        if "human" in ex:
            return {"human": str(ex["human"])[:500]}
        return dict(ex)

    attempts = [
        ("YeungNLP/moss-003-sft-data", None),
        ("fnlp/moss-003-sft-data", None),
    ]
    last_err: Exception | None = None
    for name, _ in attempts:
        try:
            print(f"trying MOSS dataset: {name} …")
            ds = load_dataset(name, split="train", streaming=True)
            rows = _stream_rows(ds, max_rows, norm)
            if rows:
                _write_jsonl(out, rows)
                return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  failed: {exc}")
    raise RuntimeError(f"MOSS fetch failed; last error: {last_err}")


def fetch_lmsys_extra(*, max_rows: int) -> Path:
    """Extra LMSYS slice (summarize yield is highest here historically)."""
    from datasets import load_dataset

    out = RAW / "lmsys" / "lmsys_sample_extra.jsonl"
    print("streaming lmsys/lmsys-chat-1m …")
    ds = load_dataset("lmsys/lmsys-chat-1m", split="train", streaming=True)
    rows: list[dict] = []
    for i, ex in enumerate(ds):
        if i >= max_rows:
            break
        # Keep first user turn
        conv = ex.get("conversation") or ex.get("conversations") or []
        text = None
        if isinstance(conv, list):
            for turn in conv:
                if isinstance(turn, dict):
                    role = (turn.get("role") or turn.get("from") or "").lower()
                    if role in {"user", "human"}:
                        text = turn.get("content") or turn.get("value")
                        break
                elif isinstance(turn, str) and turn.strip():
                    text = turn
                    break
        if isinstance(text, str) and text.strip():
            rows.append({"human": text.strip()[:500]})
        if (i + 1) % 5000 == 0:
            print(f"  … {i + 1}")
    _write_jsonl(out, rows)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        choices=("sharegpt", "moss", "lmsys", "all"),
        default="all",
    )
    ap.add_argument("--max-rows", type=int, default=50000)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    if args.source in ("moss", "all"):
        fetch_moss(max_rows=args.max_rows)
    if args.source in ("sharegpt", "all"):
        fetch_sharegpt(max_rows=args.max_rows)
    if args.source in ("lmsys", "all"):
        fetch_lmsys_extra(max_rows=args.max_rows)

    print("Done. Inspect sizes, then remine:")
    print("  wc -l workloads/phase6/raw_datasets/*/*.jsonl")
    print("  PYTHONPATH=. python -m src.eval.mine_phrasings --write")
    print("  cat workloads/phase6/phrasings_coverage.md")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fetch sample ShareGPT / MOSS dumps for Phase 6 phrasing mining.

Writes under workloads/phase6/raw_datasets/{sharegpt,moss}/.
LMSYS is assumed already present (lmsys_sample.jsonl from earlier mine).

Does NOT invent phrasings — only downloads public chat dumps for mine_phrasings.

  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source sharegpt --max-rows 20000
  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source moss --max-rows 20000
  PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source all --max-rows 20000

Requires: pip install datasets  (and network / HF cache on Aire).
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


def fetch_sharegpt(*, max_rows: int) -> Path:
    """
    Try common HF ShareGPT-style datasets; keep first-user turns as JSONL.
    """
    from datasets import load_dataset

    out = RAW / "sharegpt" / "sharegpt_sample.jsonl"
    candidates = [
        ("Aeala/ShareGPT_Vicuna_unfiltered", None),
        ("anon8231489123/ShareGPT_Vicuna_unfiltered", "json"),
        ("shareAI/ShareGPT-Chinese-English-New", None),
    ]
    last_err: Exception | None = None
    for name, fmt in candidates:
        try:
            print(f"trying ShareGPT dataset: {name} …")
            kwargs = {"split": "train", "streaming": True}
            if fmt:
                ds = load_dataset(name, fmt, **kwargs)
            else:
                ds = load_dataset(name, **kwargs)
            rows: list[dict] = []
            for i, ex in enumerate(ds):
                if i >= max_rows:
                    break
                # Normalise to a shape mine_phrasings understands
                if "conversations" in ex:
                    rows.append({"conversations": ex["conversations"]})
                elif "conversation" in ex:
                    rows.append({"conversations": ex["conversation"]})
                elif "text" in ex and isinstance(ex["text"], str):
                    rows.append({"human": ex["text"][:500]})
                else:
                    rows.append(dict(ex))
                if (i + 1) % 2000 == 0:
                    print(f"  … {i + 1} rows")
            if rows:
                _write_jsonl(out, rows)
                return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  failed: {exc}")
            continue
    raise RuntimeError(f"ShareGPT fetch failed; last error: {last_err}")


def fetch_moss(*, max_rows: int) -> Path:
    """Stream MOSS SFT-style data; keep user/human fields."""
    from datasets import load_dataset

    out = RAW / "moss" / "moss_sample.jsonl"
    candidates = [
        ("fnlp/moss-003-sft-data", None),
        ("OpenMOSS/moss-003-sft-data", None),
    ]
    last_err: Exception | None = None
    for name, _fmt in candidates:
        try:
            print(f"trying MOSS dataset: {name} …")
            ds = load_dataset(name, split="train", streaming=True)
            rows: list[dict] = []
            for i, ex in enumerate(ds):
                if i >= max_rows:
                    break
                # Common MOSS fields: conversation / chat / human
                if "conversation" in ex:
                    rows.append({"conversations": ex["conversation"]})
                elif "conversations" in ex:
                    rows.append({"conversations": ex["conversations"]})
                elif "human" in ex:
                    rows.append({"human": str(ex["human"])[:500]})
                elif "query" in ex:
                    rows.append({"query": str(ex["query"])[:500]})
                else:
                    rows.append(dict(ex))
                if (i + 1) % 2000 == 0:
                    print(f"  … {i + 1} rows")
            if rows:
                _write_jsonl(out, rows)
                return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  failed: {exc}")
            continue
    raise RuntimeError(f"MOSS fetch failed; last error: {last_err}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        choices=("sharegpt", "moss", "all"),
        default="all",
    )
    ap.add_argument("--max-rows", type=int, default=20000)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    if args.source in ("sharegpt", "all"):
        fetch_sharegpt(max_rows=args.max_rows)
    if args.source in ("moss", "all"):
        fetch_moss(max_rows=args.max_rows)
    print("Done. Next:")
    print("  PYTHONPATH=. python -m src.eval.mine_phrasings --write")
    print("  PYTHONPATH=. python -m src.eval.build_adversarial_semantic --limit 400 \\")
    print("      --out workloads/phase6/adversarial_semantic_multi.jsonl")


if __name__ == "__main__":
    main()

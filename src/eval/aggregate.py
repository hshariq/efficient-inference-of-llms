#!/usr/bin/env python3
"""
Aggregate Phase 6 run summaries into dissertation-ready tables.

  PYTHONPATH=. python -m src.eval.aggregate --summaries results/phase6/*.summary.json
  PYTHONPATH=. python -m src.eval.aggregate --jsonl results/phase6/c1_apc.jsonl \\
      results/phase6/c1_optimizer_hold.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "phase6"
TIERS = ("exact", "semantic", "best_of_n", "lone_wolf")


def _tsr(saved: float, processed: float) -> float:
    return (saved / processed) if processed else 0.0


def _write_table(path: Path, rows: list[dict], cols: list[str], title: str) -> None:
    lines = [
        title,
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _aggregate_summaries(paths: list[str], out_dir: Path) -> None:
    rows = []
    for p in paths:
        s = json.loads(Path(p).read_text(encoding="utf-8"))
        rows.append(
            {
                "system": s.get("system"),
                "n": s.get("n"),
                "n_ok": s.get("n_ok"),
                "tsr": s.get("tsr"),
                "hit_rate": s.get("hit_rate"),
                "mean_ttft_ms": s.get("mean_ttft_ms"),
                "p50_latency_ms": s.get("p50_latency_ms"),
                "p90_latency_ms": s.get("p90_latency_ms"),
                "p99_latency_ms": s.get("p99_latency_ms"),
                "throughput_gen_tok_s": s.get("throughput_gen_tok_s"),
                "prompt_tokens": s.get("prompt_tokens"),
                "cached_tokens": s.get("cached_tokens"),
                "concurrency": s.get("concurrency"),
                "workload": s.get("workload"),
            }
        )
    if not rows:
        return
    cols = list(rows[0].keys())
    _write_table(out_dir / "aggregate_table.md", rows, cols, "# Phase 6 aggregate results")
    csv_path = out_dir / "aggregate_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_dir / 'aggregate_table.md'}")
    print(f"wrote {csv_path}")


def _per_tier_from_jsonl(paths: list[str], out_dir: Path) -> None:
    """Break TSR out by workload tier — required for Optimizer vs APC claims."""
    rows: list[dict] = []
    for p in paths:
        path = Path(p)
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not records:
            continue
        system = records[0].get("system") or path.stem
        by: dict[str, dict[str, float]] = defaultdict(
            lambda: {"n": 0, "prompt_tokens": 0, "cached_tokens": 0}
        )
        for r in records:
            tier = r.get("tier") or "unknown"
            by[tier]["n"] += 1
            by[tier]["prompt_tokens"] += int(r.get("prompt_tokens") or 0)
            by[tier]["cached_tokens"] += int(r.get("cached_tokens") or 0)
        total_p = sum(v["prompt_tokens"] for v in by.values())
        total_c = sum(v["cached_tokens"] for v in by.values())
        row: dict = {
            "system": system,
            "source": path.name,
            "n": sum(int(v["n"]) for v in by.values()),
            "tsr_aggregate": round(_tsr(total_c, total_p), 6),
        }
        for tier in TIERS:
            v = by.get(tier, {"n": 0, "prompt_tokens": 0, "cached_tokens": 0})
            row[f"n_{tier}"] = int(v["n"])
            row[f"tsr_{tier}"] = round(
                _tsr(v["cached_tokens"], v["prompt_tokens"]), 6
            )
        rows.append(row)

    if not rows:
        return
    cols = list(rows[0].keys())
    _write_table(
        out_dir / "aggregate_per_tier.md",
        rows,
        cols,
        "# Phase 6 per-tier TSR (from JSONL)",
    )
    csv_path = out_dir / "aggregate_per_tier.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_dir / 'aggregate_per_tier.md'}")
    print(f"wrote {csv_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--summaries",
        nargs="*",
        default=[],
        help="*.summary.json files → aggregate_table.{md,csv}",
    )
    ap.add_argument(
        "--jsonl",
        nargs="*",
        default=[],
        help="Per-request JSONL files → aggregate_per_tier.{md,csv}",
    )
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    if not args.summaries and not args.jsonl:
        ap.error("provide --summaries and/or --jsonl")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.summaries:
        _aggregate_summaries(args.summaries, out_dir)
    if args.jsonl:
        _per_tier_from_jsonl(args.jsonl, out_dir)


if __name__ == "__main__":
    main()

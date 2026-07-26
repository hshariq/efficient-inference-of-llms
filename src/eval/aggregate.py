#!/usr/bin/env python3
"""
Aggregate Phase 6 run summaries into dissertation-ready tables.

  PYTHONPATH=. python -m src.eval.aggregate --summaries results/phase6/*.summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "phase6"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summaries", nargs="+", required=True)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in args.summaries:
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

    md_path = out_dir / "aggregate_table.md"
    cols = list(rows[0].keys()) if rows else []
    lines = [
        "# Phase 6 aggregate results",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = out_dir / "aggregate_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {md_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()

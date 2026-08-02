#!/usr/bin/env python3
"""
Aggregate Phase 6 run summaries into dissertation-ready tables.

  PYTHONPATH=. python -m src.eval.aggregate --summaries results/phase6/*.summary.json
  PYTHONPATH=. python -m src.eval.aggregate --jsonl results/phase6/c1_apc.jsonl \\
      results/phase6/c1_optimizer_hold.jsonl
  PYTHONPATH=. python -m src.eval.aggregate --probe-stats \\
      results/phase6/adv_sem_apc.jsonl results/phase6/adv_sem_optimizer.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "phase6"
TIERS = ("exact", "semantic", "best_of_n", "lone_wolf")


def _tsr(saved: float, processed: float) -> float:
    return (saved / processed) if processed else 0.0


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _hist_bins(ratios: list[float]) -> dict[str, int]:
    edges = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.01]
    labels = [
        "[0,0.05)",
        "[0.05,0.1)",
        "[0.1,0.2)",
        "[0.2,0.3)",
        "[0.3,0.5)",
        "[0.5,0.8)",
        "[0.8,1]",
    ]
    counts = {lab: 0 for lab in labels}
    for r in ratios:
        for i in range(len(edges) - 1):
            if edges[i] <= r < edges[i + 1] or (i == len(edges) - 2 and r <= 1.0):
                counts[labels[i]] += 1
                break
    return counts


def _bootstrap_tsr(
    prompt: list[int],
    cached: list[int],
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    """Token-weighted TSR bootstrap CI over requests (resample with replacement)."""
    n = len(prompt)
    if n == 0:
        return {"tsr": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n_boot": 0}
    point = _tsr(sum(cached), sum(prompt))
    rng = random.Random(seed)
    samples: list[float] = []
    idx = list(range(n))
    for _ in range(n_boot):
        draw = [rng.choice(idx) for _ in range(n)]
        samples.append(_tsr(sum(cached[i] for i in draw), sum(prompt[i] for i in draw)))
    samples.sort()
    return {
        "tsr": point,
        "ci_lo": _pct(samples, 0.025),
        "ci_hi": _pct(samples, 0.975),
        "n_boot": float(n_boot),
    }


def _probe_stats_from_jsonl(paths: list[str], out_dir: Path) -> None:
    """
    Per-request cached/prompt histogram + bootstrap TSR CI.
    Use for uniqueness probes (small n) before citing point TSR.
    """
    lines_out: list[str] = [
        "# Probe stats (ratio histogram + bootstrap TSR CI)",
        "",
        "TSR = sum(cached_tokens) / sum(prompt_tokens). "
        "CI = 95% bootstrap over requests (2000 resamples, seed=0).",
        "",
    ]
    boot_rows: list[dict] = []
    for p in paths:
        path = Path(p)
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        prompt = [int(r.get("prompt_tokens") or 0) for r in records]
        cached = [int(r.get("cached_tokens") or 0) for r in records]
        ratios = [
            (c / pt) if pt else 0.0 for c, pt in zip(cached, prompt, strict=True)
        ]
        ratios_sorted = sorted(ratios)
        boot = _bootstrap_tsr(prompt, cached)
        system = (records[0].get("system") if records else None) or path.stem
        hist = _hist_bins(ratios)
        boot_rows.append(
            {
                "system": system,
                "source": path.name,
                "n": len(records),
                "tsr": round(boot["tsr"], 6),
                "tsr_ci95_lo": round(boot["ci_lo"], 6),
                "tsr_ci95_hi": round(boot["ci_hi"], 6),
                "ratio_median": round(_pct(ratios_sorted, 0.5), 6),
                "ratio_p10": round(_pct(ratios_sorted, 0.1), 6),
                "ratio_p90": round(_pct(ratios_sorted, 0.9), 6),
            }
        )
        lines_out.append(f"## {system} (`{path.name}`)")
        lines_out.append("")
        lines_out.append(
            f"- n={len(records)}  TSR={boot['tsr']:.4f}  "
            f"95% CI [{boot['ci_lo']:.4f}, {boot['ci_hi']:.4f}]"
        )
        lines_out.append(
            f"- per-request ratio median={_pct(ratios_sorted, 0.5):.4f}  "
            f"p10={_pct(ratios_sorted, 0.1):.4f}  p90={_pct(ratios_sorted, 0.9):.4f}"
        )
        lines_out.append("- histogram `cached/prompt`:")
        for lab, cnt in hist.items():
            lines_out.append(f"  - {lab}: {cnt}")
        lines_out.append("")

    if len(boot_rows) == 2:
        # Difference CI via paired bootstrap on aligned lengths is wrong across systems;
        # report independent CIs and point delta only.
        a, b = boot_rows[0], boot_rows[1]
        delta = b["tsr"] - a["tsr"]
        lines_out.append("## Point delta (Optimizer − APC style)")
        lines_out.append("")
        lines_out.append(
            f"- {b['system']} − {a['system']} = **{delta:+.4f}** "
            f"(compare non-overlapping CIs qualitatively; not a paired test)"
        )
        lines_out.append("")

    out_md = out_dir / "probe_stats.md"
    out_md.write_text("\n".join(lines_out), encoding="utf-8")
    cols = list(boot_rows[0].keys()) if boot_rows else []
    if boot_rows:
        _write_table(
            out_dir / "probe_stats_table.md",
            boot_rows,
            cols,
            "# Probe TSR with 95% bootstrap CI",
        )
        csv_path = out_dir / "probe_stats.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(boot_rows)
        print(f"wrote {csv_path}")
    print(f"wrote {out_md}")
    print(json.dumps(boot_rows, indent=2))


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
    ap.add_argument(
        "--probe-stats",
        nargs="*",
        default=[],
        help="Per-request JSONL → ratio histogram + bootstrap TSR 95% CI",
    )
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    if not args.summaries and not args.jsonl and not args.probe_stats:
        ap.error("provide --summaries and/or --jsonl and/or --probe-stats")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.summaries:
        _aggregate_summaries(args.summaries, out_dir)
    if args.jsonl:
        _per_tier_from_jsonl(args.jsonl, out_dir)
    if args.probe_stats:
        _probe_stats_from_jsonl(args.probe_stats, out_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate Phase 6 dissertation charts (6 charts, mixed types).

  1 bar           — TSR by system                 (--summaries)
  2 grouped bar   — Hit rate vs TSR               (--summaries)
  3 line          — TTFT across load scenarios    (--ttft-c1 + --ttft-burst)
  4 box plot      — Latency distribution          (--jsonl burst runs)
  5 grouped bar   — Uniqueness probe TSR by n     (--uniqueness-summaries)
  6 scatter       — prompt tokens vs per-req TSR  (--jsonl)

Chart 5 used to be a SCALM-style stacked “semantic + TTL” breakdown; that
misattributes APC savings to rewrite and implies hold raises TSR (false on
this workload). Uniqueness scale-up replaces it.

Example:
  PYTHONPATH=. python -m src.eval.charts \\
    --summaries results/phase6/burst_*.summary.json \\
    --ttft-c1 results/phase6/c1_*.summary.json \\
    --ttft-burst results/phase6/burst_*.summary.json \\
    --uniqueness-summaries results/phase6/adv_sem*.summary.json \\
    --jsonl results/phase6/burst_*.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHART_DIR = ROOT / "results" / "phase6" / "charts"


def _load_summaries(paths: list[Path]) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def _load_jsonl(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _by_system(summaries: list[dict]) -> dict[str, dict]:
    return {str(s.get("system", "?")): s for s in summaries}


def _uniqueness_scale_chart(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bars: APC vs Optimizer TSR across uniqueness probe sizes → 05."""
    import matplotlib.pyplot as plt
    import numpy as np

    cells: dict[tuple[int, str], float] = {}
    for s in summaries:
        n = int(s.get("n") or 0)
        sys = str(s.get("system") or "?").lower()
        if sys.startswith("optimizer"):
            sys = "optimizer"
        if sys not in ("apc", "optimizer") or n <= 0:
            continue
        cells[(n, sys)] = float(s.get("tsr") or 0.0)

    ns = sorted({n for n, _ in cells})
    if len(ns) < 2:
        raise SystemExit(
            "uniqueness chart needs ≥2 probe sizes in --uniqueness-summaries "
            "(expected n≈83, 224, 556)"
        )

    apc = [cells.get((n, "apc"), 0.0) for n in ns]
    opt = [cells.get((n, "optimizer"), 0.0) for n in ns]
    x = np.arange(len(ns))
    w = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - w / 2, apc, w, label="APC")
    ax.bar(x + w / 2, opt, w, label="Optimizer")
    ax.set_xticks(x)
    ax.set_xticklabels([f"n={n}" for n in ns])
    ax.set_ylabel("TSR")
    ax.set_title("Uniqueness probes: TSR vs probe size")
    ax.set_ylim(0, max(0.4, max(apc + opt) * 1.15))
    ax.legend()
    fig.tight_layout()
    p = out_dir / "05_uniqueness_tsr_by_n.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    # Remove superseded stacked / old 07 filenames if present
    for stale in (
        out_dir / "05_ablation_stacked.png",
        out_dir / "07_uniqueness_tsr_by_n.png",
    ):
        if stale.exists():
            stale.unlink()
    return (
        f"{p.name}: Grouped bars of APC vs Optimizer TSR on uniqueness "
        f"probes (n={', '.join(str(n) for n in ns)}). Rewrite gap holds as "
        "unique mined instructions scale; not the main four-tier mix. "
        "Replaces the old stacked ‘semantic+TTL’ chart (hold does not raise TSR)."
    )


def generate(
    *,
    summaries: list[dict],
    ttft_c1: list[dict],
    ttft_burst: list[dict],
    uniqueness: list[dict],
    jsonl_rows: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise SystemExit("matplotlib required: pip install matplotlib") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    captions: list[str] = []

    systems = [s.get("system", "?") for s in summaries]
    tsr = [float(s.get("tsr") or 0) for s in summaries]
    hit = [float(s.get("hit_rate") or 0) for s in summaries]

    # --- 1 TSR bar ---
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(systems, tsr)
    ax.set_title("Token Saving Ratio by system")
    ax.set_ylabel("TSR")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    p = out_dir / "01_tsr_by_system.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    captions.append(
        f"{p.name}: Bar chart of TSR per system (primary metric). "
        "Not a TTFT comparison."
    )

    # --- 2 grouped bar hit vs TSR ---
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(systems))
    w = 0.35
    ax.bar(x - w / 2, hit, w, label="Hit rate")
    ax.bar(x + w / 2, tsr, w, label="TSR")
    ax.set_xticks(x)
    ax.set_xticklabels(systems, rotation=20)
    ax.set_title("Cache hit rate vs Token Saving Ratio")
    ax.legend()
    fig.tight_layout()
    p = out_dir / "02_hitrate_vs_tsr.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    captions.append(
        f"{p.name}: Grouped bars contrasting hit rate with TSR. "
        "APC/Optimizer hit_rate≈1.0 is a weak ‘any cache’ signal; GPTCache "
        "hit_rate is real answer-cache hits (SCALM vanity-metric argument)."
    )

    # --- 3 TTFT line across scenarios ---
    fig, ax = plt.subplots(figsize=(7, 4))
    c1_by = _by_system(ttft_c1)
    burst_by = _by_system(ttft_burst)
    line_systems = sorted(set(c1_by) | set(burst_by))
    xs = [0, 1]
    for sys in line_systems:
        y0 = float(c1_by.get(sys, {}).get("mean_ttft_ms") or 0.0)
        y1 = float(burst_by.get(sys, {}).get("mean_ttft_ms") or 0.0)
        ax.plot(xs, [y0, y1], marker="o", label=sys)
    ax.set_xticks(xs)
    ax.set_xticklabels(["concurrency=1", "burst"])
    ax.set_ylabel("Mean client-side TTFT (ms)")
    ax.set_title("TTFT across load scenarios (cost framing)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = out_dir / "03_ttft_across_scenarios.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    captions.append(
        f"{p.name}: Line chart of mean client-side TTFT from concurrency=1 to burst. "
        "Shows hold-mode latency cost under load; not framed as a speed win."
    )

    # --- 4 box plot latency ---
    fig, ax = plt.subplots(figsize=(8, 4))
    by_sys_lat: dict[str, list[float]] = defaultdict(list)
    for row in jsonl_rows:
        if row.get("disposition") == "error":
            continue
        sys = str(row.get("system") or "?")
        try:
            by_sys_lat[sys].append(float(row.get("latency_ms") or 0.0))
        except (TypeError, ValueError):
            continue
    labels = sorted(by_sys_lat)
    data = [by_sys_lat[k] for k in labels]
    if not data or all(len(d) == 0 for d in data):
        ax.text(0.5, 0.5, "No latency samples in --jsonl", ha="center", va="center")
        ax.set_axis_off()
    else:
        try:
            ax.boxplot(data, tick_labels=labels, showfliers=False)
        except TypeError:
            ax.boxplot(data, labels=labels, showfliers=False)
        ax.set_ylabel("Latency (ms)")
        ax.set_title("Latency distribution by system (burst)")
        ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    p = out_dir / "04_latency_boxplot.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    captions.append(
        f"{p.name}: Box plot of per-request latency (burst JSONL). "
        "Supports TTL/starvation tail-latency discussion better than three adjacent bars."
    )

    # --- 5 uniqueness scale (replaces stacked semantic+TTL) ---
    captions.append(_uniqueness_scale_chart(uniqueness, out_dir))

    # --- 6 scatter prompt tokens vs per-request TSR ---
    fig, ax = plt.subplots(figsize=(7, 4))
    by_sys_pts: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in jsonl_rows:
        if row.get("disposition") == "error":
            continue
        pt = float(row.get("prompt_tokens") or 0)
        ct = float(row.get("cached_tokens") or 0)
        if pt <= 0:
            continue
        by_sys_pts[str(row.get("system") or "?")].append((pt, ct / pt))
    plotted = False
    for sys, pts in sorted(by_sys_pts.items()):
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.scatter(xs, ys, s=12, alpha=0.5, label=sys)
        plotted = True
    if not plotted:
        ax.text(0.5, 0.5, "No token samples in --jsonl", ha="center", va="center")
        ax.set_axis_off()
    else:
        ax.set_xlabel("Prompt tokens (per request)")
        ax.set_ylabel("Per-request TSR (cached/prompt)")
        ax.set_title("TSR vs document/prompt size")
        ax.legend(fontsize=8, markerscale=2)
    fig.tight_layout()
    p = out_dir / "06_tsr_vs_prompt_tokens.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    captions.append(
        f"{p.name}: Scatter of per-request TSR vs prompt tokens, coloured by system. "
        "Visualises whether savings scale with document size (Phase 4 finding)."
    )

    cap_path = out_dir / "captions.txt"
    cap_path.write_text("\n\n".join(captions) + "\n", encoding="utf-8")
    print(f"wrote charts -> {out_dir}")
    print(f"captions -> {cap_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--summaries",
        nargs="+",
        required=True,
        help="Main system summaries for charts 1-2 (typically burst)",
    )
    ap.add_argument(
        "--ttft-c1",
        nargs="+",
        required=True,
        help="Concurrency=1 summaries (chart 3 left point), one per system",
    )
    ap.add_argument(
        "--ttft-burst",
        nargs="+",
        required=True,
        help="Burst summaries (chart 3 right point), one per system",
    )
    ap.add_argument(
        "--uniqueness-summaries",
        nargs="+",
        required=True,
        help="APC/Optimizer uniqueness probe summaries → chart 5 "
        "(adv_sem / multi / xl)",
    )
    ap.add_argument(
        "--jsonl",
        nargs="+",
        required=True,
        help="Per-request JSONL files for box plot (4) and scatter (6)",
    )
    ap.add_argument(
        "--ablation-summaries",
        nargs="*",
        default=[],
        help="Deprecated/ignored (old stacked chart 5 removed)",
    )
    ap.add_argument("--out-dir", default=str(CHART_DIR))
    args = ap.parse_args()

    generate(
        summaries=_load_summaries([Path(s) for s in args.summaries]),
        ttft_c1=_load_summaries([Path(s) for s in args.ttft_c1]),
        ttft_burst=_load_summaries([Path(s) for s in args.ttft_burst]),
        uniqueness=_load_summaries([Path(s) for s in args.uniqueness_summaries]),
        jsonl_rows=_load_jsonl([Path(s) for s in args.jsonl]),
        out_dir=Path(args.out_dir),
    )


if __name__ == "__main__":
    main()

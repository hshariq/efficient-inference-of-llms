#!/usr/bin/env python3
"""
Generate Phase 6 dissertation charts (6 charts, mixed types).

  1 bar           — TSR by system                 (--summaries)
  2 grouped bar   — Hit rate vs TSR               (--summaries)
  3 line          — TTFT across load scenarios    (--ttft-c1 + --ttft-burst)
  4 box plot      — Latency distribution          (--jsonl burst runs)
  5 grouped bar   — Uniqueness probe TSR by n     (--uniqueness-summaries)
  6 histograms    — Per-request TSR distribution  (--jsonl)

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
    # Only plot systems present in BOTH inputs. Missing side used to default to
    # 0 ms and draw fake cliffs (e.g. optimizer only in burst, hold only in c=1).
    fig, ax = plt.subplots(figsize=(7, 4))
    c1_by = _by_system(ttft_c1)
    burst_by = _by_system(ttft_burst)
    line_systems = sorted(set(c1_by) & set(burst_by))
    skipped = sorted((set(c1_by) | set(burst_by)) - set(line_systems))
    if skipped:
        print(
            "WARN: chart 03 skipped systems missing c=1 or burst TTFT: "
            + ", ".join(skipped)
        )
    xs = [0, 1]
    for sys in line_systems:
        y0 = float(c1_by[sys].get("mean_ttft_ms") or 0.0)
        y1 = float(burst_by[sys].get("mean_ttft_ms") or 0.0)
        ax.plot(xs, [y0, y1], marker="o", label=sys)
    if not line_systems:
        ax.text(
            0.5,
            0.5,
            "No systems with both c=1 and burst TTFT",
            ha="center",
            va="center",
        )
        ax.set_axis_off()
    else:
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
        f"{p.name}: Line chart of mean client-side TTFT from concurrency=1 to burst "
        "(systems with both endpoints only). Cost framing under load — not a speed win. "
        "Hold cost: compare optimizer vs optimizer_hold when both pairs are supplied."
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

    # --- 6 per-request TSR distribution (replaces crowded size scatter) ---
    by_sys_ratio: dict[str, list[float]] = defaultdict(list)
    for row in jsonl_rows:
        if row.get("disposition") == "error":
            continue
        pt = float(row.get("prompt_tokens") or 0)
        ct = float(row.get("cached_tokens") or 0)
        if pt <= 0:
            continue
        by_sys_ratio[str(row.get("system") or "?")].append(ct / pt)

    systems_r = sorted(by_sys_ratio)
    if not systems_r:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.text(0.5, 0.5, "No token samples in --jsonl", ha="center", va="center")
        ax.set_axis_off()
        p = out_dir / "06_tsr_distribution.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
    else:
        n = len(systems_r)
        ncols = 3 if n >= 3 else n
        nrows = int(np.ceil(n / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.2 * nrows), sharex=True)
        flat = np.atleast_1d(axes).ravel()
        bins = np.linspace(0.0, 1.0, 21)
        for ax, sys in zip(flat, systems_r):
            vals = by_sys_ratio[sys]
            ax.hist(vals, bins=bins, color="C0", edgecolor="white", linewidth=0.4)
            ax.axvline(float(np.median(vals)), color="C3", linestyle="--", linewidth=1.2, label="median")
            ax.set_title(sys, fontsize=10)
            ax.set_xlim(0.0, 1.0)
            ax.set_ylabel("requests")
        for ax in flat[len(systems_r) :]:
            ax.set_axis_off()
        for ax in flat[: len(systems_r)]:
            ax.set_xlabel("Per-request TSR (cached/prompt)")
        # one legend on first panel
        flat[0].legend(fontsize=8, loc="upper right")
        fig.suptitle("Per-request TSR distribution by system (burst)", fontsize=12, y=1.01)
        fig.tight_layout()
        p = out_dir / "06_tsr_distribution.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)

    stale_scatter = out_dir / "06_tsr_vs_prompt_tokens.png"
    if stale_scatter.exists():
        stale_scatter.unlink()

    captions.append(
        f"{p.name}: Faceted histograms of per-request TSR (cached/prompt) by system. "
        "Shows the real shape of savings — often bimodal (near-miss crumbs vs near-full "
        "exact re-use) — clearer than a multi-system size scatter. Dashed = median."
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
        help="Per-request JSONL files for box plot (4) and TSR histograms (6)",
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

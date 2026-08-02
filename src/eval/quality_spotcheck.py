#!/usr/bin/env python3
"""
Output quality spot-check: compare Optimizer Box outputs to vanilla on same prompts.

Stratifies by tier (exact / semantic / best_of_n / lone_wolf) so alphabetical
req_id order does not collapse the sample onto one tier (e.g. all bon-*).

  PYTHONPATH=. python -m src.eval.quality_spotcheck \
    --vanilla results/phase6/burst_vanilla.jsonl \
    --optimizer results/phase6/burst_optimizer_holdoff_embedoff.jsonl \
    --limit 12
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

TIERS = ("exact", "semantic", "best_of_n", "lone_wolf")


def _load(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            out[row["req_id"]] = row
    return out


def _stratified_ids(
    vanilla: dict[str, dict],
    optimizer: dict[str, dict],
    *,
    limit: int,
) -> list[str]:
    """Round-robin across tiers among shared req_ids (stable sort within tier)."""
    by_tier: dict[str, list[str]] = defaultdict(list)
    for rid in sorted(set(vanilla) & set(optimizer)):
        tier = (vanilla[rid].get("tier") or "unknown").strip()
        by_tier[tier].append(rid)

    order = [t for t in TIERS if by_tier.get(t)] + sorted(
        t for t in by_tier if t not in TIERS
    )
    picked: list[str] = []
    while len(picked) < limit and any(by_tier[t] for t in order):
        for t in order:
            if by_tier[t] and len(picked) < limit:
                picked.append(by_tier[t].pop(0))
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vanilla", required=True)
    ap.add_argument("--optimizer", required=True)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--out", default="results/phase6/quality_spotcheck.md")
    args = ap.parse_args()

    v = _load(Path(args.vanilla))
    o = _load(Path(args.optimizer))
    common = _stratified_ids(v, o, limit=max(1, args.limit))

    tier_counts: dict[str, int] = defaultdict(int)
    for rid in common:
        tier_counts[str(v[rid].get("tier") or "unknown")] += 1

    lines = [
        "# Phase 6 — quality spot-check",
        "",
        "Sampled side-by-side previews (stratified by tier). Goal: confirm",
        "canonical-prefix rewriting does not change task meaning",
        "(not a formal BLEU/ROUGE study).",
        "",
        f"Sample mix: {dict(tier_counts)}",
        "",
    ]
    for rid in common:
        lines.append(f"## {rid} (tier={v[rid].get('tier')})")
        lines.append("")
        lines.append(f"- task: `{v[rid].get('task')}`")
        lines.append(f"- vanilla: {(v[rid].get('output_preview') or '')[:300]}")
        lines.append(f"- optimizer: {(o[rid].get('output_preview') or '')[:300]}")
        lines.append(
            f"- optimizer rewrite={o[rid].get('rewrite')} "
            f"catalogue_task={o[rid].get('catalogue_task')}"
        )
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(common)} samples) tiers={dict(tier_counts)}")


if __name__ == "__main__":
    main()

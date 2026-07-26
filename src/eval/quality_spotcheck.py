#!/usr/bin/env python3
"""
Output quality spot-check: compare Optimizer Box outputs to vanilla on same prompts.

  PYTHONPATH=. python -m src.eval.quality_spotcheck \
    --vanilla results/phase6/run_vanilla.jsonl \
    --optimizer results/phase6/run_optimizer.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            out[row["req_id"]] = row
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vanilla", required=True)
    ap.add_argument("--optimizer", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default="results/phase6/quality_spotcheck.md")
    args = ap.parse_args()

    v = _load(Path(args.vanilla))
    o = _load(Path(args.optimizer))
    common = sorted(set(v) & set(o))[: args.limit]

    lines = [
        "# Phase 6 — quality spot-check",
        "",
        "Sampled side-by-side previews. Goal: confirm canonical-prefix rewriting",
        "does not change task meaning (not a formal BLEU/ROUGE study).",
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
    print(f"wrote {out} ({len(common)} samples)")


if __name__ == "__main__":
    main()

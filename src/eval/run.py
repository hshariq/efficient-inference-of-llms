"""CLI entry: python -m src.eval.run ..."""

from __future__ import annotations

import argparse
import json
import sys

from src.eval.config import SYSTEMS, EvalConfig
from src.eval.runner import run_eval


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 6 evaluation harness")
    p.add_argument("--system", required=True, choices=SYSTEMS)
    p.add_argument(
        "--workload",
        default="workloads/phase6/smoke_tiny.jsonl",
        help="JSONL workload path",
    )
    p.add_argument("--out", default=None, help="Output JSONL path")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--base-url", default=None)
    p.add_argument("--max-tokens", type=int, default=64)
    p.add_argument(
        "--skip-cached-tokens-gate",
        action="store_true",
        help="DANGEROUS: skip probe_cached_tokens hard gate (allows silent TSR=0)",
    )
    args = p.parse_args(argv)

    cfg = EvalConfig.from_args(
        system=args.system,
        workload=args.workload,
        out=args.out,
        concurrency=args.concurrency,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        skip_cached_tokens_gate=args.skip_cached_tokens_gate,
    )
    print(
        f"system={cfg.system} base_url={cfg.base_url} "
        f"workload={cfg.workload_path} concurrency={cfg.concurrency}"
    )
    try:
        summary = run_eval(cfg)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    if summary.get("mode_mismatch") or summary.get("cached_tokens_gate_skipped"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

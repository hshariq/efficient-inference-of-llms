#!/usr/bin/env python3
"""
Phase 4 — 4-way tagging ablation harness.

Conditions:
  1. rules_only          — Part 1 fields, no Part 2, no embed
  2. rules_plus_features — Part 1 + Part 2 metadata, no embed
  3. embed_minilm        — (2) + MiniLM fallback on low-confidence/UNKNOWN
  4. embed_qwen3         — (2) + Qwen3-Embedding-0.6B fallback

Per-request detail (default on): prints INPUT / OUTPUT tags / METRICS for each
prompt. Use --quiet for aggregate-only, --limit N to sample, --jsonl FILE to save.

Example (Aire GPU node, after pip install sentence-transformers):
  python -m src.proxy.ablation.run_tag_ablation --conditions rules_only
  python -m src.proxy.ablation.run_tag_ablation --conditions embed_minilm --limit 5
  python -m src.proxy.ablation.run_tag_ablation --write-log
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.proxy.ablation.fixtures import (
    ACTION_ANALYSIS,
    ACTION_GENERATION,
    ACTION_RETRIEVAL,
    ENTITY_FOCUS_INDIVIDUAL,
    ENTITY_FOCUS_TEAM,
    EXCLUSION_PAIRS,
    SUMMARIZE_PARAPHRASES,
)
from src.proxy.rewrite.embed.factory import clear_backend_cache, get_embedding_backend
from src.proxy.rewrite.tagging import AblationCondition, TagConfig, tag_with_timing

ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = ROOT / "docs" / "PHASE4_DECISIONS_LOG.md"

CONDITIONS: list[AblationCondition] = [
    "rules_only",
    "rules_plus_features",
    "embed_minilm",
    "embed_qwen3",
]


def build_request_set() -> list[str]:
    reqs: list[str] = []
    reqs.extend(SUMMARIZE_PARAPHRASES)
    reqs.extend(ENTITY_FOCUS_TEAM)
    reqs.extend(ENTITY_FOCUS_INDIVIDUAL)
    reqs.extend(ACTION_ANALYSIS)
    reqs.extend(ACTION_RETRIEVAL)
    reqs.extend(ACTION_GENERATION)
    for base, with_excl, _ in EXCLUSION_PAIRS:
        reqs.append(base)
        reqs.append(with_excl)
    seen: set[str] = set()
    out: list[str] = []
    for r in reqs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


@dataclass
class ConditionStats:
    condition: str
    n: int
    bypass_rate: float
    mean_rule_ms: float
    mean_embed_ms: float
    embed_used_rate: float
    vram_bytes: int | None


def _print_case(
    condition: str,
    index: int,
    total: int,
    text: str,
    result,
) -> None:
    tags = result.tags
    print(f"\n----- [{condition}] case {index}/{total} -----")
    print("INPUT:")
    print(text)
    print("OUTPUT (tags):")
    print(
        f"  task={tags.task.value}  domain={tags.domain.value}  "
        f"confidence={tags.confidence:.3f}  length_class={tags.length_class.value}"
    )
    print(
        f"  entity_focus={tags.entity_focus.value}  "
        f"action_type={tags.action_type.value}  "
        f"excluded_terms={list(tags.excluded_terms)}"
    )
    print("METRICS:")
    print(
        f"  rule_ms={result.rule_ms:.2f}  embed_ms={result.embed_ms:.2f}  "
        f"embed_used={result.embed_used}  embed_backend={result.embed_backend}  "
        f"embed_score={result.embed_score}  would_bypass={result.would_bypass}"
    )


def run_condition(
    condition: AblationCondition,
    requests: list[str],
    *,
    verbose: bool,
    jsonl_path: Path | None,
) -> ConditionStats:
    clear_backend_cache()
    cfg = TagConfig.for_ablation(condition)
    vram: int | None = None
    if cfg.embedding_backend not in ("off", "none", "", "false", "0"):
        backend = get_embedding_backend(cfg.embedding_backend)
        if backend is not None:
            t_load = time.perf_counter()
            backend.load()
            load_ms = (time.perf_counter() - t_load) * 1000.0
            print(f"  [{condition}] loaded {backend.model_id} in {load_ms:.0f} ms")
            vram = backend.vram_bytes()

    bypass = 0
    rule_ms: list[float] = []
    embed_ms: list[float] = []
    embed_used = 0
    jsonl_fh = jsonl_path.open("a", encoding="utf-8") if jsonl_path else None
    try:
        n_req = len(requests)
        for i, text in enumerate(requests, start=1):
            result = tag_with_timing(text, cfg)
            rule_ms.append(result.rule_ms)
            embed_ms.append(result.embed_ms)
            if result.would_bypass:
                bypass += 1
            if result.embed_used:
                embed_used += 1
            if verbose:
                _print_case(condition, i, n_req, text, result)
            if jsonl_fh is not None:
                rec = {
                    "condition": condition,
                    "index": i,
                    "input": text,
                    "output": {
                        "task": result.tags.task.value,
                        "domain": result.tags.domain.value,
                        "confidence": result.tags.confidence,
                        "length_class": result.tags.length_class.value,
                        "entity_focus": result.tags.entity_focus.value,
                        "action_type": result.tags.action_type.value,
                        "excluded_terms": list(result.tags.excluded_terms),
                    },
                    "metrics": {
                        "rule_ms": result.rule_ms,
                        "embed_ms": result.embed_ms,
                        "embed_used": result.embed_used,
                        "embed_backend": result.embed_backend,
                        "embed_score": result.embed_score,
                        "would_bypass": result.would_bypass,
                    },
                }
                jsonl_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    finally:
        if jsonl_fh is not None:
            jsonl_fh.close()

    n = len(requests)
    return ConditionStats(
        condition=condition,
        n=n,
        bypass_rate=bypass / n if n else 0.0,
        mean_rule_ms=statistics.fmean(rule_ms) if rule_ms else 0.0,
        mean_embed_ms=statistics.fmean(embed_ms) if embed_ms else 0.0,
        embed_used_rate=embed_used / n if n else 0.0,
        vram_bytes=vram,
    )


def format_report(stats: list[ConditionStats]) -> str:
    lines = [
        "",
        f"## Part 4 — Ablation results ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        "",
        "Shared request set = Part 2 coverage assets + summarize paraphrases "
        f"(n={stats[0].n if stats else 0}). Latencies are **mean ms**, "
        "rule vs embed reported separately. VRAM is process `torch.cuda.memory_allocated` "
        "after backend load (None = CPU / unavailable).",
        "",
        "| Condition | Bypass rate | Mean rule_ms | Mean embed_ms | Embed-used rate | VRAM |",
        "|-----------|-------------|--------------|---------------|-----------------|------|",
    ]
    for s in stats:
        vram = f"{s.vram_bytes / (1024**2):.0f} MiB" if s.vram_bytes is not None else "n/a"
        lines.append(
            f"| `{s.condition}` | {100 * s.bypass_rate:.1f}% | "
            f"{s.mean_rule_ms:.2f} | {s.mean_embed_ms:.2f} | "
            f"{100 * s.embed_used_rate:.1f}% | {vram} |"
        )
    lines.extend(
        [
            "",
            "**Notes:** Warm TTFT / Token Saving Ratio need live vLLM+APC "
            "(`smoke_rewrite_apc.py` / Phase 6) and are not duplicated here — "
            "tagging ablation isolates classifier behaviour only.",
            "",
            "### Decisions / caveats from this run",
            "",
            "- Embeddings used only when rules return UNKNOWN or confidence below threshold.",
            "- Qwen3-Embedding-0.6B VRAM must be read against vLLM "
            "`--gpu-memory-utilization 0.90` on L40S; if contention appears, "
            "set `OPTIMIZER_EMBED_DEVICE=cpu` for the proxy process.",
            "- Catalogue still keyed by Task only; Part 2 fields remain metadata.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--conditions",
        default="rules_only,rules_plus_features,embed_minilm,embed_qwen3",
        help="Comma-separated ablation conditions",
    )
    parser.add_argument(
        "--write-log",
        action="store_true",
        help=f"Append markdown aggregate results to {LOG_PATH}",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Only run rules_only + rules_plus_features (no model download)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Aggregate summary only (no per-request INPUT/OUTPUT/METRICS)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only first N requests (0 = all). Useful for a quick verbose smoke.",
    )
    parser.add_argument(
        "--jsonl",
        type=str,
        default="",
        help="Append per-request records as JSONL to this path",
    )
    args = parser.parse_args()

    conditions: list[AblationCondition] = []
    for raw in args.conditions.split(","):
        c = raw.strip()
        if not c:
            continue
        if args.skip_embed and c.startswith("embed_"):
            continue
        if c not in CONDITIONS:
            raise SystemExit(f"Unknown condition {c!r}; choose from {CONDITIONS}")
        conditions.append(c)  # type: ignore[arg-type]

    requests = build_request_set()
    if args.limit and args.limit > 0:
        requests = requests[: args.limit]

    verbose = not args.quiet
    jsonl_path = Path(args.jsonl) if args.jsonl else None
    if jsonl_path is not None:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Ablation request set size: {len(requests)}")
    print(f"Conditions: {conditions}")
    print(f"Per-request detail: {'ON' if verbose else 'OFF (--quiet)'}")

    all_stats: list[ConditionStats] = []
    for cond in conditions:
        print(f"\n========== CONDITION: {cond} ==========")
        try:
            stats = run_condition(
                cond,
                requests,
                verbose=verbose,
                jsonl_path=jsonl_path,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            continue
        all_stats.append(stats)
        print(f"\n--- aggregate [{cond}] ---")
        print(
            f"  bypass={100 * stats.bypass_rate:.1f}%  "
            f"mean_rule_ms={stats.mean_rule_ms:.2f}  mean_embed_ms={stats.mean_embed_ms:.2f}  "
            f"embed_used={100 * stats.embed_used_rate:.1f}%"
        )
        if stats.vram_bytes is not None:
            print(f"  vram_allocated≈{stats.vram_bytes / (1024**2):.0f} MiB")

    report = format_report(all_stats)
    print(report)
    if args.write_log and all_stats:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Appended results to {LOG_PATH}")


if __name__ == "__main__":
    main()

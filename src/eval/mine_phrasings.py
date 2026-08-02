#!/usr/bin/env python3
"""
Mine real user phrasings from ShareGPT / LMSYS-Chat-1M / MOSS for Phase 6.

Hard rule: do NOT invent paraphrases. If search yields insufficient coverage,
write a gap note to docs/PHASE6_DECISIONS_LOG.md (printed here; paste/update).

This script searches locally cached JSON/JSONL dumps if present under
workloads/phase6/raw_datasets/, or HuggingFace datasets if installed.

  PYTHONPATH=. python -m src.eval.mine_phrasings --dry-run
  PYTHONPATH=. python -m src.eval.mine_phrasings --write

Expected raw layout (any subset):
  workloads/phase6/raw_datasets/sharegpt/*.json
  workloads/phase6/raw_datasets/lmsys/*.jsonl
  workloads/phase6/raw_datasets/moss/*.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "workloads" / "phase6" / "raw_datasets"
OUT = ROOT / "workloads" / "phase6" / "phrasings"

SUMMARIZE_RE = re.compile(
    r"\b(summariz|summaris|summary|bullet\s*points?|key\s+points?|3\s*bullets?|three\s+bullets?)\b",
    re.I,
)
ENTITY_RE = re.compile(
    r"\b(extract|named\s+entities|entities|entity\s+extraction)\b", re.I,
)
# Lone wolf: short chatty asks that are clearly not catalogue tasks
LONE_EXCLUDE = re.compile(
    r"\b(summariz|summaris|extract|entities|bullet|handbook|module|assessment)\b",
    re.I,
)


def _iter_texts() -> list[tuple[str, str, str]]:
    """Yield (source, mine_id, text) from local raw dumps."""
    out: list[tuple[str, str, str]] = []
    if not RAW.exists():
        return out

    for p in RAW.joinpath("sharegpt").glob("**/*") if (RAW / "sharegpt").exists() else []:
        if p.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            if p.suffix == ".jsonl":
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines()):
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    text = _extract_human(obj)
                    if text:
                        out.append(("sharegpt", f"{p.name}:{i}", text))
            else:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, list):
                    for i, obj in enumerate(data):
                        text = _extract_human(obj)
                        if text:
                            out.append(("sharegpt", f"{p.name}:{i}", text))
        except Exception:  # noqa: BLE001
            continue

    for sub, source in (("lmsys", "lmsys"), ("moss", "moss")):
        d = RAW / sub
        if not d.exists():
            continue
        for p in d.glob("**/*"):
            if p.suffix.lower() not in {".json", ".jsonl", ".txt"}:
                continue
            try:
                if p.suffix == ".txt":
                    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines()):
                        if line.strip():
                            out.append((source, f"{p.name}:{i}", line.strip()[:500]))
                elif p.suffix == ".jsonl":
                    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines()):
                        if not line.strip():
                            continue
                        obj = json.loads(line)
                        text = _extract_human(obj)
                        if text:
                            out.append((source, f"{p.name}:{i}", text))
            except Exception:  # noqa: BLE001
                continue
    return out


def _extract_human(obj: object) -> str | None:
    if isinstance(obj, str):
        return obj.strip()[:500] or None
    if not isinstance(obj, dict):
        return None
    for key in ("human", "user", "query", "prompt", "text", "content"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:500]
    # ShareGPT / MOSS conversations (possibly JSON-string nested)
    conv = obj.get("conversations") or obj.get("conversation") or obj.get("chat")
    if isinstance(conv, str) and conv.strip().startswith(("[", "{")):
        try:
            conv = json.loads(conv)
        except json.JSONDecodeError:
            conv = None
    if isinstance(conv, list):
        for turn in conv:
            if isinstance(turn, str) and turn.strip():
                return turn.strip()[:500]
            if not isinstance(turn, dict):
                continue
            # MOSS YeungNLP: {"human": "...", "assistant": "..."}
            if isinstance(turn.get("human"), str) and turn["human"].strip():
                return turn["human"].strip()[:500]
            role = (turn.get("from") or turn.get("role") or "").lower()
            if role in {"human", "user"}:
                v = turn.get("value") or turn.get("content") or turn.get("text")
                if isinstance(v, str) and v.strip():
                    return v.strip()[:500]
            for k in ("value", "content", "text", "human", "user", "query"):
                v = turn.get(k)
                if isinstance(v, str) and v.strip() and len(v.strip()) >= 12:
                    return v.strip()[:500]
    return None


def _adapt_domain(instruction: str, task: str) -> str:
    """
    Adapt surface nouns only — keep instructional wording.
    Replace generic doc references with university-assistant subjects.
    """
    # Light, conservative substitutions for subject matter only
    out = instruction
    replacements = [
        (r"\bthis (article|document|text|passage|contract|email)\b", "this module handbook", re.I),
        (r"\bthe (article|document|text|passage)\b", "the assessment policy", re.I),
    ]
    for pat, repl, flags in replacements:
        out, n = re.subn(pat, repl, out, count=1, flags=flags)
        if n:
            break
    # Ensure task still readable as instruction (no full rewrite)
    if task == "summarize_3_bullets" and not SUMMARIZE_RE.search(out):
        return instruction  # refuse unsafe adapt
    if task == "extract_entities" and not ENTITY_RE.search(out):
        return instruction
    return out


def mine() -> dict[str, list[dict]]:
    texts = _iter_texts()
    buckets: dict[str, list[dict]] = {
        "summarize_3_bullets": [],
        "extract_entities": [],
        "lone_wolf": [],
    }
    seen: set[str] = set()
    for source, mine_id, text in texts:
        key = text.lower().strip()
        if key in seen or len(text) < 12:
            continue
        seen.add(key)
        if SUMMARIZE_RE.search(text) and not ENTITY_RE.search(text):
            instr = _adapt_domain(text.split("\n")[0].strip(), "summarize_3_bullets")
            buckets["summarize_3_bullets"].append(
                {"mine_id": mine_id, "source": source, "instruction": instr, "raw": text}
            )
        elif ENTITY_RE.search(text):
            instr = _adapt_domain(text.split("\n")[0].strip(), "extract_entities")
            buckets["extract_entities"].append(
                {"mine_id": mine_id, "source": source, "instruction": instr, "raw": text}
            )
        elif not LONE_EXCLUDE.search(text) and len(text) < 200:
            buckets["lone_wolf"].append(
                {"mine_id": mine_id, "source": source, "instruction": text, "raw": text}
            )
    return buckets


def _write_coverage_report(buckets: dict[str, list[dict]]) -> Path:
    """Persist coverage gaps so they cannot be silently skipped."""
    from datetime import datetime, timezone

    report = ROOT / "workloads" / "phase6" / "phrasings_coverage.md"
    log_path = ROOT / "docs" / "PHASE6_DECISIONS_LOG.md"
    lines = [
        "# Phase 6 phrasing coverage",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Task | Mined | ShareGPT | LMSYS | MOSS | Gap? |",
        "|------|------:|---------:|------:|-----:|------|",
    ]
    gap_notes: list[str] = []
    for task, rows in buckets.items():
        by_src: dict[str, int] = {}
        for r in rows:
            by_src[r["source"]] = by_src.get(r["source"], 0) + 1
        gap = "YES" if len(rows) == 0 else "no"
        lines.append(
            f"| {task} | {len(rows)} | {by_src.get('sharegpt', 0)} | "
            f"{by_src.get('lmsys', 0)} | {by_src.get('moss', 0)} | {gap} |"
        )
        if len(rows) == 0:
            gap_notes.append(
                f"- **{task}**: 0 mined phrasings after scan of `{RAW}`. "
                "Do not invent; place ShareGPT/LMSYS/MOSS dumps and re-run."
            )
    lines.append("")
    if gap_notes:
        lines.append("## Coverage gaps")
        lines.append("")
        lines.extend(gap_notes)
        lines.append("")
    else:
        lines.append("No coverage gaps for scanned tasks.")
        lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")

    # Append a short pointer into the decisions log (idempotent-ish marker)
    marker = "<!-- phrasings-coverage-auto -->"
    snippet = (
        f"\n{marker}\n"
        f"### Phrasing coverage auto-update\n\n"
        f"See latest table in `workloads/phase6/phrasings_coverage.md` "
        f"({datetime.now(timezone.utc).date().isoformat()}).\n"
    )
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8")
        if marker in text:
            # replace previous auto block through next --- or EOF-ish: simple truncate at marker
            head = text.split(marker)[0].rstrip()
            text = head + "\n" + snippet
        else:
            text = text.rstrip() + "\n" + snippet
        log_path.write_text(text, encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    buckets = mine()
    print(f"raw texts scanned from: {RAW} (exists={RAW.exists()})")
    for task, rows in buckets.items():
        by_src: dict[str, int] = {}
        for r in rows:
            by_src[r["source"]] = by_src.get(r["source"], 0) + 1
        print(f"{task}: {len(rows)} mined {by_src}")
        if len(rows) == 0:
            print(
                f"  COVERAGE GAP: {task} - no mined phrasings. "
                f"Place ShareGPT/LMSYS/MOSS dumps under {RAW} and re-run. Do not invent."
            )

    report = _write_coverage_report(buckets)
    print(f"wrote coverage report -> {report}")

    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        for task, rows in buckets.items():
            path = OUT / f"{task}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"wrote {path}")
    elif not args.dry_run:
        print("Pass --write to save JSONL, or --dry-run to only print counts "
              "(coverage report is always written).")


if __name__ == "__main__":
    main()

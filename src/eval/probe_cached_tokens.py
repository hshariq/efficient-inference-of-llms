#!/usr/bin/env python3
"""
Gate probe for Phase 6b: confirm vLLM exposes cached_tokens on an APC hit.

Requires a warm vLLM server WITH --enable-prefix-caching.

  PYTHONPATH=. python -m src.eval.probe_cached_tokens
  PYTHONPATH=. python -m src.eval.probe_cached_tokens --base-url http://localhost:8000/v1

On PASS, writes results/phase6/.cached_tokens_probe_ok.json — required by the
eval harness before apc/optimizer/gptcache runs (hard gate).
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from src.eval.backends import _extract_cached_tokens
from src.eval.cached_tokens_gate import write_probe_pass_marker
from src.eval.config import MODEL


PROMPT = (
    "Please summarize the following in 3 bullets.\n\n"
    "Probe document for APC: Alpha Corp reported 12% revenue growth driven by "
    "cloud services in Europe. The board approved a dividend increase."
)


def _one(client: httpx.Client, model: str) -> dict:
    r = client.post(
        "/chat/completions",
        headers={"Authorization": "Bearer EMPTY"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 32,
            "temperature": 0,
            "stream": False,
        },
    )
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    print(f"base_url={args.base_url}")
    print(f"model={args.model}")
    print("--- firing identical prompt twice (expect APC hit on #2) ---")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120.0) as client:
        d1 = _one(client, args.model)
        d2 = _one(client, args.model)

    u1 = d1.get("usage") or {}
    u2 = d2.get("usage") or {}
    print("usage call#1 (raw):")
    print(json.dumps(u1, indent=2))
    print("usage call#2 (raw):")
    print(json.dumps(u2, indent=2))

    c1 = _extract_cached_tokens(u1)
    c2 = _extract_cached_tokens(u2)
    print(f"extracted cached_tokens: call1={c1} call2={c2}")

    if c2 <= 0:
        print(
            "FAIL: second identical request shows cached_tokens=0 (or missing field).\n"
            "TSR will silently read 0.0 until vLLM exposes this field.\n"
            "Check --enable-prefix-caching, vLLM version, and usage schema.\n"
            "Harness will REFUSE apc/optimizer/gptcache runs until this PASSes.",
            file=sys.stderr,
        )
        return 1

    marker = write_probe_pass_marker(
        base_url=args.base_url,
        model=args.model,
        cached_tokens_call2=c2,
        usage_call2=u2,
    )
    print("probe_cached_tokens: PASS (non-zero cached_tokens on repeat)")
    print(f"wrote gate marker -> {marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

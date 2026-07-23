#!/usr/bin/env python3
"""
Phase 5 smoke: exercise TTL headers via the live proxy.

Requires vLLM :8000 + proxy :9000 with admission hold on (and rewrite on).

  export OPTIMIZER_REWRITE_MODE=on
  export OPTIMIZER_TTL_MODE=on
  export OPTIMIZER_ADMISSION_HOLD_MS=50
  export OPTIMIZER_MAX_TTL_MS=200
  export OPTIMIZER_TTL_BATCH_PEERS=8
  bash src/proxy/start_proxy.sh

  PYTHONPATH=. python src/proxy/smoke_ttl.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import time

from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
PROMPT = (
    "Please summarize the following in 3 bullets.\n\n"
    "Alpha Corp revenue rose 12% on cloud growth in Europe."
)


def _one(base_url: str) -> tuple[str, str, float]:
    # Use raw httpx-style via OpenAI is awkward for headers; use httpx.
    import httpx

    t0 = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        r = client.post(
            "/chat/completions",
            headers={"Authorization": "Bearer EMPTY"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 64,
                "temperature": 0,
                "stream": False,
            },
        )
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    return (
        r.headers.get("x-optimizer-ttl", ""),
        r.headers.get("x-optimizer-ttl-wait-ms", ""),
        elapsed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:9000/v1")
    args = parser.parse_args()

    print(f"base_url={args.base_url}")
    print("--- lonely request (expect hold_window if hold on, else skip) ---")
    disp, wait, elapsed = _one(args.base_url)
    print(f"  X-Optimizer-TTL={disp!r} wait_ms={wait!r} wall_s={elapsed:.3f}")

    print("--- two concurrent same-task (expect hold_window together, or max_batch if peers=2) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_one, args.base_url) for _ in range(2)]
        for i, fut in enumerate(futs, start=1):
            disp, wait, elapsed = fut.result()
            print(f"  req{i}: TTL={disp!r} wait_ms={wait!r} wall_s={elapsed:.3f}")

    # Sanity OpenAI path still works
    client = OpenAI(base_url=args.base_url, api_key="EMPTY")
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=32,
        temperature=0,
    )
    print("--- openai client ok ---")
    print((r.choices[0].message.content or "")[:120])


if __name__ == "__main__":
    main()

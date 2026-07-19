#!/usr/bin/env python3
"""
Lightweight parallel smoke test for the Phase 2 proxy (not a formal eval).

Fires N concurrent chat requests and reports how many succeed.
Does not replace bench_overhead.py or the later load harness.

  # vLLM :8000 + proxy :9000 up on this GPU node:
  python src/proxy/smoke_parallel.py --n 10
  python src/proxy/smoke_parallel.py --n 10 --base-url http://localhost:8000/v1  # direct
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
PROMPT = "Say hello in one short sentence."


def one_request(base_url: str, idx: int) -> tuple[int, bool, float, str]:
    client = OpenAI(base_url=base_url, api_key="EMPTY")
    t0 = time.perf_counter()
    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            stream=True,
            max_tokens=32,
            temperature=0.0,
        )
        chunks: list[str] = []
        for event in stream:
            if not event.choices:
                continue
            piece = event.choices[0].delta.content or ""
            if piece:
                chunks.append(piece)
        elapsed = time.perf_counter() - t0
        reply = "".join(chunks).strip() or "(empty)"
        return idx, True, elapsed, reply
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        return idx, False, elapsed, str(exc)


def main() -> None:
    p = argparse.ArgumentParser(description="Parallel smoke test (proxy/vLLM)")
    p.add_argument("--n", type=int, default=10, help="concurrent requests (default 10)")
    p.add_argument(
        "--base-url",
        default="http://localhost:9000/v1",
        help="OpenAI base URL (default: proxy :9000)",
    )
    args = p.parse_args()

    print(f"Firing {args.n} concurrent requests → {args.base_url}")
    print(f"Model: {MODEL}")
    t0 = time.perf_counter()
    ok = 0
    fail = 0

    with ThreadPoolExecutor(max_workers=args.n) as pool:
        futs = [pool.submit(one_request, args.base_url, i) for i in range(args.n)]
        for fut in as_completed(futs):
            idx, success, elapsed, detail = fut.result()
            if success:
                ok += 1
                print(f"  [{idx:02d}] OK  {elapsed:.3f}s  {detail!r}")
            else:
                fail += 1
                print(f"  [{idx:02d}] FAIL {elapsed:.3f}s  {detail}")

    wall = time.perf_counter() - t0
    print("---")
    print(f"OK={ok}  FAIL={fail}  wall_time={wall:.3f}s")
    if fail:
        raise SystemExit(1)
    print("Proxy/server survived concurrent smoke test.")


if __name__ == "__main__":
    main()

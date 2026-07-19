#!/usr/bin/env python3
"""
Phase 2 overhead harness: direct vLLM vs pass-through proxy.

Runs N streaming chat requests at concurrency=1 against each base URL,
skips warmup runs, reports mean ± std (and median / p95) for TTFT + total.

Example (GPU node, vLLM :8000 and proxy :9000 both up):
  python src/proxy/bench_overhead.py --n 30 --warmup 3
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass

from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
PROMPT = "Say hello in one short sentence."


@dataclass
class Sample:
    ttft: float
    total: float


def one_stream(client: OpenAI) -> Sample:
    t0 = time.perf_counter()
    ttft: float | None = None
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        stream=True,
        max_tokens=64,
        temperature=0.0,
    )
    for event in stream:
        if not event.choices:
            continue
        piece = event.choices[0].delta.content or ""
        if not piece:
            continue
        if ttft is None:
            ttft = time.perf_counter() - t0
    total = time.perf_counter() - t0
    if ttft is None:
        raise RuntimeError("no content tokens received")
    return Sample(ttft=ttft, total=total)


def run_path(name: str, base_url: str, n: int, warmup: int) -> list[Sample]:
    client = OpenAI(base_url=base_url, api_key="EMPTY")
    print(f"\n=== {name} ({base_url}) ===")
    print(f"warmup={warmup}, timed={n}")

    for i in range(warmup):
        s = one_stream(client)
        print(f"  warmup[{i}] ttft={s.ttft:.3f}s total={s.total:.3f}s")

    samples: list[Sample] = []
    for i in range(n):
        s = one_stream(client)
        samples.append(s)
        print(f"  run[{i:02d}] ttft={s.ttft:.3f}s total={s.total:.3f}s")
    return samples


def summarise(label: str, samples: list[Sample]) -> None:
    ttfts = [s.ttft for s in samples]
    totals = [s.total for s in samples]

    def stats(xs: list[float]) -> str:
        mean = statistics.fmean(xs)
        std = statistics.stdev(xs) if len(xs) > 1 else 0.0
        med = statistics.median(xs)
        p95 = sorted(xs)[max(0, int(round(0.95 * (len(xs) - 1))))]
        return f"mean={mean:.3f}s ± {std:.3f}  median={med:.3f}  p95={p95:.3f}"

    print(f"\n--- {label} (n={len(samples)}) ---")
    print(f"  TTFT:  {stats(ttfts)}")
    print(f"  Total: {stats(totals)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Proxy overhead: direct vLLM vs proxy")
    p.add_argument("--n", type=int, default=30, help="timed repeats per path (default 30)")
    p.add_argument("--warmup", type=int, default=3, help="discarded warmup runs (default 3)")
    p.add_argument(
        "--direct",
        default="http://localhost:8000/v1",
        help="direct vLLM base URL",
    )
    p.add_argument(
        "--proxy",
        default="http://localhost:9000/v1",
        help="proxy base URL",
    )
    p.add_argument(
        "--only",
        choices=("both", "direct", "proxy"),
        default="both",
    )
    args = p.parse_args()

    print(f"Model: {MODEL}")
    print(f"Prompt: {PROMPT!r}")
    print(f"Concurrency: 1 | N={args.n} | warmup={args.warmup}")

    direct_samples: list[Sample] = []
    proxy_samples: list[Sample] = []

    if args.only in ("both", "direct"):
        direct_samples = run_path("direct vLLM", args.direct, args.n, args.warmup)
        summarise("direct vLLM", direct_samples)

    if args.only in ("both", "proxy"):
        proxy_samples = run_path("via proxy", args.proxy, args.n, args.warmup)
        summarise("via proxy", proxy_samples)

    if direct_samples and proxy_samples:
        d_ttft = statistics.fmean(s.ttft for s in direct_samples)
        p_ttft = statistics.fmean(s.ttft for s in proxy_samples)
        d_tot = statistics.fmean(s.total for s in direct_samples)
        p_tot = statistics.fmean(s.total for s in proxy_samples)
        print("\n========== OVERHEAD (mean proxy − mean direct) ==========")
        print(f"  Δ TTFT:  {p_ttft - d_ttft:+.3f} s")
        print(f"  Δ Total: {p_tot - d_tot:+.3f} s")
        print("=========================================================")


if __name__ == "__main__":
    main()

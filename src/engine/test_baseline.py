#!/usr/bin/env python3
"""
Phase 1 smoke test for the baseline vLLM OpenAI server (with APC).

Run this on the SAME Slurm compute node as run_vllm.sh.
localhost:8000 is not reachable from a login node.
"""

from __future__ import annotations

import time

from openai import OpenAI

BASE_URL = "http://localhost:8000/v1"
MODEL = "meta-llama/Llama-3.1-8B-Instruct"
TEST_PROMPT = "Say hello in one short sentence."


def main() -> None:
    client = OpenAI(
        base_url=BASE_URL,
        # vLLM does not validate this; any non-empty string is fine locally.
        api_key="EMPTY",
    )

    print(f"Connecting to {BASE_URL}")
    print(f"Model: {MODEL}")
    print(f"Prompt: {TEST_PROMPT!r}")
    print("---")

    t0 = time.perf_counter()
    ttft: float | None = None
    chunks: list[str] = []

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": TEST_PROMPT}],
        stream=True,
        max_tokens=64,
        temperature=0.0,
    )

    for event in stream:
        if not event.choices:
            continue
        delta = event.choices[0].delta
        piece = delta.content or ""
        if not piece:
            continue
        if ttft is None:
            ttft = time.perf_counter() - t0
        chunks.append(piece)

    total_latency = time.perf_counter() - t0
    reply = "".join(chunks).strip()

    print(f"Response: {reply}")
    print("---")
    if ttft is None:
        print("TTFT: n/a (no content tokens received)")
    else:
        print(f"TTFT: {ttft:.3f} s")
    print(f"Total latency: {total_latency:.3f} s")


if __name__ == "__main__":
    main()

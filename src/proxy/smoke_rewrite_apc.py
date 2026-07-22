#!/usr/bin/env python3
"""
Phase 4e smoke: shared-instruction / different-data APC benefit via the proxy.

Sends two summarize requests with *different* documents through :9000.
With OPTIMIZER_REWRITE_MODE=on, both should get the same block-aligned system
prefix → request B should show a warm TTFT vs cold A (and vs rewrite=off).

Example (GPU node, vLLM :8000 + proxy :9000):
  python src/proxy/smoke_rewrite_apc.py
  python src/proxy/smoke_rewrite_apc.py --base-url http://localhost:9000/v1
"""

from __future__ import annotations

import argparse
import time

from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"

DOC_A = (
    "Alpha Corp reported quarterly revenue of $4.2B, up 12% year over year, "
    "driven by cloud services in Europe and a new enterprise contract with "
    "Nordic Bank. Operating margin improved to 28%."
)
DOC_B = (
    "The City of Leeds approved a zoning ordinance for the waterfront district, "
    "allowing mixed-use towers up to 18 storeys and requiring 20% affordable "
    "housing units. Construction is expected to begin in 2027."
)

# Paraphrased instructions — catalogue should collapse both to the same prefix.
PROMPT_A = f"Please summarize the following in 3 bullets.\n\n{DOC_A}"
PROMPT_B = f"Summarise this document in three bullet points:\n\n{DOC_B}"


def one_stream(client: OpenAI, prompt: str) -> tuple[float, float, str]:
    t0 = time.perf_counter()
    ttft: float | None = None
    chunks: list[str] = []
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=128,
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
        chunks.append(piece)
    total = time.perf_counter() - t0
    if ttft is None:
        raise RuntimeError("no content tokens received")
    return ttft, total, "".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:9000/v1",
        help="Proxy OpenAI base URL (default :9000)",
    )
    args = parser.parse_args()

    client = OpenAI(base_url=args.base_url, api_key="EMPTY")
    print(f"base_url={args.base_url}")
    print("Case: shared instruction (paraphrased) + DIFFERENT documents")
    print("---")
    print("INPUT A (client → proxy):")
    print(PROMPT_A)
    print("---")
    print("INPUT B (client → proxy):")
    print(PROMPT_B)
    print("---")

    # Show what the rewrite layer would emit (same logic as the proxy).
    from src.proxy.rewrite.pipeline import rewrite_request

    for label, prompt in (("A", PROMPT_A), ("B", PROMPT_B)):
        body, decision = rewrite_request(
            {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
        )
        print(f"REWRITE {label}: action={decision.action} reason={decision.reason} task={decision.catalogue_task}")
        if decision.action == "rewrite":
            sys_msg = body["messages"][0]["content"]
            usr_msg = body["messages"][1]["content"]
            print(f"  system[:160]={sys_msg[:160]!r}")
            print(f"  user[:160]={usr_msg[:160]!r}")
    print("---")

    ttft_a, total_a, text_a = one_stream(client, PROMPT_A)
    print(f"Doc A (cold-ish)  ttft={ttft_a:.3f}s total={total_a:.3f}s")
    print(f"  LLM output[:120]={text_a[:120]!r}")

    # Brief pause so APC can settle; not required but avoids overlapping decode.
    time.sleep(0.5)

    ttft_b, total_b, text_b = one_stream(client, PROMPT_B)
    print(f"Doc B (warm hope) ttft={ttft_b:.3f}s total={total_b:.3f}s")
    print(f"  LLM output[:120]={text_b[:120]!r}")

    ratio = ttft_a / ttft_b if ttft_b > 0 else float("inf")
    print("---")
    print(f"TTFT A/B ratio = {ratio:.2f}x  ( >1 means B was faster — expected under APC)")
    print("Check proxy logs / response headers: X-Optimizer-Rewrite: rewrite")
    print("Compare with OPTIMIZER_REWRITE_MODE=off restart if needed.")


if __name__ == "__main__":
    main()

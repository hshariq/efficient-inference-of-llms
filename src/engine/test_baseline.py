#!/usr/bin/env python3
"""
Phase 1 smoke / timing test.

Backends:
  vllm  — OpenAI client → local vLLM server (http://localhost:8000)
  hf    — Hugging Face transformers generate on this GPU (no vLLM)

Examples (on the SAME GPU node as the job):
  python src/engine/test_baseline.py              # vLLM only (server must be up)
  python src/engine/test_baseline.py --backend hf # HF only (stop vLLM first — VRAM)
  python src/engine/test_baseline.py --backend both
"""

from __future__ import annotations

import argparse
import time

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
TEST_PROMPT = "Say hello in one short sentence."
BASE_URL = "http://localhost:8000/v1"


def bench_vllm() -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key="EMPTY")
    print(f"[vLLM] Connecting to {BASE_URL}")
    print(f"[vLLM] Model: {MODEL}")
    print(f"[vLLM] Prompt: {TEST_PROMPT!r}")

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
        piece = event.choices[0].delta.content or ""
        if not piece:
            continue
        if ttft is None:
            ttft = time.perf_counter() - t0
        chunks.append(piece)

    total = time.perf_counter() - t0
    reply = "".join(chunks).strip()
    return {"backend": "vLLM (OpenAI API)", "reply": reply, "ttft": ttft, "total": total}


def bench_hf() -> dict:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
    from threading import Thread

    print(f"[HF] Loading {MODEL} on CUDA (no vLLM) ...")
    print(f"[HF] Prompt: {TEST_PROMPT!r}")
    print("[HF] Tip: stop the vLLM server first if you hit CUDA OOM.")

    t_load0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
    )
    model.eval()
    load_s = time.perf_counter() - t_load0
    print(f"[HF] Model load time: {load_s:.3f} s")

    messages = [{"role": "user", "content": TEST_PROMPT}]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # Warmup (exclude from timed generate)
    with torch.inference_mode():
        _ = model.generate(**inputs, max_new_tokens=1, do_sample=False)
        torch.cuda.synchronize()

    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    gen_kwargs = dict(
        **inputs,
        max_new_tokens=64,
        do_sample=False,
        streamer=streamer,
    )

    t0 = time.perf_counter()
    ttft: float | None = None
    chunks: list[str] = []

    thread = Thread(target=lambda: model.generate(**gen_kwargs))
    thread.start()
    for piece in streamer:
        if not piece:
            continue
        if ttft is None:
            ttft = time.perf_counter() - t0
        chunks.append(piece)
    thread.join()
    torch.cuda.synchronize()
    total = time.perf_counter() - t0
    reply = "".join(chunks).strip()

    return {
        "backend": "Hugging Face (no vLLM)",
        "reply": reply,
        "ttft": ttft,
        "total": total,
        "load_s": load_s,
    }


def print_result(result: dict) -> None:
    print("---")
    print(f"Backend: {result['backend']}")
    print(f"Response: {result['reply']}")
    if result.get("load_s") is not None:
        print(f"Model load: {result['load_s']:.3f} s")
    if result["ttft"] is None:
        print("TTFT: n/a")
    else:
        print(f"TTFT: {result['ttft']:.3f} s")
    print(f"Total generate latency: {result['total']:.3f} s")


def print_comparison(results: list[dict]) -> None:
    if len(results) < 2:
        return
    print("\n========== COMPARISON ==========")
    print(f"{'Backend':<28} {'TTFT (s)':>10} {'Total (s)':>10}")
    for r in results:
        ttft = f"{r['ttft']:.3f}" if r["ttft"] is not None else "n/a"
        print(f"{r['backend']:<28} {ttft:>10} {r['total']:>10.3f}")
    print("================================")
    print("Note: HF TTFT/total are local generate; vLLM includes server scheduling.")
    print("      HF also paid a one-shot model load (printed above) — vLLM amortises that.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline timing: vLLM vs HF")
    parser.add_argument(
        "--backend",
        choices=("vllm", "hf", "both"),
        default="both",
        help="Which backend(s) to time (default: both)",
    )
    args = parser.parse_args()

    results: list[dict] = []

    if args.backend in ("vllm", "both"):
        try:
            results.append(bench_vllm())
            print_result(results[-1])
        except Exception as exc:  # noqa: BLE001 — show friendly error on cluster
            print(f"[vLLM] FAILED: {exc}")
            print("[vLLM] Is the server up? bash src/engine/start_on_gpu.sh")

    if args.backend in ("hf", "both"):
        if args.backend == "both":
            print(
                "\n[HF] If CUDA OOM: Ctrl+C the vLLM server, then re-run "
                "with --backend hf only.\n"
            )
        try:
            results.append(bench_hf())
            print_result(results[-1])
        except Exception as exc:  # noqa: BLE001
            print(f"[HF] FAILED: {exc}")

    print_comparison(results)


if __name__ == "__main__":
    main()

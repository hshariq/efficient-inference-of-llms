# Phase 6 — vLLM launch modes (Vanilla vs APC)

Same node as eval harness. Model: `meta-llama/Llama-3.1-8B-Instruct`.

## APC (default Phase 1 path)

Use existing `src/engine/start_on_gpu.sh` / `run_vllm.sh` with
`--enable-prefix-caching` and `--enable-prompt-tokens-details` (required so
`usage.prompt_tokens_details.cached_tokens` is populated for Phase 6 TSR).
Always launch via the script (sets `VLLM_USE_FLASHINFER_SAMPLER=0` on Aire).

Harness:

```bash
PYTHONPATH=. python -m src.eval.run --system apc --workload workloads/phase6/smoke_tiny.jsonl
```

## Vanilla (no prefix caching)

**vLLM 0.11 (V1) enables APC by default.** Omitting `--enable-prefix-caching`
is **not** enough — you must pass **`--no-enable-prefix-caching`**.

```bash
export VLLM_USE_FLASHINFER_SAMPLER=0
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --enable-prompt-tokens-details \
  --no-enable-prefix-caching
```

Confirm engine log shows `enable_prefix_caching=False`. Probe should report
`call2 cached_tokens = 0` (gate FAIL is expected for vanilla).

```bash
PYTHONPATH=. python -m src.eval.run --system vanilla --workload workloads/phase6/smoke_tiny.jsonl
```

Do not run Vanilla and APC against the same live server process if the flag differs —
restart vLLM between modes.

## Optimizer Box

vLLM with APC on `:8000` + proxy `:9000`:

- semantic-only ablation: `OPTIMIZER_REWRITE_MODE=on` `OPTIMIZER_TTL_MODE=off`
- full / hold ablation: `OPTIMIZER_TTL_MODE=on` (hold_ms=50 for realistic burst)

```bash
PYTHONPATH=. python -m src.eval.run --system optimizer --workload ...
PYTHONPATH=. python -m src.eval.run --system optimizer_hold --workload ... --concurrency 8
```

## GPTCache

In-process semantic output cache; `--base-url` / default points at upstream vLLM `:8000`.

```bash
PYTHONPATH=. python -m src.eval.run --system gptcache --workload ...
```

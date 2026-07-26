#!/bin/bash
#SBATCH --job-name=ob-vllm-baseline
#SBATCH --output=logs/vllm_baseline_%j.out
#SBATCH --error=logs/vllm_baseline_%j.err
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:l40s:1
# Partition confirmed via `sinfo` on Aire: `gpu` (nodes gpu001–gpu028).
# GRES confirmed on gpu020: `Gres=gpu:l40s:3` (use lowercase `l40s`, not `L40S`).
#SBATCH --partition=gpu
# QoS: not shown as required by `sinfo`; leave unset unless Aire docs say otherwise.
# #SBATCH --qos=

# =============================================================================
# Optimizer Box — Phase 1: Baseline Engine + APC (vLLM OpenAI server)
# University of Leeds Aire HPC — NVIDIA L40S
#
# WORKING RECIPE (smoke-tested 2026-07-18):
#   vllm==0.11.0 + transformers==4.57.6 + VLLM_USE_FLASHINFER_SAMPLER=0
#   model: meta-llama/Llama-3.1-8B-Instruct
#   flags: --dtype bfloat16 --gpu-memory-utilization 0.90
#          --max-model-len 8192 --enable-prefix-caching
#          --enable-prompt-tokens-details  (Phase 6 TSR / cached_tokens)
#
# Interactive start (from login node):
#   srun -t 02:00:00 -p gpu --gres=gpu:1 --mem=64G --cpus-per-task=8 --pty /bin/bash
#   # CRITICAL: always --mem=64G (default mem=1G → OOM "Killed")
#   cd ~/efficient-inference-of-llms
#   export HF_TOKEN=hf_...          # once per shell
#   bash src/engine/start_on_gpu.sh
#
# Second shell for the smoke test (same job):
#   srun --jobid=$SLURM_JOB_ID --overlap --pty /bin/bash
#   module load python/3.13.0 && source .venv/bin/activate
#   python src/engine/test_baseline.py
# =============================================================================

set -euo pipefail

mkdir -p logs

# -----------------------------------------------------------------------------
# Cluster environment (Aire-specific)
# -----------------------------------------------------------------------------
module purge
module load python/3.13.0

# Project venv (pinned deps from requirements.txt — do not upgrade mid-experiment)
source /users/bgxj0542/efficient-inference-of-llms/.venv/bin/activate

# -----------------------------------------------------------------------------
# Known-good runtime env (required on Aire — no nvcc / CUDA toolkit on nodes)
# -----------------------------------------------------------------------------
export VLLM_USE_FLASHINFER_SAMPLER=0

# Soft check: interactive jobs without --mem often get 1G and die during load
if [[ -n "${SLURM_MEM_PER_NODE:-}" ]]; then
  # SLURM_MEM_PER_NODE is usually MiB
  if (( SLURM_MEM_PER_NODE < 32000 )); then
    echo "ERROR: This job has only ${SLURM_MEM_PER_NODE} MiB RAM."
    echo "       Restart with: srun ... --mem=64G --cpus-per-task=8 ..."
    exit 1
  fi
fi

# -----------------------------------------------------------------------------
# Hugging Face auth (gated Llama-3.1 — token required only for first download)
# -----------------------------------------------------------------------------
if [[ -z "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  echo "WARNING: HF_TOKEN / HUGGING_FACE_HUB_TOKEN is not set."
  echo "         First-time download of Llama-3.1-8B-Instruct will fail."
  echo "         Cached weights under ~/.cache/huggingface do not need the token."
fi
if [[ -n "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
fi

MODEL="meta-llama/Llama-3.1-8B-Instruct"
PORT=8000
HOST="0.0.0.0"
MAX_MODEL_LEN=8192

echo "=============================================="
echo " Host:     $(hostname)"
echo " Model:    ${MODEL}"
echo " Port:     ${PORT}"
echo " Max len:  ${MAX_MODEL_LEN}"
echo " Prefix:   APC enabled (--enable-prefix-caching)"
echo " Usage:    prompt_tokens_details enabled (cached_tokens in API)"
echo " Dtype:    bfloat16"
echo " GPU util: 0.90"
echo " FlashInfer sampler: OFF (VLLM_USE_FLASHINFER_SAMPLER=0)"
echo "=============================================="

# Launch OpenAI-compatible vLLM server (baseline + Automatic Prefix Caching).
python -m vllm.entrypoints.openai.api_server \
  --model "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len "${MAX_MODEL_LEN}" \
  --enable-prefix-caching \
  --enable-prompt-tokens-details

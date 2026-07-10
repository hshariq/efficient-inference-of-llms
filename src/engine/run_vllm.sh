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
# IMPORTANT — same-node testing:
#   test_baseline.py talks to http://localhost:8000 and MUST run on THIS
#   compute node (the same Slurm job), not on a login node.
#
#   Typical workflows:
#     A) Interactive (what worked on Aire):
#          srun -t 01:00:00 -p gpu --gres=gpu:1 --pty /bin/bash
#        Then on the allocated node (e.g. gpu020): module load, activate venv,
#        start the server, and in another shell on the SAME allocation run
#        test_baseline.py. Note: interactive used generic --gres=gpu:1;
#        this batch script pins --gres=gpu:l40s:1 for reproducible L40S nodes.
#     B) Batch: sbatch this script; once the server is up, run the test from
#        within the same job / on the same node (localhost only).
# =============================================================================

set -euo pipefail

mkdir -p logs

# -----------------------------------------------------------------------------
# Cluster environment (Aire-specific)
# -----------------------------------------------------------------------------
# Confirmed working interactive session on gpu020 (Jul 2026): only python/3.13.0
# was loaded. CUDA toolkit module was not required for vLLM 0.24.0 wheels;
# the node driver reports CUDA 12.6 via nvidia-smi. If a future install needs
# nvcc / toolkit headers, add e.g. `module load CUDA/12.x` here.
module purge
module load python/3.13.0

# Project venv (pinned deps from requirements.txt)
source /users/bgxj0542/efficient-inference-of-llms/.venv/bin/activate

# Pin note: install with  pip install -r requirements.txt
# Current baseline pin: vllm==0.24.0  (see requirements.txt). Do not upgrade
# mid-experiment — APC / scheduler behaviour can change across versions.

# -----------------------------------------------------------------------------
# Hugging Face auth (Llama-3-8B-Instruct is gated)
# -----------------------------------------------------------------------------
# TODO: Export your Hugging Face token (accepted Llama 3 licence on the Hub).
# Prefer injecting via Slurm secrets / env rather than hard-coding:
#   export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# Or:  export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
if [[ -z "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  echo "WARNING: HF_TOKEN / HUGGING_FACE_HUB_TOKEN is not set."
  echo "         Gated model download for Meta-Llama-3-8B-Instruct will fail."
fi

# Optional: keep HF cache on shared scratch rather than $HOME
# TODO: export HF_HOME="/path/to/scratch/hf_cache"

MODEL="meta-llama/Meta-Llama-3-8B-Instruct"
PORT=8000
HOST="0.0.0.0"

echo "=============================================="
echo " Host:     $(hostname)"
echo " Model:    ${MODEL}"
echo " Port:     ${PORT}"
echo " Prefix:   APC enabled (--enable-prefix-caching)"
echo " Dtype:    bfloat16"
echo " GPU util: 0.90"
echo "=============================================="

# Launch OpenAI-compatible vLLM server (baseline + Automatic Prefix Caching).
# Bind 0.0.0.0 so other processes on this node can reach it; clients on this
# node should still use http://localhost:8000/v1.
python -m vllm.entrypoints.openai.api_server \
  --model "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching

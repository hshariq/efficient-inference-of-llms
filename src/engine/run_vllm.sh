#!/bin/bash
#SBATCH --job-name=ob-vllm-baseline
#SBATCH --output=logs/vllm_baseline_%j.out
#SBATCH --error=logs/vllm_baseline_%j.err
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:L40S:1
# TODO: Confirm the Aire partition / QoS name for L40S nodes and set it here.
#SBATCH --partition=gpu
# #SBATCH --qos=TODO_QOS

# =============================================================================
# Optimizer Box — Phase 1: Baseline Engine + APC (vLLM OpenAI server)
# University of Leeds Aire HPC — NVIDIA L40S
#
# IMPORTANT — same-node testing:
#   test_baseline.py talks to http://localhost:8000 and MUST run on THIS
#   compute node (the same Slurm job), not on a login node.
#
#   Typical workflows:
#     A) Interactive:  srun --pty bash   → start this script / server, then
#        in another shell on the same allocation run test_baseline.py
#     B) Batch: start the server in the background below, wait until healthy,
#        then run:  python src/engine/test_baseline.py
# =============================================================================

set -euo pipefail

mkdir -p logs

# -----------------------------------------------------------------------------
# Cluster environment (Aire-specific — fill these in before first real run)
# -----------------------------------------------------------------------------
# TODO: Load the CUDA / compiler modules required on Aire, e.g.:
#   module purge
#   module load CUDA/12.4.0
#   module load GCCcore/13.2.0
#   module load Python/3.11.5

# TODO: Activate the project virtualenv that has the pinned deps from
#       requirements.txt installed, e.g.:
#   source /path/to/optimizer-box/.venv/bin/activate
#   # or: source "$HOME/venvs/optimizer-box/bin/activate"

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

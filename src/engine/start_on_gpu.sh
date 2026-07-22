#!/bin/bash
# One-shot launcher for an Aire GPU node (after srun has already landed you here).
# Usage:
#   export HF_TOKEN=hf_...   # optional if model already cached
#   bash src/engine/start_on_gpu.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ "$(hostname)" == login* ]]; then
  echo "ERROR: You are on a login node ($(hostname))."
  echo "Request a GPU first:"
  echo "  srun -t 02:00:00 -p gpu --gres=gpu:1 --mem=64G --cpus-per-task=8 --pty /bin/bash"
  exit 1
fi

echo "Starting baseline vLLM on $(hostname) ..."
echo "When you see 'Application startup complete', open a second shell with:"
echo "  srun --jobid=\${SLURM_JOB_ID} --overlap --pty /bin/bash"
echo "then:  python src/engine/test_baseline.py"
echo

exec bash "$ROOT/src/engine/run_vllm.sh"

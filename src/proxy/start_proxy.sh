#!/bin/bash
# Start Phase 2 pass-through proxy on the GPU node (vLLM must already be on :8000).
#
#   export VLLM_BASE_URL=http://localhost:8000/v1   # default
#   bash src/proxy/start_proxy.sh
#
# Then point clients at http://localhost:9000/v1
# No gzip — would buffer SSE and corrupt TTFT measurements.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ "$(hostname)" == login* ]]; then
  echo "ERROR: Run the proxy on the same GPU node as vLLM, not a login node."
  exit 1
fi

module load python/3.13.0 2>/dev/null || true
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

export VLLM_BASE_URL="${VLLM_BASE_URL:-http://localhost:8000/v1}"
export PROXY_HOST="${PROXY_HOST:-0.0.0.0}"
export PROXY_PORT="${PROXY_PORT:-9000}"
# Phase 4: on | tag_only | off
export OPTIMIZER_REWRITE_MODE="${OPTIMIZER_REWRITE_MODE:-on}"
# Part 2/3 tagging: basic|full  and  off|minilm|qwen3 (default: rules only)
export OPTIMIZER_SCHEMA_FEATURES="${OPTIMIZER_SCHEMA_FEATURES:-full}"
export OPTIMIZER_EMBEDDING_BACKEND="${OPTIMIZER_EMBEDDING_BACKEND:-off}"

echo "=============================================="
echo " Optimizer Box proxy (Phase 4 rewrite enabled)"
echo " Upstream: ${VLLM_BASE_URL}"
echo " Listen:   ${PROXY_HOST}:${PROXY_PORT}"
echo " Rewrite:  ${OPTIMIZER_REWRITE_MODE}"
echo " Features: ${OPTIMIZER_SCHEMA_FEATURES}"
echo " EmbedFB:  ${OPTIMIZER_EMBEDDING_BACKEND}"
echo " Gzip:     disabled (SSE / TTFT integrity)"
echo "=============================================="

# --http1.1 / no proxy compression: keep chunks unbuffered for fair TTFT.
exec python -m uvicorn src.proxy.app:app \
  --host "${PROXY_HOST}" \
  --port "${PROXY_PORT}" \
  --http h11

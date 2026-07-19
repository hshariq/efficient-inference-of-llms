# Aire — start baseline in 3 steps

## 1. Login node → GPU node (always include --mem=64G)

```bash
srun -t 02:00:00 -p gpu --gres=gpu:1 --mem=64G --cpus-per-task=8 --pty /bin/bash
```

## 2. On the GPU node — start server

```bash
cd ~/efficient-inference-of-llms
export HF_TOKEN=hf_...          # only needed if weights not cached yet
bash src/engine/start_on_gpu.sh
```

Wait until the log shows: `Application startup complete`

## 3. Second shell — smoke test / timing (same job)

```bash
srun --jobid=$SLURM_JOB_ID --overlap --pty /bin/bash
module load python/3.13.0
source ~/efficient-inference-of-llms/.venv/bin/activate
cd ~/efficient-inference-of-llms

# vLLM only (server must be running):
python src/engine/test_baseline.py --backend vllm

# vLLM then HF comparison (default). If HF OOMs, stop the server and run:
python src/engine/test_baseline.py --backend hf
```

## Phase 2 — proxy (pass-through)

With vLLM already running on `:8000` (another shell on the same job):

```bash
# install once if needed
pip install 'fastapi>=0.115' 'uvicorn[standard]>=0.30' 'httpx>=0.27'

bash src/proxy/start_proxy.sh
```

Smoke via proxy:
```bash
python src/engine/test_baseline.py --backend vllm --base-url http://localhost:9000/v1
```

Overhead (N runs, mean ± std):
```bash
python src/proxy/bench_overhead.py --n 30 --warmup 3
```

Parallel smoke (not formal eval — just “does it survive?”):
```bash
python src/proxy/smoke_parallel.py --n 10
```

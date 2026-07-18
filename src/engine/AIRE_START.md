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

## Do not

- Start without `--mem=64G` (you get 1G → process `Killed`)
- Use `vllm==0.24` or `transformers` 5.x on Aire
- Force-reinstall a different PyTorch CUDA build after `pip install -r requirements.txt`
- Run the test from a login node (`localhost:8000` won’t work)

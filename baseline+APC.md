We are building Phase 1 (Baseline Engine + APC). I need to generate the baseline infrastructure to deploy on the University of Leeds Aire HPC cluster using an NVIDIA L40S GPU. 

Please generate the following two files, baking in these strict engineering requirements for HPC environments:

1. `src/engine/run_vllm.sh`: A comprehensive Slurm batch script requesting 1 NVIDIA L40S GPU. 
   - Include a placeholder and comment for exporting the `HF_TOKEN` since Llama-3-8B-Instruct is a gated model.
   - Launch `vllm.entrypoints.openai.api_server` on port 8000 with `--enable-prefix-caching`.
   - Explicitly set `--model meta-llama/Meta-Llama-3-8B-Instruct`, `--dtype bfloat16`, and `--gpu-memory-utilization 0.90` to ensure strict reproducibility for our dissertation benchmarks.
   - Add clearly marked `# TODO` comments for cluster-specific paths (like loading the specific CUDA module and activating the virtual environment).
   - Document in comments that `test_baseline.py` must run on the **same job/node** as the server (e.g. interactive `srun`, or a second step after the server is up). `localhost:8000` will not work from a login node.
   - Pin / note the vLLM version used for this baseline (comment in the script + `requirements.txt`) so APC behaviour does not silently drift between dissertation runs.

2. `src/engine/test_baseline.py`: A Python script using the `openai` client library to test the baseline engine.
   - It must point to `http://localhost:8000/v1` to talk to the engine running locally on the same compute node.
   - Crucial: It must use a streaming request (`stream=True`) so we can accurately measure and print the Time-to-First-Token (TTFT), alongside the total end-to-end latency. Calculate TTFT by marking the timestamp immediately before the API call and subtracting it from the timestamp when the very first token chunk arrives.

Do not write the FastAPI proxy, the router, or the trimmer yet. Just give me these two files so I can establish a bulletproof, reproducible baseline on the cluster.

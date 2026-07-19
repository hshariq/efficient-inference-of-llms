# Optimizer Box — Your TODO (manual / cluster-side)

Things **you** still need to do outside of generated code. Check items off as you go.

---

## Phase 1 — Baseline Engine + APC

### On Aire (before first `sbatch`)

- [ ] Create a Python venv on Aire and install pinned deps:
  ```bash
  # Prefer a modern Python module on Aire (vLLM wants >=3.10), then:
  python -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt   # currently pinned to vllm==0.11.0
  ```
  - [ ] If install still fails: check `python --version` and that CUDA modules are loaded.
  - [ ] Optional later: after a newer Python + pip, re-check `pip index versions vllm` and bump the pin deliberately.
  - [ ] Confirm the install on aire cluster: python -c "from importlib.metadata import version; print(version('vllm'))", should get 0.24.0

- [x] Accept the Meta Llama licence on Hugging Face — **granted** for `meta-llama/Llama-3.1-8B-Instruct`.
- [ ] Export `HF_TOKEN` in the job environment (or set it in `~/.bashrc` / Slurm env — do **not** commit the token).
  Baseline model is now **`meta-llama/Llama-3.1-8B-Instruct`** (scripts updated).
  **CUDA note (Aire):** driver is **12.6**. Do **not** use `vllm==0.24.0` (needs CUDA 13). Use `vllm==0.11.0` + torch `cu126` (see `requirements.txt`).
  Interactive job must use `--mem=64G` (default `mem=1G` OOM-kills vLLM).

  **How (HF licence + token) — you are not prompted during `pip install`:**
  The Llama 3 gate only hits when vLLM first **downloads the model weights**, not when installing packages.
  1. Log into https://huggingface.co (create an account if needed).
  2. Open https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct and **Accept** / request access to Meta’s licence (approval can take a few minutes).
  3. Create a token: Hugging Face → **Settings → Access Tokens → New token** (read access is enough).
  4. On Aire, in the same shell/job that will run vLLM:
     ```bash
     export HF_TOKEN="hf_your_token_here"
     ```
  5. Do **not** commit the token to git. Prefer job env, a private file outside the repo, or Slurm env injection.
  6. If skipped, the server usually fails later with `401` / `gated repo` / `access restricted` when pulling `Meta-Llama-3-8B-Instruct`.

  **Progress note (do not delete checklist above):** venv + `pip install -r requirements.txt` already done on Aire (Python 3.13, `vllm==0.24.0`). Verify with:
  ```bash
  python -c "from importlib.metadata import version; print(version('vllm'))"
  ```
  (`vllm.__version__` may print a module object — that is OK.)
- [ ] Fill `# TODO`s in `src/engine/run_vllm.sh`:
  - [x] Correct `--partition` / `--qos` for L40S on Aire → `--partition=gpu`; QoS not required from `sinfo`
  - [x] `module load` lines for CUDA / Python on Aire → `module load python/3.13.0` (no CUDA module in working session)
  - [x] `source` path to your venv → `/users/bgxj0542/efficient-inference-of-llms/.venv/bin/activate`
  - [ ] Optional: `HF_HOME` on scratch if `$HOME` quota is tight
- [x] Confirm GPU request syntax (`--gres=gpu:l40s:1`) matches Aire’s docs.
  Confirmed on `gpu020`: `Gres=gpu:l40s:3`, `nvidia-smi` shows NVIDIA L40S (~46GB). Use lowercase `l40s`.

### First smoke test

**How you get onto a GPU node (confirmed):** login nodes have no GPU. From the login node:
```bash
srun -t 02:00:00 -p gpu --gres=gpu:1 --mem=64G --cpus-per-task=8 --pty /bin/bash
```
**CRITICAL:** always pass `--mem=64G`. Without it Aire may allocate `mem=1G` and the OOM-killer will `Killed` vLLM while loading Llama 8B (seen on job 6685447).  
Wait in the queue until you land on a compute node (e.g. `gpu001`). Only then start vLLM / run `test_baseline.py`.

**Working stack on Aire (Jul 2026 smoke test — SUCCESS):**
- `vllm==0.11.0`, `transformers==4.57.6`, torch from vllm (`+cu128` ok on this driver for this run)
- `export VLLM_USE_FLASHINFER_SAMPLER=0` (no nvcc on node)
- `--max-model-len 8192 --enable-prefix-caching --dtype bfloat16`
- Model: `meta-llama/Llama-3.1-8B-Instruct`
- Smoke test result: reply `Hello.` — TTFT ~1.92s, total ~1.96s

- [x] Submit / start the server on a compute node (`sbatch` or interactive `srun`).
- [x] Wait until the OpenAI server is listening on port 8000.
- [x] Run `python src/engine/test_baseline.py` **on the same node** (not the login node).
- [x] Confirm printed TTFT + total latency look sane and a reply is returned.
- [ ] Save the job `.out` / `.err` logs and note the vLLM version (`0.11.0`) + transformers `4.57.6` for the dissertation methods section.
- [ ] Commit/push working pins (`requirements.txt`, `run_vllm.sh`, `start_on_gpu.sh`, `AIRE_START.md`) so Aire can `git pull` and restart cleanly.
- [ ] On Aire after pull: `chmod +x src/engine/start_on_gpu.sh src/engine/run_vllm.sh`

### Repo hygiene (when you’re ready)

- [x] Add a `.gitignore` (venv, logs, HF cache, `.env`, `__pycache__`, etc.).
- [ ] Commit Phase 1 files and push to `efficient-inference-of-llms` (private).
- [ ] Write a short README: how to launch baseline + how to run the smoke test on Aire.

---

## Later phases

- [x] **Phase 2 code scaffold** (pass-through proxy) — see `PHASE2_PROXY.md` / `src/proxy/`
  - [x] Aire smoke via `:9000` + `bench_overhead.py --n 30` (~+1 ms overhead)
  - [ ] Optional: `smoke_parallel.py --n 10`; commit/push Phase 2 + parallel smoke
- [~] **Phase 3: Trimmer preprocessing — SKIPPED for this dissertation** (cite as **future work**)
- [ ] **Phase 4: Semantic sub-batching + canonical prefixes** — see `PHASE4_SEMANTIC.md`
  - [x] 4a–4c code: schema tagger, catalogue, chat-template block align, bypass, proxy headers
  - [x] Unit tests in `tests/test_rewrite_align.py` (run on Aire with HF cache / `HF_TOKEN`)
  - [ ] Aire: `git pull`, restart proxy (`OPTIMIZER_REWRITE_MODE=on`), confirm `X-Optimizer-Rewrite: rewrite`
  - [ ] Aire 4e: `python src/proxy/smoke_rewrite_apc.py` (shared-instruction / different-data TTFT)
  - Must include: **block alignment** (16-token), shared-instruction/**different-data** tests, no Trimmer creep
- [ ] Phase 5: TTL / starvation escape hatch
- [ ] Phase 6: Evaluation harness (vanilla / APC / GPTCache / Optimizer Box)

**Scope note:** Architecture still *includes* Trimmer conceptually (`project-context.md` / diagram), but we are **not implementing** it in the submitted system. Ablation “(b) Trimmer alone” is dropped; eval focuses on proxy + semantic sub-batching (+ TTL) vs baselines.

---

*Update this file whenever a manual step appears (cluster config, tokens, licence acceptance, data collection). Generated code TODOs in scripts should stay mirrored here.*

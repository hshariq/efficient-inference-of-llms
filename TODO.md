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

- [ ] Accept the Meta Llama 3 licence on Hugging Face and create an access token.
- [ ] Export `HF_TOKEN` in the job environment (or set it in `~/.bashrc` / Slurm env — do **not** commit the token).
- [ ] Fill `# TODO`s in `src/engine/run_vllm.sh`:
  - [ ] Correct `--partition` / `--qos` for L40S on Aire
  - [ ] `module load` lines for CUDA / Python on Aire
  - [ ] `source` path to your venv
  - [ ] Optional: `HF_HOME` on scratch if `$HOME` quota is tight
- [ ] Confirm GPU request syntax (`--gres=gpu:L40S:1`) matches Aire’s docs.

### First smoke test

- [ ] Submit / start the server on a compute node (`sbatch` or interactive `srun`).
- [ ] Wait until the OpenAI server is listening on port 8000.
- [ ] Run `python src/engine/test_baseline.py` **on the same node** (not the login node).
- [ ] Confirm printed TTFT + total latency look sane and a reply is returned.
- [ ] Save the job `.out` / `.err` logs and note the vLLM version (`0.11.0`) for the dissertation methods section.

### Repo hygiene (when you’re ready)

- [ ] Add a `.gitignore` (venv, logs, HF cache, `.env`, `__pycache__`, etc.).
- [ ] Commit Phase 1 files and push to `efficient-inference-of-llms` (private).
- [ ] Write a short README: how to launch baseline + how to run the smoke test on Aire.

---

## Later phases (not started — do not implement yet)

- [ ] Phase 2: FastAPI proxy skeleton in front of vLLM
- [ ] Phase 3: Trimmer preprocessing
- [ ] Phase 4: Semantic sub-batching + canonical prefixes
- [ ] Phase 5: TTL / starvation escape hatch
- [ ] Phase 6: Evaluation harness (vanilla / APC / GPTCache / Optimizer Box)

---

*Update this file whenever a manual step appears (cluster config, tokens, licence acceptance, data collection). Generated code TODOs in scripts should stay mirrored here.*

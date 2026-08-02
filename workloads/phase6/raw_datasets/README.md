# Raw datasets (not committed)

Place ShareGPT / LMSYS-Chat-1M / MOSS dumps here for `src.eval.mine_phrasings`.

Suggested layout:

```text
raw_datasets/
  sharegpt/   *.json or *.jsonl
  lmsys/      *.jsonl
  moss/       *.jsonl or *.txt
```

Large files should stay on Aire scratch / local disk — add this directory to
`.gitignore` if downloading into the repo tree.

## Fetch on Aire (recommended)

```bash
cd ~/efficient-inference-of-llms
module load python/3.13.0 && source .venv/bin/activate
pip install -q datasets   # if needed

# Stream ~20k rows each (may take several minutes; do not invent phrasings)
PYTHONPATH=. python -m src.eval.fetch_raw_datasets --source all --max-rows 20000

# Remine (overwrites phrasings/*.jsonl — commit coverage report after)
PYTHONPATH=. python -m src.eval.mine_phrasings --write
cat workloads/phase6/phrasings_coverage.md

# Larger uniqueness probe (multi-source, no exact repeats)
PYTHONPATH=. python -m src.eval.build_adversarial_semantic --limit 400 \
  --probe-name adversarial_semantic_multi \
  --out workloads/phase6/adversarial_semantic_multi.jsonl
```

Then eval (APC vs Optimizer only, cold between):

```bash
PYTHONPATH=. python -m src.eval.run --system apc \
  --workload workloads/phase6/adversarial_semantic_multi.jsonl \
  --concurrency 1 \
  --out results/phase6/adv_sem_multi_apc.jsonl

# restart vLLM cold + proxy hold-off embed-off
PYTHONPATH=. python -m src.eval.run --system optimizer \
  --workload workloads/phase6/adversarial_semantic_multi.jsonl \
  --concurrency 1 \
  --out results/phase6/adv_sem_multi_optimizer.jsonl
```

## Notes

- **LMSYS** was mined earlier (`lmsys/lmsys_sample.jsonl`).
- **ShareGPT / MOSS** were deferred (parse / hang); `fetch_raw_datasets` + hardened
  ShareGPT turn parsing address that.
- Still **no invented paraphrases** — only mined instructions that rules-tag as
  catalogue tasks enter the adversarial builder.

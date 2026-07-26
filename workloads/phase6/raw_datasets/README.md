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

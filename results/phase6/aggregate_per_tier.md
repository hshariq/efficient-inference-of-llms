# Phase 6 per-tier TSR (from JSONL)

| system | source | n | tsr_aggregate | n_exact | tsr_exact | n_semantic | tsr_semantic | n_best_of_n | tsr_best_of_n | n_lone_wolf | tsr_lone_wolf |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vanilla | c1_vanilla.jsonl | 200 | 0.0 | 40 | 0.0 | 80 | 0.0 | 30 | 0.0 | 50 | 0.0 |
| apc | c1_apc.jsonl | 200 | 0.693092 | 40 | 0.974421 | 80 | 0.461241 | 30 | 0.963827 | 50 | 0.379029 |
| gptcache | c1_gptcache.jsonl | 200 | 0.85655 | 40 | 0.975 | 80 | 0.758769 | 30 | 1.0 | 50 | 0.0 |
| optimizer_hold | c1_optimizer_hold.jsonl | 200 | 0.700365 | 40 | 0.975516 | 80 | 0.475059 | 30 | 0.963212 | 50 | 0.360388 |
| optimizer | c1_optimizer_holdoff_minilm.jsonl | 200 | 0.700199 | 40 | 0.975516 | 80 | 0.475059 | 30 | 0.963212 | 50 | 0.347429 |
| optimizer_hold | c1_optimizer_holdon_minilm.jsonl | 200 | 0.700199 | 40 | 0.975516 | 80 | 0.475059 | 30 | 0.963212 | 50 | 0.347429 |

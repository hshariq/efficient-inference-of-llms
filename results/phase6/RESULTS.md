# Phase 6 — Final Results (dissertation source)

> **Canonical** citeable Phase 6 numbers. Spec: `PHASE6_EVAL.md`.  
> Decisions / narrative: `docs/PHASE6_DECISIONS_LOG.md`.  
> Short ablation pointer: `ABLATION_C1_2026-07-26.md` (tables live **here only**).

**Status (2026-07-30):** **6f burst matrix complete.** Per-tier on burst JSONLs, quality (6h), charts (6i), aggregate tables (6j) still pending.

---

## 1. Setup (cite in methodology)

| Item | Value |
|------|--------|
| Model | `meta-llama/Llama-3.1-8B-Instruct` |
| Engine | vLLM **0.11.0** (V1) |
| Primary metric | **TSR** = `cached_tokens / prompt_tokens` (harness; proxy `/metrics` cross-check for Optimizer) |
| Secondary | mean TTFT (client-side, includes hold), p50/p90/p99 latency, hit rate, throughput |
| Corpus | Simulated **University of Leeds Student Assistant** — **not** real student data |
| Docs | 8 synthetic university-style RAG docs |
| Phrasing | LMSYS-mined (ShareGPT/MOSS deferred) — no hand-authored paraphrases |
| Tasks | Catalogue: mainly `summarize_3_bullets` (+ `extract_entities` where matched) |
| Workloads | `burst_ablation.jsonl` (200) · `burst_full.jsonl` (2000 = 400 exact / 800 semantic / 300 BoN / 500 lone_wolf) |
| Concurrency | Ablation c=1 · Burst **c=8** (BoN groups always co-dispatched) |
| Hard gate | `probe_cached_tokens` PASS required for apc/optimizer/gptcache |
| Vanilla note | vLLM 0.11 **defaults APC on** — must launch with `--no-enable-prefix-caching` |

**Systems**

| Label | Stack |
|-------|--------|
| vanilla | vLLM, APC **off** (`--no-enable-prefix-caching`) |
| apc | vLLM, APC **on**, direct `:8000` |
| gptcache | In-process semantic **answer** cache → upstream `:8000` (MiniLM similarity ≥ 0.92) |
| optimizer | Proxy `:9000` rewrite on, hold off, embed off\|minilm |
| optimizer_hold | Same + admission hold on (`hold_ms=50`, `batch_peers=8`) |

**Honesty rules**

- Cite only rows marked **OK**. Reject warm KV (`cached_tokens_call1` ≈ 96 → TSR ≈ 0.995).
- Soft crumb (`call1` 0–48 after probe) noted; prefer cold.
- APC/optimizer `hit_rate=1.0` means `cached_tokens > 0` (often template crumbs) — **not** full-prompt hit rate. **Claim TSR.**
- GPTCache is **answer memoization**, not KV prefix reuse — different mechanism.
- No TTFT-win claim unless data shows one. TSR↑ / TTFT flat is expected and valid.
- Do **not** headline TBT/TPOT (prefill-scope system).

---

## 2. Headline results (use in dissertation tables)

### 2.1 Burst 2k @ c=8 — main comparison

| System | TSR | mean TTFT (ms) | p50 lat (ms) | p90 | p99 | File |
|--------|-----|----------------|--------------|-----|-----|------|
| **vanilla** | **0.000** | 308 | 2410 | 2961 | 3425 | `burst_vanilla.jsonl` |
| **apc** | **0.775** | 122 | 1555 | 2342 | 2762 | `burst_apc.jsonl` |
| **optimizer** (hold off, embed off) | **0.780** | 126 | 1641 | 2272 | 2738 | `burst_optimizer_holdoff_embedoff.jsonl` |
| gptcache | 0.862 | 111 | 110 | 1523 | 2866 | `burst_gptcache_c8.jsonl` |

**One-paragraph takeaway:** Without APC, TSR is zero and latency is highest. APC saves ~77.5% of prompt tokens and cuts median latency vs vanilla. Optimizer rewrite-only matches APC on aggregate TSR (~0.780) with similar TTFT — on this catalogue/mix, most savings are already APC’s. GPTCache posts higher TSR and much lower p50 via answer reuse (not prefix KV); treat as comparator, not “better APC.”

### 2.2 Optimizer 2×2 ablation (burst) — latency cost, flat TSR

| Hold | MiniLM | TSR | mean TTFT (ms) | p50 lat (ms) | n_ok | File | Role |
|------|--------|-----|----------------|--------------|------|------|------|
| off | off | **0.780** | 126 | 1641 | 2000/2000 | `burst_optimizer_holdoff_embedoff.jsonl` | **Main Optimizer row** |
| on (50 ms) | off | 0.780 | **200** | 1698 | 2000/2000 | `burst_optimizer_holdon_embedoff.jsonl` | Hold tax; max_batch@50 cell |
| off | on | 0.780 | **608** | 1813 | **1999**/2000 | `burst_optimizer_holdoff_minilm.jsonl` | MiniLM tax (1 error) |
| on | on | 0.780 | **639** | 1851 | 2000/2000 | `burst_optimizer_holdon_minilm.jsonl` | Worst latency |

**Takeaway:** Hold and MiniLM do **not** raise TSR on this workload; they add client-side cost (MiniLM dominates). Prefer embed-off for main claims.

### 2.3 Ablation @ c=1 (200 req) — supports same story at small scale

| System | TSR | mean TTFT (ms) | p50 lat (ms) |
|--------|-----|----------------|--------------|
| vanilla | 0.00 | 101 | 1443 |
| apc | 0.693 | 98 | 1444 |
| optimizer (citeable cells) | 0.700 | 126–165 | 1454–1507 |
| gptcache | 0.857 | 25 | 15 |

### 2.4 Per-tier TSR @ c=1 (do not rely on aggregate alone for Optimizer vs APC)

| System | exact | **semantic** | best_of_n | lone_wolf | aggregate |
|--------|------:|-------------:|----------:|----------:|----------:|
| vanilla | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| apc | 0.974 | **0.461** | 0.964 | 0.379 | 0.693 |
| optimizer | 0.976 | **0.475** | 0.963 | ~0.35 | 0.700 |
| gptcache | 0.975 | 0.759 | 1.000 | 0.000 | 0.857 |

**Optimizer − APC on semantic only: +0.014.** No buried headline win in the aggregate gap. Burst per-tier still TODO (`aggregate --jsonl` on `burst_*.jsonl`).

### 2.5 Why APC already has TSR 0.461 on “semantic” (important for write-up)

Audited `c1_apc.jsonl` semantic tier (n=80). The **0.461 mean is bimodal**, not “APC matches varied phrasing”:

| Bin (cached/prompt) | Count (APC) | Interpretation |
|---------------------|------------:|----------------|
| &lt;5% | 38 | Cold / crumb only (~16 toks) — instruction differs → **no** long prefix match |
| 5–25% | 6 | Partial |
| ≥75% | 36 | Near-full (~2000/2005) — **exact re-occurrence** of same phrasing+doc in the tier |

- **Median** APC semantic ratio ≈ **0.05** (near zero); the **mean** is pulled up by exact repeats.
- Optimizer cold floor is higher (~80 toks from canonical prefix vs ~16 crumbs) but the hot half is already saturated for both → aggregate gap stays ~+0.014.
- So this is **not** primarily “APC matching the shared document mid-prompt despite different instructions” (classic APC is prefix-from-start; different instruction tokens break that). It **is** largely: the semantic tier **cycles a limited mined phrasing set**, so many “semantic” rows are exact duplicates of earlier ones → APC wins without rewrite.

**Dissertation framing:** Phase 4 hypothesis (“shared instruction / different data = Optimizer win”) was **tested and only weakly supported** on this workload. Root cause leans toward **workload construction** (semantic tier not adversarial enough at token level), not a failed harness. Optional follow-up: semantic-only adversarial slice (highly varied mined instructions, **short** distinct docs, **no** exact re-cycles) before locking 6h–6j.

---

## 3. Full burst run log (all cells)

Nodes/jobs: gpu020 `6913635` (APC/GPTCache) · gpu001 `6920808` (Optimizer 2×2) · gpu005 (vanilla).

| System | Config | n | TSR | TTFT | p50/p90/p99 | hit_rate | call1 | Cite? | Artefact |
|--------|--------|---|-----|------|-------------|----------|-------|-------|----------|
| apc | APC on, direct | 2000/2000 | 0.775 | 122 | 1555/2342/2762 | 1.0* | 16 | **OK** | `burst_apc.jsonl` |
| gptcache | c=1 (MiniLM race workaround) | 2000/2000 | 0.870 | 51 | 21/1419/1574 | 0.662 | 16 | OK backup | `burst_gptcache.jsonl` |
| gptcache | **c=8 aligned** | 2000/2000 | 0.862 | 111 | 110/1523/2866 | 0.656 | 48 | **OK prefer** | `burst_gptcache_c8.jsonl` |
| optimizer | hold off, embed off | 2000/2000 | 0.780 | 126 | 1641/2272/2738 | 1.0* | 16 | **OK** | `burst_optimizer_holdoff_embedoff.jsonl` |
| optimizer_hold | hold on 50, embed off | 2000/2000 | 0.780 | 200 | 1698/2387/2821 | 1.0* | **0** | **OK cold** | `burst_optimizer_holdon_embedoff.jsonl` |
| optimizer | hold off, minilm | 1999/2000 | 0.780 | 608 | 1813/3371/5175 | 1.0* | 16 | **OK** note 1 err | `burst_optimizer_holdoff_minilm.jsonl` |
| optimizer_hold | hold on, minilm | 2000/2000 | 0.780 | 639 | 1851/3309/4683 | 1.0* | 16 | **OK** | `burst_optimizer_holdon_minilm.jsonl` |
| vanilla | `--no-enable-prefix-caching` | 2000/2000 | 0.000 | 308 | 2410/2961/3425 | 0.0 | 0 | **OK** | `burst_vanilla.jsonl` |

\* APC/optimizer hit_rate: weak signal. GPTCache hit_rate: real answer-cache hits.

**Smoke (not for tables):** `smoke_apc_gpu020.jsonl` TSR 0.507 n=7; `smoke_gptcache_c8.jsonl` TSR 0 (tiny unique mix @ c=8).

---

## 4. Ablation @ c=1 detail (2026-07-26 · gpu012 · job `6882827`)

Workload: `burst_ablation.jsonl` (200 = 40/80/30/50).

### Citeable whole-workload

| System | TSR | TTFT | p50 | call1 | File |
|--------|-----|------|-----|-------|------|
| vanilla | 0.00 | 101 | 1443 | 0 | `c1_vanilla.jsonl` |
| apc | 0.693 | 98 | 1444 | — | `c1_apc.jsonl` |
| gptcache | 0.857 | 25 | 15 | — | `c1_gptcache.jsonl` |
| optimizer hold-on embed-off | 0.700 | 146 | 1506 | 0 | `c1_optimizer_hold.jsonl` |
| optimizer hold-off minilm | 0.700 | 126 | 1454 | 16 | `c1_optimizer_holdoff_minilm.jsonl` |
| optimizer hold-on minilm | 0.700 | 165 | 1507 | 0 | `c1_optimizer_holdon_minilm.jsonl` |

### Why three optimizer configs all showed TSR 0.700 — benign

| Config | rewrite/bypass | MiniLM |
|--------|----------------|--------|
| hold-on embed-off | 150/50 | never |
| hold-off / hold-on minilm | 151/49 | **1×** (`lone-156` → `extract_entities`) |

Semantic: 80/80 rewrite by **rules alone**. Identical aggregate TSR expected; hold only moves TTFT.

### Do not cite

- Warm KV runs with **TSR ≈ 0.995** and `cached_tokens_call1: 96` (e.g. early `c1_optimizer.summary.json`).

### Still missing (c=1 only)

- Cold hold-off + embed-off at c=1 (covered at burst scale as main Optimizer row).

---

## 5. Operational notes (methods appendix)

| Issue | Resolution |
|-------|------------|
| GPTCache `requires sentence-transformers` | Package present; real failure = meta-tensor / GPU clash / c=8 race |
| Fix | `device=cpu`, `low_cpu_mem_usage=False`, encoder lock + eager init (`src/eval/backends.py`) |
| Vanilla still showing APC | vLLM 0.11 **default APC on**; use `--no-enable-prefix-caching` |
| Proxy MiniLM vs vLLM GPU | Start proxy with `CUDA_VISIBLE_DEVICES=` when embed=minilm |
| Gate key | Upstream URL fingerprint (`localhost:8000`), not Slurm hostname |
| Hold default | `OPTIMIZER_ADMISSION_HOLD_MS=50` for realistic burst (Phase 5 open item) |

---

## 6. Claims you can / cannot make

**Can say**

1. Vanilla TSR=0 vs APC/Optimizer ~0.78 → prefix caching yields large token savings on this workload.
2. Optimizer rewrite-only ≈ APC on **aggregate** TSR; not a large aggregate win over stock APC here.
3. On the designed win condition (semantic tier), Optimizer−APC is only **+0.014**; hypothesis weakly supported.
4. APC’s semantic mean TSR ~0.46 is **bimodal** (median ~0.05): mostly crumbs on first-of-kind phrasing, near-full on **exact re-cycles** of mined strings — not proof that APC defeats paraphrase via mid-doc match.
5. Hold raises TTFT; does not raise TSR.
6. MiniLM adds large latency, negligible TSR.
7. GPTCache is answer memoization — different mechanism.
8. Strongest empirical contribution: **TSR vs TTFT decoupling** (vanilla vs APC/Optimizer).

**Cannot say**

1. Optimizer Box beats APC (data do not support this as a headline).
2. TTFT win for Optimizer vs APC.
3. APC `hit_rate=1.0` = 100% exact full-prompt hits.
4. GPTCache is “better prefix caching.”
5. Warm-KV TSR≈0.995 runs.

---

## 7. Artefact index

| Path | Role |
|------|------|
| `burst_vanilla.jsonl` + `.summary.json` | No-APC baseline |
| `burst_apc.jsonl` | APC baseline |
| `burst_gptcache.jsonl` / `burst_gptcache_c8.jsonl` | GPTCache c=1 / c=8 |
| `burst_optimizer_holdoff_embedoff.jsonl` | Main Optimizer |
| `burst_optimizer_holdon_embedoff.jsonl` | Hold ablation + max_batch@50 |
| `burst_optimizer_holdoff_minilm.jsonl` | MiniLM ablation (1 fail) |
| `burst_optimizer_holdon_minilm.jsonl` | Hold+MiniLM |
| `c1_*.jsonl` | Ablation @ c=1 |
| `aggregate_per_tier.{md,csv}` | c=1 per-tier export |
| `.cached_tokens_probe_ok.json` | Gate marker (ephemeral per job) |

Regenerate per-tier:

```bash
PYTHONPATH=. python -m src.eval.aggregate --jsonl \
  results/phase6/burst_vanilla.jsonl \
  results/phase6/burst_apc.jsonl \
  results/phase6/burst_gptcache_c8.jsonl \
  results/phase6/burst_optimizer_holdoff_embedoff.jsonl \
  results/phase6/burst_optimizer_holdon_embedoff.jsonl
```

---

## 8. Remaining Phase 6 work

| Step | Status |
|------|--------|
| 6a–6e scaffold / c=1 | Done |
| **6f burst + hold=50** | **Done** |
| Explain semantic APC 0.461 | **Done** (§2.5 — bimodal / exact re-cycles) |
| Burst per-tier TSR | TODO |
| max_batch disposition counts @ hold=50 | TODO |
| MiniLM 1-error row | JSONL not local yet — `grep` error on Aire before citing cell 3 as fully clean |
| **Optional: adversarial semantic-only probe** | **Workload ready** — run on Aire (see §9) |
| 6h quality spot-check | Pending |
| 6i six charts + captions | Pending |
| 6j aggregate dissertation tables | Pending |

### Recommended next experiment (before 6h–6j lock-in)

**Not** a full matrix redo. One targeted probe — **§9**.

---

## 9. Adversarial semantic-only probe (ready to run)

**Purpose:** Stress Phase 4 win condition without exact re-cycles that inflated APC semantic TSR in §2.5.

| Design choice | Value |
|---------------|--------|
| Workload | `workloads/phase6/adversarial_semantic.jsonl` (**83** req) |
| Meta | `adversarial_semantic.meta.json` |
| Doc | `docs/doc_adversarial_short.txt` (~795 chars, shared) |
| Instructions | Unique LMSYS-mined, **rules-matched** `summarize_3_bullets` only |
| Exact repeats | **None** (deduped prompts) |
| Builder | `python -m src.eval.build_adversarial_semantic` |

**Systems (only two):** `apc` vs `optimizer` (hold **off**, embed **off**). Cold vLLM between runs.

**How to read the outcome**

| Result | Interpretation |
|--------|----------------|
| Optimizer TSR ≫ APC (APC median ~crumbs) | Hypothesis OK under stress; main matrix was workload-limited |
| Still flat | Design insight: rewrite adds little even when adversarial; discuss honestly |

**Also report:** histogram of `cached_tokens/prompt_tokens` (median + bins), not only mean TSR.

### Aire commands

```bash
cd ~/efficient-inference-of-llms && git pull
# rebuild if needed:
PYTHONPATH=. python -m src.eval.build_adversarial_semantic --limit 100

# 1) APC on (start_on_gpu.sh), cold, probe PASS
PYTHONPATH=. python -m src.eval.probe_cached_tokens
PYTHONPATH=. python -m src.eval.run --system apc \
  --workload workloads/phase6/adversarial_semantic.jsonl \
  --concurrency 1 \
  --out results/phase6/adv_sem_apc.jsonl

# 2) restart vLLM cold + re-probe, then proxy hold-off embed-off
OPTIMIZER_REWRITE_MODE=on OPTIMIZER_TTL_MODE=off OPTIMIZER_EMBEDDING_BACKEND=off \
  bash src/proxy/start_proxy.sh
PYTHONPATH=. python -m src.eval.run --system optimizer \
  --workload workloads/phase6/adversarial_semantic.jsonl \
  --concurrency 1 \
  --out results/phase6/adv_sem_optimizer.jsonl
```

Prefer **c=1** so the first→later cache story is readable (no concurrent miss storm). Paste both summaries here.

Quick local histogram after copy-back:
```bash
PYTHONPATH=. python -m src.eval.aggregate --jsonl \
  results/phase6/adv_sem_apc.jsonl \
  results/phase6/adv_sem_optimizer.jsonl
```


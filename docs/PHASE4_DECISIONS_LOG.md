# Phase 4 — Decisions & Results Log

Running lab notebook for dissertation methodology / evaluation chapters.
Separate from the Phase 4 spec (`PHASE4_SEMANTIC.md`). Artefacts: `results/phase4/`.

**Last updated:** 2026-07-23 — **Phase 4 CLOSED**

---

## Executive summary (read this first)

Phase 4 builds **schema tagging + optional embed fallback + block-aligned canonical
prefix rewrite** in the Phase 2 proxy so vLLM APC can hit on
**shared-instruction / different-document** traffic.

### Verdict

**Phase 4 is complete.** Implementation, tagging ablation, embed VRAM, APC mechanism
smokes (incl. long+warmup control), and live MiniLM hard-prompt / bypass are all done.
Nothing Phase-4-blocking remains. Next work is **Phase 5 (TTL)**.

### What was delivered

| Area | Outcome |
|------|---------|
| **Implementation** | Parts 0–4 code complete (schema, Part 2 features, MiniLM + Qwen embed, ablation harness, proxy rewrite path). |
| **Rules / Part 1–2** | Local pytest (110+); summarize 18/18; Part 2 metadata-only (catalogue keyed by `Task`). |
| **Alignment** | Chat-template–aware pad; dummies `QQQ_…` / `ZZZ_…`. Model: `meta-llama/Llama-3.1-8B-Instruct`. |
| **4-way tagging ablation** | n=113 Aire; MiniLM preferred trade-off; default embed **`off`**. |
| **APC smoke** | Mechanism OK; long+warmup **off A/B ≈ 1.05×** (clean control); on/off TTFT similar at ~50ms floor → **TSR in Phase 6**. |
| **Live MiniLM** | Hard prompt → `canonical_prefix_embed`; out-of-catalogue → embed try then **bypass**. |

### Defaults (unchanged)

- `OPTIMIZER_REWRITE_MODE=on`
- `OPTIMIZER_EMBEDDING_BACKEND=off` (opt-in `minilm` when wanted)
- Trimmer / TTL / Token Saving Ratio / full baselines → **not Phase 4**

---

## Status table

| Layer | State (2026-07-23) |
|-------|---------------------|
| **Implementation** | **Done** |
| **Rules / Part 1–2** | **Done** |
| **Part 3 embeddings (ablation + VRAM)** | **Done** (Aire) |
| **Part 4 tagging ablation** | **Done** — `results/phase4/ablation_*` |
| **APC smoke (short + long/warmup)** | **Done** — `results/phase4/smoke_apc_*` |
| **Live MiniLM hard / bypass** | **Done** (gpu018) |
| **Token Saving Ratio / full eval** | **Phase 6** |
| **TTL** | **Phase 5** |

---

## Request path (one sentence)

Client → `POST /v1/chat/completions` (`app.py`) → `rewrite_request` (tag rules → optional embed → bypass or catalogue system + align) → vLLM `:8000`.

---

## Part 0 — Setup (2026-07-19)

**Standing design constraints (locked):**
- Rules are the **default** classifier; embeddings are **fallback-only** on
  low-confidence / `UNKNOWN` task — never a primary classifier.
- No LLM system-prompt classification; no hosted third-party APIs; local weights only.
- No open-ended label generation — fixed enumerated fields only.
- Negation / exclusion is **rule-based only**.
- Part 2 multi-facet fields do **not** fork the catalogue (Task-only selection).

---

## Part 1 — Schema hygiene

**Regex:** expanded summarize patterns (incl. British `summarised` / `summary` / bullets).  
**Tie-break:** explicit `TASK_PRIORITY` — summarize before extract (workload prior).  
**Tokenizer:** same HF id as serving — `meta-llama/Llama-3.1-8B-Instruct`.  
**Length buckets:** short &lt;128 / medium &lt;1024 / long ≥1024 (logging only).

**Coverage:** 18/18 summarize paraphrases → `summarize_3_bullets` (`tests/test_tag_coverage.py`).

**Limitation (accepted):** task-level negation (“Don’t summarize — extract”) only partially handled.

---

## Part 2 — Richer schema + exclusion metadata

| Field | Values | Role |
|-------|--------|------|
| `entity_focus` | team / individual / unknown | Metadata |
| `action_type` | analysis / retrieval / generation / unknown | Metadata |
| `excluded_terms` | captured phrases | Metadata; **never** bumps confidence |

**Decision:** catalogue not forked on these fields.  
**Coverage:** Part 2 fixtures 100% on authored set; pytest 110+ with tag coverage.  
**Honest limit:** authored consistency ≠ uncurated generalization → Phase 6.

---

## Part 3 — Embedding fallbacks

| Backend | Model | Gate |
|---------|-------|------|
| MiniLM | `sentence-transformers/all-MiniLM-L6-v2` | UNKNOWN or conf &lt; threshold |
| Qwen3 | `Qwen/Qwen3-Embedding-0.6B` | Same |

Exemplars + max cosine; never used for exclusion.  
**Default backend: `off`.** Prefer **MiniLM** if enabling embed.

**Alignment fix:** pad dummies `QQQ_…` vs `ZZZ_…` (not `DOCUMENT_A/B`).

---

## Part 4 — Tagging ablation (Aire gpu013, 2026-07-22)

Harness: `python -m src.proxy.ablation.run_tag_ablation`  
Shared set **n=113** (no vLLM). Logs: `results/phase4/ablation_*.{txt,jsonl}`.

| Condition | Bypass rate | Mean rule_ms | Mean embed_ms | Embed-used | VRAM |
|-----------|-------------|--------------|---------------|------------|------|
| `rules_only` | 20.4% | (rules) | 0.00 | 0.0% | n/a |
| `rules_plus_features` | 20.4% | ~6–27 | 0.00 | 0.0% | n/a |
| `embed_minilm` | **10.6%** | 6.59 | 0.76 | 9.7% | **95 MiB** |
| `embed_qwen3` | **0.0%** | 5.76 | 4.27 | 20.4% | **2281 MiB** |

**Decision:** MiniLM = preferred opt-in fallback; Qwen = max coverage / expensive; default stays `off`.

---

## Live APC smoke (Aire, 2026-07-23)

Script: `PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py`  
(proxy `:9000`, vLLM Llama-3.1-8B-Instruct + APC).  
Case: paraphrased summarize instructions + **different** documents.

### Cold rewrite-on (gpu012, short docs)

| | TTFT | Notes |
|--|------|--------|
| Doc A | ~1.884s | Cold-ish |
| Doc B | ~0.043s | Warm |
| **A/B** | **~43.8×** | Anecdotal cold-start; clean bullets |

### Warm short-doc pair (gpu018) — confounded by warmup

| Mode | A/B | Note |
|------|-----|------|
| off / on | ~9–10× | Not diagnostic |

### Strong smoke: `--long --warmup` (gpu018) — primary controlled pair

Artefacts: `results/phase4/smoke_apc_long_off.txt`, `smoke_apc_long_on.txt`.  
`cached_tokens` not reported by this vLLM OpenAI usage payload.

| Mode | A TTFT | B TTFT | A/B | prompt_tokens A/B | Output |
|------|--------|--------|-----|-------------------|--------|
| **off** | 0.053s | 0.050s | **1.05×** | 405 / 395 | Preamble |
| **on** | 0.055s | 0.052s | **1.05×** | 435 / 424 | Catalogue bullets only |

**Interpretation:**
- Off control **verified** (A/B ≈ 1 after warmup) — earlier large off ratios were engine warmup.
- On **mechanism verified** (same system + style); TTFT on≈off at ~50ms floor on L40S for ~400-token prompts.
- **Quantitative APC / Token Saving Ratio → Phase 6.**

---

## Live MiniLM hard-prompt + bypass (gpu018, 2026-07-23)

Proxy: `OPTIMIZER_REWRITE_MODE=on`, `OPTIMIZER_EMBEDDING_BACKEND=minilm`.

### Rescue (rules weak → embed → rewrite)

Prompt: `I need a 3-bullet overview of the sales team performance.` (+ short doc)

| Field | Value |
|--------|--------|
| `reason` | `canonical_prefix_embed` |
| `embed_used` | `True` |
| `catalogue_task` | `summarize_3_bullets` |
| `embed_ms` (first load) | ~2624 ms |
| Output | Bullet summary (as expected) |

### Safety bypass (out of catalogue)

Prompt: `Generate a draft email based on the notes.`

| Field | Value |
|--------|--------|
| `action` | `bypass` |
| `task` | `unknown` |
| `embed_ms` | ~4.3 ms (encode attempted) |
| `embed_used` | `False` (no score ≥ min) |
| Upstream | Original text → vLLM (“I don't see any notes…”) |

**Decision confirmed:** embed is fallback-only; failed match does not force a wrong catalogue task.

---

## Locked decisions (quick reference)

1. Rules first; embed fallback-only; default embed **`off`**.  
2. If embed on → prefer **MiniLM** over Qwen for live proxy.  
3. Catalogue keyed by **Task** only (summarize / extract).  
4. Exclusion = rules only; does not affect confidence.  
5. Align on **rendered** chat-template span.  
6. Low confidence / UNKNOWN after all stages → **bypass**.  
7. Trimmer out of scope; light normalize only.

---

## Artefacts checklist

| Path | Contents |
|------|----------|
| `results/phase4/ablation_rules_only.txt` | Rules-only tee |
| `results/phase4/ablation_rules_plus_features.{txt,jsonl}` | Part 2 features |
| `results/phase4/ablation_embed_minilm.{txt,jsonl}` | MiniLM ablation |
| `results/phase4/ablation_embed_qwen3.{txt,jsonl}` | Qwen ablation |
| `results/phase4/smoke_apc_rewrite_*.txt` | Short warm smokes |
| `results/phase4/smoke_apc_long_{on,off}.txt` | Long + warmup smokes |
| `results/phase4/smoke_minilm_hard_prompt.txt` | Optional tee of hard-prompt client output |
| `docs/PHASE4_DECISIONS_LOG.md` | This file |
| `PHASE4_SEMANTIC.md` | Spec / design |
| `src/proxy/smoke_rewrite_apc.py` | Supports `--long --warmup` |

---

## What’s next (Phase 4 closed)

### Phase 4 remaining

**None.** All planned and optional Phase 4 checks are done.

### Later phases

| Item | Phase |
|------|-------|
| **TTL / starvation escape** | **5** ← start here next |
| Token Saving Ratio, cache hit rate, full workload | **6** |
| Uncurated / ShareGPT-style generalization | **6** |
| Baselines (e.g. GPTCache), multi-seed tables | **6** |
| Trimmer | Future work |
| Catalogue fork on Part 2 facets | Future ablation |

### Suggested next session

1. Commit/push any remaining Aire `results/phase4/*` + this log from Windows.  
2. Open / draft **Phase 5 TTL** design (priority escalation when a request waits too long).  
3. Keep proxy defaults: rewrite `on`, embed `off` unless testing fallback.

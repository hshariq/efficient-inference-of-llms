# Phase 4 — Decisions & Results Log

Running lab notebook for dissertation methodology / evaluation chapters.
Separate from the Phase 4 spec (`PHASE4_SEMANTIC.md`). Artefacts: `results/phase4/`.

**Last updated:** 2026-07-23

---

## Executive summary (read this first)

Phase 4 builds **schema tagging + optional embed fallback + block-aligned canonical
prefix rewrite** in the Phase 2 proxy so vLLM APC can hit on
**shared-instruction / different-document** traffic.

### What was delivered

| Area | Outcome |
|------|---------|
| **Implementation** | Parts 0–4 code complete (schema, Part 2 features, MiniLM + Qwen embed, ablation harness, proxy rewrite path). |
| **Rules / Part 1–2** | Local pytest coverage (110+); summarize paraphrases 18/18; Part 2 fields metadata-only (catalogue still keyed by `Task`). |
| **Alignment** | Chat-template–aware pad; dummy docs `QQQ_…` / `ZZZ_…` (fixed false LCP from shared `DOCUMENT_` stem). Model id locked: `meta-llama/Llama-3.1-8B-Instruct`. |
| **4-way tagging ablation (Aire)** | n=113; MiniLM preferred cost/coverage trade-off; default embed still **`off`**. |
| **Live APC smoke (Aire)** | Rewrite applies identical canonical system across paraphrased prompts + different docs; quality spot-check OK. Cold rewrite-on showed large TTFT A/B; warm on vs off ratios similar (see caveats). |

### Defaults (unchanged)

- `OPTIMIZER_REWRITE_MODE=on`
- `OPTIMIZER_EMBEDDING_BACKEND=off` (enable `minilm` only when you want fallback)
- Trimmer / TTL / Token Saving Ratio / full baselines → **not Phase 4**

### Phase 4 status verdict

**Core Phase 4 is complete** for the dissertation build: rewrite path works end-to-end;
tagging ablations and embed VRAM measured; APC smoke verified mechanism + spot quality.

**Optional polish left in Phase 4** (nice-to-have, not blocking Phase 5):
see [What’s left](#whats-left--phase-4-vs-later) below.

---

## Status table

| Layer | State (as of 2026-07-23) |
|-------|---------------------------|
| **Implementation** | Parts 0–4 **code complete**. |
| **Verification (rules / Part 1–2)** | **Done** — local tests + Aire rules rows in ablation. |
| **Verification (Part 3 embeddings)** | **Done on Aire** — MiniLM + Qwen3 load, fallback, VRAM. |
| **Verification (Part 4 tagging ablation)** | **Done on Aire** — all four conditions; `results/phase4/ablation_*`. |
| **Verification (rewrite + APC smoke)** | **Done on Aire** — mechanism + cold ~44× on-path; warm on/off caveat logged; `results/phase4/smoke_apc_*` when committed. |
| **Token Saving Ratio / full eval** | **Phase 6** — not claimed from Phase 4 smoke. |

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

### Cold rewrite-on (gpu012, first clean on-path)

| | TTFT | Notes |
|--|------|--------|
| Doc A | ~1.884s | Cold-ish |
| Doc B | ~0.043s | Warm |
| **A/B** | **~43.8×** | Same canonical system; clean bullets (no preamble) |

### Warm control pair (gpu018, after unrelated warmup)

| Mode | A TTFT | B TTFT | A/B | Output style |
|------|--------|--------|-----|--------------|
| `REWRITE_MODE=off` | ~0.391s | ~0.043s | ~9.2× | Preamble (“Here's a summary…”) |
| `REWRITE_MODE=on` | ~0.414s | ~0.043s | ~9.6× | Catalogue bullets only |

**Interpretation (honest):**
- **Mechanism verified:** on applies identical block-aligned catalogue system; off does not (preamble vs bullets).
- **Ideal TTFT story** (off ≈1×, on ≫1× after warmup) is **not** cleanly shown by this tiny warm smoke — B hits a ~40ms floor either way; off after cold vLLM restart was also confounded by engine warmup (~36×).
- **Token Saving Ratio** and robust APC quantification → **Phase 6**.
- Smoke `LLM output[:120]` truncates display; third bullet may exist beyond the cut.

Artefacts (when present): `results/phase4/smoke_apc_rewrite_off.txt`, `smoke_apc_rewrite_on.txt`.

---

## Locked decisions (quick reference)

1. Rules first; embed fallback-only; default embed **`off`**.  
2. If embed on → prefer **MiniLM** over Qwen for live proxy.  
3. Catalogue keyed by **Task** only (two prefixes: summarize / extract).  
4. Exclusion = rules only; does not affect confidence.  
5. Align on **rendered** chat-template span; pad trailer policy in `align.py`.  
6. Low confidence / UNKNOWN → **bypass** (identity body to vLLM).  
7. Trimmer out of scope; light normalize only.

---

## Artefacts checklist

| Path | Contents |
|------|----------|
| `results/phase4/ablation_rules_only.txt` | Rules-only tee |
| `results/phase4/ablation_rules_plus_features.{txt,jsonl}` | Part 2 features |
| `results/phase4/ablation_embed_minilm.{txt,jsonl}` | MiniLM fallback |
| `results/phase4/ablation_embed_qwen3.{txt,jsonl}` | Qwen fallback |
| `results/phase4/smoke_apc_rewrite_*.txt` | Live TTFT smokes (commit from Aire if not yet) |
| `docs/PHASE4_DECISIONS_LOG.md` | This file |
| `PHASE4_SEMANTIC.md` | Spec / design |

---

## What’s left — Phase 4 vs later

### Still optional inside Phase 4 (not blocking)

- [x] Commit smoke tee files from Aire (user reported done 2026-07-23).
- [ ] Stronger APC smoke: `smoke_rewrite_apc.py --long --warmup` on vs off (see script); tee to `results/phase4/smoke_apc_long_{on,off}.txt`.
- [ ] Optional: live proxy with `OPTIMIZER_EMBEDDING_BACKEND=minilm` on a bypass-prone prompt (ablation already covers tagging).

### Explicitly **not** Phase 4 (do next phases)

| Item | Phase |
|------|-------|
| TTL / starvation escape | **5** |
| Token Saving Ratio, cache hit rate, full workload | **6** |
| Uncurated / ShareGPT-style generalization | **6** |
| Baselines (e.g. GPTCache), multi-seed tables | **6** |
| Trimmer | Future work |
| Catalogue fork on Part 2 facets | Future ablation |

### Suggested next move after closing Phase 4

Start **Phase 5 (TTL)** when ready; keep proxy defaults as above for any further APC work.

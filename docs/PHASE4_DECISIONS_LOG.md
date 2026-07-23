# Phase 4 — Decisions & Results Log

Running lab notebook for dissertation methodology / evaluation chapters.
Separate from the Phase 4 spec (`PHASE4_SEMANTIC.md`). Artefacts: `results/phase4/`.

**Last updated:** 2026-07-23 — **implementation complete; APC performance still open**

---

## Executive summary (read this first)

Phase 4 builds **schema tagging + optional embed fallback + block-aligned canonical
prefix rewrite** in the Phase 2 proxy so vLLM APC *can* hit on
**shared-instruction / different-document** traffic.

### Verdict

**Implementation / plumbing: done.** Parts 0–4 code, tagging ablation, embed VRAM,
rewrite path, MiniLM live hard-prompt + bypass are verified.

**APC performance benefit: not yet shown.** At ~400 prompt tokens, rewrite-on and
rewrite-off give the same warm TTFT A/B (~1.05×). That test cannot distinguish
“cache reuse helping” from “fixed overhead dominating prefill.” Treat speed claims
as **unverified** until RAG-scale (~multi-thousand token) smokes (or Phase 6 TSR)
show a gap. Do **not** cite the long/warmup smoke as evidence that the mechanism
saves latency.

**Gate before Phase 5:** reframe (this file) + Qwen draft-email sanity + optional
`--rag-scale` smoke on Aire.

### What was delivered

| Area | Outcome |
|------|---------|
| **Implementation** | Parts 0–4 code complete. |
| **Rules / Part 1–2** | Local pytest (110+); Part 2 metadata-only. |
| **Alignment** | Chat-template pad; model `meta-llama/Llama-3.1-8B-Instruct`. |
| **4-way tagging ablation** | n=113; MiniLM preferred cost/coverage; default embed **`off`**. |
| **APC smoke (~400 tok)** | **Plumbing** OK (identical catalogue system + style). **Perf** null vs off at this scale. |
| **Live MiniLM** | Hard prompt → embed rewrite; out-of-catalogue → bypass. |

### Defaults (unchanged)

- `OPTIMIZER_REWRITE_MODE=on`
- `OPTIMIZER_EMBEDDING_BACKEND=off`
- Trimmer / TTL / TSR → not Phase 4

---

## Status table

| Layer | State (2026-07-23) |
|-------|---------------------|
| **Implementation** | **Done** |
| **Rules / Part 1–2** | **Done** |
| **Part 3 embeddings (ablation + VRAM)** | **Done** (Aire) |
| **Part 4 tagging ablation** | **Done** |
| **Rewrite plumbing (canonical prefix)** | **Done** |
| **APC latency benefit (~400 tok smoke)** | **Not detected** — see below |
| **APC latency benefit (RAG-scale)** | **Pending** — `--rag-scale` on Aire |
| **Qwen 0% bypass sanity** | **Pending / in progress** — draft-email probe |
| **Token Saving Ratio / full eval** | **Phase 6** |
| **TTL** | **Phase 5** (after gate) |

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

**Regex:** expanded summarize patterns (incl. British forms).  
**Tie-break:** `TASK_PRIORITY` — summarize before extract.  
**Tokenizer / model:** `meta-llama/Llama-3.1-8B-Instruct`.  
**Length buckets:** short &lt;128 / medium &lt;1024 / long ≥1024 (logging only).

**Coverage:** 18/18 summarize paraphrases → `summarize_3_bullets`.

**Limitation (accepted):** task-level negation only partially handled.

---

## Part 2 — Richer schema + exclusion metadata

| Field | Values | Role |
|-------|--------|------|
| `entity_focus` | team / individual / unknown | Metadata |
| `action_type` | analysis / retrieval / generation / unknown | Metadata |
| `excluded_terms` | captured phrases | Metadata; **never** bumps confidence |

**Decision:** catalogue not forked. Authored 100% ≠ generalization → Phase 6.

---

## Part 3 — Embedding fallbacks

| Backend | Model | Gate |
|---------|-------|------|
| MiniLM | `sentence-transformers/all-MiniLM-L6-v2` | UNKNOWN or conf &lt; threshold |
| Qwen3 | `Qwen/Qwen3-Embedding-0.6B` | Same `min_score` gate in code |

Exemplars + max cosine; never used for exclusion.  
**Default backend: `off`.** Prefer **MiniLM** if enabling embed.

**Prompting asymmetry (write-up note):** Qwen wraps the *query* as
`Instruct: …\nQuery:…` (model-card asymmetric retrieval); exemplars encode without
instruct. MiniLM uses plain `encode()` on both sides. The 4-way ablation is therefore
**backend weights + prompting strategy**, not a pure apple-to-apple weight swap.

**Alignment fix:** pad dummies `QQQ_…` vs `ZZZ_…`.

---

## Part 4 — Tagging ablation (Aire gpu013, 2026-07-22)

Harness: `python -m src.proxy.ablation.run_tag_ablation`  
Shared set **n=113**. Logs: `results/phase4/ablation_*.{txt,jsonl}`.

| Condition | Bypass rate | Mean rule_ms | Mean embed_ms | Embed-used | VRAM |
|-----------|-------------|--------------|---------------|------------|------|
| `rules_only` | 20.4% | (rules) | 0.00 | 0.0% | n/a |
| `rules_plus_features` | 20.4% | ~6–27 | 0.00 | 0.0% | n/a |
| `embed_minilm` | **10.6%** | 6.59 | 0.76 | 9.7% | **95 MiB** |
| `embed_qwen3` | **0.0%** | 5.76 | 4.27 | 20.4% | **2281 MiB** |

**Decision:** MiniLM = preferred opt-in fallback; Qwen = denser coverage on *this* set but costly; default stays `off`.

**Caveat — Qwen 0.0% bypass:** Do **not** cite as “perfect coverage” without the
draft-email sanity check. Same gate exists in code (`best_score < min_score → None`);
0% may mean (a) all 113 still exceeded `min_score` under Qwen+Instruct, or (b) weak
force-matches. Probe: `python -m src.proxy.ablation.probe_embed_bypass`.

---

## Live APC smoke (Aire, 2026-07-23)

Script: `PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py`

### Cold rewrite-on (gpu012, short docs)

A/B ~43.8× — anecdotal cold-start; **not** a controlled APC proof.

### Warm short-doc pair — confounded by warmup (~9–10× both modes)

### Controlled pair: `--long --warmup` (~400 prompt tokens)

Artefacts: `smoke_apc_long_{on,off}.txt`.

| Mode | A TTFT | B TTFT | A/B | prompt_tokens | Output |
|------|--------|--------|-----|---------------|--------|
| **off** | 0.053s | 0.050s | **1.05×** | ~400 | Preamble |
| **on** | 0.055s | 0.052s | **1.05×** | ~430 | Catalogue bullets |

**Honest read (gate finding):**
- Rewrite **plumbing** verified: on applies identical catalogue system; off does not (style differs).
- Off A/B ≈ 1 is a **good negative control** (warmup noise removed).
- On A/B ≈ off A/B ⇒ **no detectable TTFT benefit** at this scale. Prefill of ~400 tokens
  on L40S finishes in ~50ms; shared system span savings sit under fixed overhead.
- **Do not** claim APC latency wins from this smoke. Need `--rag-scale` (~5k-token docs)
  and/or Phase 6 Token Saving Ratio / engine cached-token metrics.

### RAG-scale smoke (pending Aire)

```bash
export OPTIMIZER_REWRITE_MODE=off   # match proxy
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --rag-scale --warmup \
  2>&1 | tee results/phase4/smoke_apc_ragscale_off.txt
# restart proxy with on, then:
export OPTIMIZER_REWRITE_MODE=on
PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --rag-scale --warmup \
  2>&1 | tee results/phase4/smoke_apc_ragscale_on.txt
```

Log TTFT A/B and prompt sizes here when available.

---

## Live MiniLM hard-prompt + bypass (gpu018, 2026-07-23)

### Rescue

`I need a 3-bullet overview…` → `canonical_prefix_embed`, `embed_used=True`,
`summarize_3_bullets` (first-load embed_ms ~2.6s).

### Safety bypass (MiniLM)

`Generate a draft email based on the notes.` → `bypass`, `embed_used=False`
(encode attempted, score below min). Upstream got original text.

---

## Locked decisions (quick reference)

1. Rules first; embed fallback-only; default embed **`off`**.  
2. If embed on → prefer **MiniLM** over Qwen for live proxy.  
3. Catalogue keyed by **Task** only.  
4. Exclusion = rules only; does not affect confidence.  
5. Align on **rendered** chat-template span.  
6. Low confidence / UNKNOWN after all stages → **bypass**.  
7. No APC **speed** claim from ~400-token smokes.

---

## Artefacts checklist

| Path | Contents |
|------|----------|
| `results/phase4/ablation_*` | 4-way tagging ablation |
| `results/phase4/smoke_apc_long_*.txt` | ~400-tok controlled smoke |
| `results/phase4/smoke_apc_ragscale_*.txt` | RAG-scale (when run) |
| `src/proxy/ablation/probe_embed_bypass.py` | Qwen/MiniLM draft-email probe |
| `docs/PHASE4_DECISIONS_LOG.md` | This file |
| `PHASE4_SEMANTIC.md` | Spec |

---

## What’s next

### Phase 4 gate (before Phase 5)

- [x] Reframe APC conclusions (this update).
- [ ] Qwen draft-email probe — record score / bypass vs force-match.
- [ ] RAG-scale `--rag-scale --warmup` on vs off on Aire — log gap or null.

### Later phases

| Item | Phase |
|------|-------|
| TTL / starvation escape | **5** (after gate) |
| Token Saving Ratio, full workload | **6** |
| Uncurated generalization | **6** |
| Trimmer | Future work |

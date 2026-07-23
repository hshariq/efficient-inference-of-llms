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
| **APC latency benefit (RAG-scale ~4.5k tok)** | **Null TTFT** (on≈off≈1.0×) — shared system ≪ unique doc; see log |
| **Qwen 0% bypass sanity** | **Force-match found** — `QWEN_SCORE_FLOOR=0.65` fix; re-probe on Aire |
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

**Caveat — Qwen 0.0% bypass (resolved 2026-07-23):** Probe
`Generate a draft email based on the notes.`:

| Backend | nearest score | @0.35 gate | Outcome |
|---------|---------------|------------|---------|
| MiniLM | 0.288 → summarize | bypass | Correct |
| Qwen3 | 0.560 → extract_entities | **rewrite** | Force-match bug |

Threshold code existed, but Qwen+Instruct scores sit higher, so 0.35 was too weak.
**Fix:** `QWEN_SCORE_FLOOR=0.65` in `qwen_backend.py` (`effective_min = max(min_score, floor)`).
Re-run `probe_embed_bypass` and (optionally) `embed_qwen3` ablation after pull — expect
bypass &gt; 0%; do **not** cite pre-fix 0% as coverage win.

**Prompting asymmetry:** Qwen `Instruct:…\nQuery:`; MiniLM plain encode.
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

### RAG-scale smoke (gpu014, 2026-07-23) — `--rag-scale --warmup`

Artefacts: `smoke_apc_ragscale_{on,off}.txt`. ~20k chars / **~4500–4650 prompt tokens**.

| Mode | A TTFT | B TTFT | A/B | prompt_tokens A/B | Output |
|------|--------|--------|-----|-------------------|--------|
| **off** | 0.389s | 0.393s | **0.99×** | 4541 / 4627 | Preamble |
| **on** | 0.403s | 0.402s | **1.00×** | 4571 / 4656 | Catalogue bullets |

**Honest read:**
- Off control still clean (A/B ≈ 1).
- On plumbing still verified (style + identical system).
- **Still no TTFT gap** at RAG body size. Expected under this catalogue design: the
  **shared** span is a short system instruction (~tens of tokens); the **unique**
  document is ~4.5k tokens. APC can skip only the short shared prefix; prefill time
  remains dominated by the long unique user body, so client TTFT barely moves.
- Implications: (1) do not claim latency wins from these smokes; (2) Phase 6 must use
  **Token Saving Ratio / cached-token counts**, not TTFT alone; (3) larger TTFT wins
  would need a much longer *shared* prefix (not just a short catalogue system), which
  is a different product choice than the current two-task catalogue.

### Gate status

- [x] Reframe APC conclusions.
- [x] Qwen draft-email probe — force-match confirmed; floor fix landed in code (re-probe on Aire).
- [x] RAG-scale smoke logged (null TTFT gap; explanation above).

Phase 5 (TTL) may proceed; APC **speed** remains a Phase 6 measurement problem.

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

- [x] Reframe APC conclusions.
- [x] Qwen draft-email probe — force-match; `QWEN_SCORE_FLOOR=0.65` (re-probe after pull).
- [x] RAG-scale smoke — null TTFT; shared system ≪ unique doc.

### Later phases

| Item | Phase |
|------|-------|
| TTL / starvation escape | **5** ← next |
| Token Saving Ratio / cached tokens (APC proof) | **6** |
| Uncurated generalization | **6** |
| Trimmer | Future work |

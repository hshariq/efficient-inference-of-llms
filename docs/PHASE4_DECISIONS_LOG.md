# Phase 4 — Decisions & Progress Log

Running lab notebook for dissertation methodology / evaluation chapters.
Update incrementally as Parts 0–4 land. Separate from the Phase 4 spec (`PHASE4_SEMANTIC.md`).

---

## Status distinction (read this first)

| Layer | State (as of 2026-07-22) |
|-------|---------------------------|
| **Implementation** | Parts 0–4 **code complete** (schema, features, both embed backends, ablation harness, proxy wiring). |
| **Verification (rules / Part 1–2)** | **Done locally** — regex/coverage/exclusion/confidence tests passed (110+). Tokenizer id reconciled to `Llama-3.1-8B-Instruct`. |
| **Verification (rewrite + APC)** | **Done on Aire earlier** — `smoke_rewrite_apc.py` ~30× warm TTFT (rules rewrite path). |
| **Verification (Part 3 embeddings)** | **Pending on Aire** — MiniLM / Qwen3-Embedding-0.6B never loaded against L40S + vLLM 0.90; fallback trigger not confirmed with real model output. |
| **Verification (Part 4 full 4-way)** | **Partial** — harness ran locally with `--skip-embed` (conditions 1–2 only); conditions 3–4 + VRAM **not** measured. |

For the methodology chapter: treat embeddings and the full ablation table as
**“implemented, awaiting cluster verification”** — not as validated claims.

---

## Part 0 — Setup (2026-07-19)

Created this file as the standing decisions/progress log for richer schema tagging,
negation/exclusion metadata, embedding fallbacks, and the 4-way ablation.

**Standing design constraints (locked):**
- Rules are the **default** classifier; embeddings are **fallback-only** on
  low-confidence / `UNKNOWN` task — never a primary classifier.
- No LLM system-prompt classification; no hosted third-party APIs; local weights only
  on the Aire node beside vLLM.
- No open-ended label generation — every field uses a fixed enumerated set.
- Negation / exclusion detection is **rule-based only** (embeddings are a known weak
  spot for antonymic near-duplicates such as “with X” vs “without X”).
- New multi-facet fields do **not** fork the canonical-prefix catalogue in this pass
  (metadata / reporting / future priority weighting only).

---

## Part 1 — Schema hygiene (in progress)

### What changed and why

**Regex coverage.** The original summarize patterns used `summariz(?:e|e|ing)`, which
duplicated `e` and missed common paraphrases (`summarized`, `summary`, `summarization`,
and British `summarised`). Because the dissertation contribution specifically claims
paraphrase resilience for shared-instruction APC, those gaps would inflate bypass rate
and understate rewrite coverage. Patterns were expanded to verb/noun forms plus
`summary` / `bullet points`; British forms mirrored.

**Tie-break.** Implicit `summarize_hits >= entity_hits` was replaced with an explicit
`TASK_PRIORITY` tuple. **Decision:** summarization precedes entity extraction because
the primary APC evaluation case is shared-instruction summarization traffic; the order
is a deliberate workload prior, not an accident of comparison operators.

**Serving model / tokenizer — reconciliation (confirmed in code, not assumed).**

| Source | Model id |
|--------|----------|
| `src/engine/run_vllm.sh` `MODEL=` | `meta-llama/Llama-3.1-8B-Instruct` |
| `src/proxy/rewrite/align.py` `MODEL_ID` | `meta-llama/Llama-3.1-8B-Instruct` |
| `length_class` / `_token_len` | calls `align.get_tokenizer()` → same `MODEL_ID` |

**Why Llama-3.1 (not Meta-Llama-3-8B-Instruct):** that is the model Aire smoke-tested
and the string `run_vllm.sh` actually launches. Token buckets for logging must use the
same tokenizer APC / chat-template alignment use, so schema imports that path rather
than a second HF id. `Meta-Llama-3-8B-Instruct` is **not** used anywhere in the live
stack.

**Token bucket thresholds (decision):**
| Class | Token count |
|-------|-------------|
| short | &lt; 128 |
| medium | &lt; 1024 |
| long | ≥ 1024 |

These are logging/reporting buckets only — they do **not** select catalogue prefixes.
Chosen as round powers-of-two-ish cut-points aligned with short instruction vs
medium RAG vs long document regimes; not calibrated on a corpus yet.

### Known limitation (negation) — accepted scope

Part 2 adds rule-based **exclusion-term extraction** (e.g. “without BeautifulSoup”).
That does **not** fully solve task-level negation (“Don’t summarize — extract
entities”). Deeply nested, implied, or sarcasm-style negation may still be missed.
Documented as a v1 keyword-tagger limitation for the dissertation limitations section;
a regression test encodes the failure mode where a hit-count tie still prefers
summarize despite “Don’t summarize…”.

### Numbers (Part 1)

- Paraphrase coverage asset (`tests/test_tag_coverage.py`): **18/18** summarize
  paraphrases tagged `summarize_3_bullets` after regex fix (measured locally,
  2026-07-19).

---

## Part 2 — Richer schema fields + exclusion metadata (2026-07-19)

### What was built

Added three orthogonal fields on `SchemaTags`, each with its own regex list:

| Field | Values | Role |
|-------|--------|------|
| `entity_focus` | `team` / `individual` / `unknown` | Who the request is about |
| `action_type` | `analysis` / `retrieval` / `generation` / `unknown` | Verb class of the ask |
| `excluded_terms` | tuple of captured phrases | Explicit “without / not using / excluding / avoid / don’t use|include …” |

**Decision — catalogue not forked on these fields.** Prefix selection remains keyed by
`Task` only. Splitting the catalogue by every feature combination would fragment
traffic across more prefixes and can *reduce* APC hit rate; that trade-off needs a
dedicated future ablation, not a default change now. Part 2 fields are logged for
evaluation reporting and future priority/eviction weighting only.

**Decision — exclusion is rule-based, never embedded.** “Scrape with BeautifulSoup”
vs “without BeautifulSoup” are lexically near-identical and often close in embedding
space despite opposite meaning. Exclusion cues therefore use regex capture only.

**Correctness note:** rewrite still passes user content through `light_normalize`
unchanged after attaching the canonical system prefix. An exclusion like “without
BeautifulSoup” is never stripped — catching it in `excluded_terms` is for metadata/
reporting, not generation correctness.

**Limitation (accepted):** unusual exclusion phrasings outside the cue list are
missed. Task-level negation (“Don’t summarize — extract”) remains only partially
addressed (see Part 1).

### Coverage numbers (Part 2) — evidence before Part 3

Fixtures in `src/proxy/ablation/fixtures.py`; tests in `tests/test_schema_features.py`.

| Asset | Count | Result (2026-07-19) |
|-------|------:|---------------------|
| `entity_focus` TEAM paraphrases | 16 | all → `team` |
| `entity_focus` INDIVIDUAL paraphrases | 16 | all → `individual` |
| `action_type` ANALYSIS | 16 | all → `analysis` |
| `action_type` RETRIEVAL | 16 | all → `retrieval` |
| `action_type` GENERATION | 16 | all → `generation` |
| Exclusion pairs (with vs without cue) | 8 | same `task`; term captured |
| Summarize paraphrases (Part 1 asset) | 18 | all → `summarize_3_bullets` |

Combined pytest: **`tests/test_schema_features.py` + `tests/test_tag_coverage.py` → 110 passed**.

Example exclusion pair (generation task unchanged):
- `Write web scraping code for this site.`
- `Write web scraping code for this site without BeautifulSoup.`
  → same task tag; `BeautifulSoup` in `excluded_terms`.

**Honest limit of this evidence:** 100% on this suite is a **weaker signal than it
looks**. The same authors wrote both the regex patterns and the test phrasings, so a
perfect score mainly confirms **internal consistency** of the authored asset — not that
the tagger **generalizes to unseen / uncurated user phrasing**. The dissertation claim
that needs external evidence is generalization (e.g. ShareGPT/LMSYS-style prompts, or
prompts written by someone who has not seen `_SUMMARIZE_PATTERNS`). That is deferred to
**Phase 6 evaluation**, not claimed from Part 2 coverage alone.

**Part 3 was therefore built after this coverage evidence**, not on an untested assumption
that rules alone were adequate for in-schema paraphrases. (Bypass on out-of-catalogue
prompts such as bare “write code…” remains expected — that is what embed fallback targets.)

### Confidence coupling check — `excluded_terms`

**Confirmed in `tag_user_text`:** only `entity_focus` / `action_type` (when not UNKNOWN)
add +0.05 to confidence; `excluded_terms` is assigned after scoring and **never** read
when updating `conf`. Docstring on `extract_excluded_terms` states the same. Regression:
`test_excluded_terms_do_not_affect_confidence` in `tests/test_schema_features.py`.

---

## Part 3 — Embedding fallbacks (2026-07-19)

### What was built (implementation only — not yet verified on Aire)

Two swappable local backends under `src/proxy/rewrite/embed/`, selected by
`OPTIMIZER_EMBEDDING_BACKEND=off|minilm|qwen3` (also via ablation
`TagConfig.for_ablation`):

| Backend | Model id | When used |
|---------|----------|-----------|
| A MiniLM | `sentence-transformers/all-MiniLM-L6-v2` | Rules return UNKNOWN or conf &lt; threshold |
| B Qwen3 | `Qwen/Qwen3-Embedding-0.6B` (confirmed HF card) | Same gate |

Matching uses **multiple exemplars per Task** (`exemplars.py`) and **max cosine
similarity** across exemplars — never a single fragile anchor, never open-ended
labels, never used for exclusion/negation.

**Decision — default backend is `off`.** Production proxy stays rules-first; embed
is opt-in for ablation / low-coverage rescue.

### What is still unverified (do not claim in results yet)

1. **Load / VRAM:** Qwen3-Embedding-0.6B (and MiniLM) on the same L40S as vLLM
   `--gpu-memory-utilization 0.90` — OOM or contention unknown; may need
   `OPTIMIZER_EMBED_DEVICE=cpu`.
2. **Fallback trigger:** that UNKNOWN / low-confidence paths actually call the
   backend and change `task` with **real** embedding scores (not mocked).
3. **Quality:** whether embed rescue reduces bypass rate on the shared request set
   without mis-tagging.

Local Windows env had no usable torch/CUDA for these models; HF-gated serving
tokenizer was also unavailable without `HF_TOKEN` (same class of skip as earlier
alignment tests). **Coded ≠ validated.**

Aire verification command:

```bash
pip install sentence-transformers
python -m src.proxy.ablation.run_tag_ablation --write-log
```

---

## Part 4 — Ablation harness

Harness: `python -m src.proxy.ablation.run_tag_ablation`
Conditions: `rules_only` | `rules_plus_features` | `embed_minilm` | `embed_qwen3`.
Reports bypass rate, **mean rule_ms**, **mean embed_ms** (separate), embed-used rate,
VRAM after backend load. Appends to this log with `--write-log`.

Warm TTFT / Token Saving Ratio intentionally deferred to live
`smoke_rewrite_apc.py` / Phase 6 (tagging ablation isolates classifier behaviour).

### Has the harness actually been run?

**Yes — once locally with `--skip-embed` (2026-07-19):** conditions 1–2 only, n=113
shared prompts. Confirmed comparable output structure (same table columns:
bypass / rule_ms / embed_ms / embed-used / VRAM). Numbers below are that dry-run;
`embed_ms` stayed 0 because backends were skipped.

**Not yet run:** full four-condition Aire pass with real MiniLM + Qwen loads.
Until that lands, Part 4 is “harness smoke-tested for schema; embed rows pending.”

Local dry-run (`--skip-embed`) results follow; re-run on Aire for embed rows.

## Part 4 — Ablation results (2026-07-19 16:37 UTC)

Shared request set = Part 2 coverage assets + summarize paraphrases (n=113). Latencies are **mean ms**, rule vs embed reported separately. VRAM is process `torch.cuda.memory_allocated` after backend load (None = CPU / unavailable).

| Condition | Bypass rate | Mean rule_ms | Mean embed_ms | Embed-used rate | VRAM |
|-----------|-------------|--------------|---------------|-----------------|------|
| `rules_only` | 20.4% | 236.25 | 0.00 | 0.0% | n/a |
| `rules_plus_features` | 20.4% | 206.94 | 0.00 | 0.0% | n/a |

**Notes:** Warm TTFT / Token Saving Ratio need live vLLM+APC (`smoke_rewrite_apc.py` / Phase 6) and are not duplicated here — tagging ablation isolates classifier behaviour only.

### Decisions / caveats from this run

- Embeddings used only when rules return UNKNOWN or confidence below threshold.
- Qwen3-Embedding-0.6B VRAM must be read against vLLM `--gpu-memory-utilization 0.90` on L40S; if contention appears, set `OPTIMIZER_EMBED_DEVICE=cpu` for the proxy process.
- Catalogue still keyed by Task only; Part 2 fields remain metadata.

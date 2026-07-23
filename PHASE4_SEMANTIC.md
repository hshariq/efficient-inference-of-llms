# Phase 4 — Semantic Sub-Batching + Canonical Prefixes

> **Goal:** Inside the Phase 2 proxy, rewrite eligible RAG requests onto **block-aligned
> Canonical Task Prefixes** so vLLM Automatic Prefix Caching (APC) gets exact-match hits
> on *shared-instruction / different-data* traffic — without Trimmer, without runtime
> clustering, with low-confidence bypass.

Builds on: pass-through proxy (`src/proxy/`).  
Explicitly **not** building: Trimmer (future work).

---

## Why this phase (contribution edge)

vLLM APC already helps when a **large shared document** sits at the front of two prompts
(shared-context / near-duplicate). Our value is the harder case:

- **Shared instruction, different data** — e.g. the same “summarize in 3 bullets” template
  applied across *different* documents. Without us, instruction text is buried or phrased
  differently and APC rarely shares the instruction prefix. We **lift a fixed, identical,
  block-aligned instruction prefix** to the front so APC can hash-hit it across requests.

---

## Locked design choices

| Choice | Decision |
|--------|----------|
| Where | Rewrite in proxy **before** upstream `httpx` call; SSE still pass-through |
| Primary signal | Schema-driven / rule-based tags (O(1)) |
| Embeddings | Fallback among a **fixed** canonical-prefix set only — not open-ended clustering |
| Runtime k-means / DBSCAN | Forbidden |
| Low confidence | **Bypass** (forward original messages unchanged) |
| Trimmer | Out of scope — see normalization rules below |

---

## Build sequence

### 4a — Hook only
- Add `rewrite_request(body) -> body` in the proxy (default: identity).
- Log decision: `bypass | rewrite` + tags (when any).
- No behaviour change yet; proves plumbing.

### 4b — Schema tagging + block-aligned canonical prefixes (**core**)

**Schema fields (deterministic):** e.g. `domain`, `task`, `entity_focus`, `length_class`  
(exact enum set fixed in code + documented for the dissertation).

**Rules:** keyword / regex / template matchers → tags + confidence score.

**Canonical map:** `(tags) → Canonical Task Prefix` string from a **fixed** catalogue
(e.g. `TASK_SUMMARIZE_3_BULLETS`, `TASK_EXTRACT_ENTITIES`, …).

**Rewrite shape:**
```text
[block-aligned canonical prefix] + [user content with LIGHT normalization only]
```

#### Block alignment (required — not optional)

vLLM APC / PagedAttention hashes at **block** granularity (default **16 tokens** on our
stack unless configured otherwise). Alignment MUST match what APC actually sees.

**Critical:** APC hashes the **fully rendered** prompt after the chat template inserts
role headers and special tokens (e.g. `<|begin_of_text|>`,
`<|start_header_id|>…<|end_header_id|>`, etc.). The rewrite operates on the OpenAI-style
`messages` JSON, but token positions in the hashed sequence are **not** the same as
tokenizing the raw canonical prefix string in isolation.

Therefore:

1. Pad / align against the **fully-rendered chat-template output**, not the raw
   canonical prefix string alone.
2. Use the **same** tokenizer + chat template path as serving model
   `meta-llama/Llama-3.1-8B-Instruct` (the model we run on Aire — keep this name
   consistent everywhere; do not mix with `Meta-Llama-3-8B-Instruct`).
3. Two requests that map to the same catalogue entry must produce **byte-identical**
   rendered prefix segments (same special tokens + same prefix body).
4. After render, the shared prefix span’s token length must satisfy
   `length % BLOCK_SIZE == 0` (or the catalogue entry must be pre-crafted so the
   rendered span already lands on a block boundary).

**4b unit test (required):** for each catalogue entry, build the minimal `messages`
array the proxy would emit for that task, run `tokenizer.apply_chat_template(...)`
(same flags vLLM uses server-side insofar as we can match them), then assert the
shared-prefix token span is block-aligned. **Do not** only assert
`len(tokenizer.encode(raw_prefix_string)) % BLOCK_SIZE == 0`.

If alignment is computed on the raw string only, block boundaries in the final prompt
sit elsewhere — tagging can look correct while APC hits stay inconsistent.

#### Padding content (quality — short note for `catalogue.py`)

Padding is **not** training-style attention-mask padding: whatever you append is real
context the model may attend to and generate against. Prefer, in order:

1. **Pre-craft** each canonical prefix so the *rendered* shared span naturally lands on
   a block multiple (best).
2. If residual pad is needed, use a **fixed, semantically inert** trailer documented in
   `catalogue.py`. It must survive Llama chat-template `.strip()` **and** increase
   rendered LCP (some glyphs e.g. middle-dot can be BPE-absorbed with Δtokens=0).
   `align.py` tries `PAD_TRAILER` then ASCII fallbacks like ` #`.

Document the chosen pad policy in `catalogue.py`’s docstring so future changes don’t
quietly degrade answer quality.

#### Light normalization vs Trimmer (scope firewall)

Allowed in Phase 4 (“normalized lightly”):

- Unicode/whitespace collapse (trim, squeeze repeated spaces/newlines)
- Optional NFKC normalization
- **Not** changing wording

**Forbidden** (that is Trimmer / future work):

- Stripping filler (“please”, “kindly”, …)
- Paraphrase / reordering / “cleanup” of user phrasing
- Aggressive punctuation or sentence restructuring aimed at near-duplicate convergence

If a change would make two differently worded instructions become the same *without*
going through the canonical-prefix catalogue, it belongs to Trimmer — **do not add it**.

### 4c — Bypass
- If confidence &lt; threshold **or** no catalogue match → no rewrite.
- Metric/log: bypass rate (should stay non-zero on messy traffic).

**Rule-tagger limitations (flag for dissertation):**
- Paraphrase coverage is only as good as `_SUMMARIZE_PATTERNS` / `_ENTITY_PATTERNS`
  (see `tests/test_tag_coverage.py` for an explicit paraphrase asset).
- **No negation handling** — e.g. “Don’t summarize, extract entities” may mis-tag;
  accepted for v1 keyword tagging.
- `length_class` is **logging-only** (token buckets via Llama-3.1 tokenizer); it does not
  select catalogue prefixes (task enum does). Confidence is a simple heuristic, not a
  calibrated probability.
- Tie-breaks use explicit `TASK_PRIORITY` (summarize before extract).

### Test map (don’t forget — no vLLM)

These are **tagger unit/coverage** checks. They call `tag_user_text` only.
They do **not** prove generalization to unseen user phrasing (that is Phase 6).

#### `tests/test_tag_coverage.py` — “do summarize paraphrases still tag?”

- Loads ~18 hand-written ways to say “summarize in 3 bullets” (`SUMMARIZE_PARAPHRASES`).
- For each: `tag_user_text(prompt + fake_doc)` must return `task=summarize_3_bullets`
  and `confidence >= 0.55`.
- **Example:** `"I need a summary of this in 3 bullets."` + oak-tree doc → regex hits
  `summary` + `3 bullets` → `summarize_3_bullets` → pass; if `unknown`, test fails
  (that phrasing would bypass in the live proxy).
- Also locks: tie-break prefers summarize; entity wins when it has more hits;
  negation failure mode stays documented (`Don't summarize… extract…` still tags summarize).

#### `tests/test_schema_features.py` — “do Part 2 metadata fields work?”

- **entity_focus:** 16 team + 16 individual prompts → must tag `team` / `individual`.
- **action_type:** 16 analysis + 16 retrieval + 16 generation → matching enum.
- **excluded_terms:** pairs like  
  `Write web scraping code…` vs `… without BeautifulSoup`  
  → **same `task`**, but the second has `BeautifulSoup` in `excluded_terms`
  (metadata only; generation correctness still relies on user text passing through).
- Also: `rich_features=False` clears Part 2 fields; `excluded_terms` must **not**
  change confidence.

#### Related

- `tests/test_rewrite_align.py` — block alignment + rewrite/bypass (needs Llama tokenizer).
- `python -m src.proxy.ablation.run_tag_ablation` — same fixtures, prints INPUT/OUTPUT/METRICS
  per condition (still no vLLM).
- Full narrative + “authored set ≠ generalization” caveat:
  `docs/PHASE4_DECISIONS_LOG.md`.

#### Ablation conditions (tagging only — no vLLM)

Same prompt set for all four. Each run prints per request:

- **INPUT** — the prompt string  
- **OUTPUT (tags)** — task / domain / confidence / entity_focus / action_type / excluded_terms  
- **METRICS** — rule_ms, embed_ms, embed_used, embed_score, would_bypass  

Then an aggregate: bypass %, mean rule_ms, mean embed_ms, embed-used %, VRAM.

| # | `--conditions` | What is turned on | What you are measuring |
|---|----------------|-------------------|------------------------|
| 1 | `rules_only` | Part 1 fields only (`task`/`domain`/`length_class`). No Part 2. No embed. | Baseline rule tagger. Part 2 fields stay `unknown` / empty. |
| 2 | `rules_plus_features` | (1) + Part 2 metadata (`entity_focus`, `action_type`, `excluded_terms`) | Do richer tags fill in? Catalogue/`task` should stay the same policy as (1) for in-schema prompts; maybe slight confidence bumps. |
| 3 | `embed_minilm` | (2) + MiniLM fallback only if UNKNOWN or conf &lt; threshold | Does MiniLM rescue bypasses? Watch `embed_used`, `embed_ms`, bypass ↓. |
| 4 | `embed_qwen3` | (2) + Qwen3-Embedding-0.6B on the same gate | Same as (3) with a stronger local embedder; also VRAM vs vLLM. **Uses a classification `Instruct:` wrapper on the query** (MiniLM does not). |

**Slow walkthrough with one example prompt**  
`Write web scraping code for this site without BeautifulSoup.`

1. **`rules_only`**  
   - Regex may not map “write code…” to summarize/extract → often `task=unknown`, `would_bypass=True`.  
   - `entity_focus` / `action_type` / `excluded_terms` forced empty (rich features off).  
   - `embed_ms=0`, `embed_used=False`.

2. **`rules_plus_features`**  
   - Still likely `task=unknown` (same task rules).  
   - But now: `action_type=generation`, `excluded_terms=['BeautifulSoup']` (and maybe team/individual if present).  
   - Still `embed_ms=0`. Shows metadata works even when we would not rewrite.

3. **`embed_minilm`**  
   - Rules still say UNKNOWN → fallback runs MiniLM vs fixed task exemplars.  
   - If similarity ≥ min score: `task` becomes e.g. `extract_entities` or stays unmatched; `embed_used=True`, `embed_ms>0`.  
   - If still weak: bypass remains. **This is what Aire must verify.**

4. **`embed_qwen3`**  
   - Same control flow as (3), different model (`Qwen/Qwen3-Embedding-0.6B`).  
   - Compare bypass rate / embed_ms / VRAM to MiniLM — not mixed in one process.

Commands (GPU node, `.venv`, no vLLM required for tagging):

```bash
python -m src.proxy.ablation.run_tag_ablation --conditions rules_only
python -m src.proxy.ablation.run_tag_ablation --conditions rules_plus_features
python -m src.proxy.ablation.run_tag_ablation --conditions embed_minilm
python -m src.proxy.ablation.run_tag_ablation --conditions embed_qwen3
# sample: add --limit 5 ; save: --jsonl logs/run.jsonl ; summary only: --quiet
```

### 4d — Embedding assist (optional, only if rules insufficient)
- Small Sbert/MPNet-class model.
- Choose among **fixed** canonical prefix IDs (nearest neighbour / threshold).
- Still no open-ended cluster create-at-runtime.

### 4e — Measure (test set must hit our contribution case)

**Must include (primary):**

| Pattern | Example | Why |
|---------|---------|-----|
| Shared-instruction, **different data** | Same “summarize in 3 bullets” prefix + Doc A vs Doc B | **Our** APC win condition |
| Paraphrased instruction, different data | “3 bullet summary of …” vs “Summarise the following in three bullets …” + different docs | Shows catalogue + rewrite beats raw phrasing |
| Low-confidence / out-of-schema | Gibberish or unknown task | Must **bypass** |

**May include (control — do not treat as main success proof):**

| Pattern | Example | Why |
|---------|---------|-----|
| Shared-context near-duplicate | Same contract, “summarize” vs “please summarize” | APC often already helps; useful as control, **not** the claim |

**Metrics (Phase 4):** warm TTFT on 2nd+ request sharing a canonical prefix; later Token
Saving Ratio in Phase 6. Quality spot-check: rewrite must not change task meaning.

**“Done” for 4b (revised):**  
Two requests with the **same catalogue task** and **different document bodies** leave the
proxy with an **identical block-aligned rendered prefix span** (verified via chat-template
tokenization, not raw-string encode), and under APC the later request shows a clear
warm-prefix benefit vs pass-through proxy on that pair — not merely a paraphrase-of-same-doc
pair.

---

## Suggested repo layout (when implementing)

```text
src/proxy/
  app.py                 # call rewrite_request() before upstream
  rewrite/
    __init__.py
    schema.py            # enums + rule taggers
    catalogue.py         # canonical prefixes + pad policy docstring
    align.py             # block-size pad on chat-template–rendered spans
    pipeline.py          # tag → confidence → bypass/rewrite
```

---

## Out of scope this phase

- Trimmer (filler removal / paraphrase)
- TTL / starvation (Phase 5)
- Full eval harness vs GPTCache (Phase 6)
- Unsupervised runtime clustering

---

## Done checklist

- [x] 4a identity hook + logs (`OPTIMIZER_REWRITE_MODE=tag_only|off`)
- [x] 4b schema + catalogue + **chat-template–aware** block alignment unit tests
- [x] Model id locked: `meta-llama/Llama-3.1-8B-Instruct` (no Llama-3 mix-ups)
- [x] 4c bypass path (low confidence / unknown)
- [x] 4e shared-instruction / different-data pairs smoke on Aire (APC TTFT) — see `docs/PHASE4_DECISIONS_LOG.md` (mechanism verified; warm on/off ratio caveat; TSR → Phase 6)
- [x] Light-normalization rules documented and Trimmer-creep absent in code review
- [x] Optional 4d (MiniLM / Qwen embed fallback) implemented + Aire ablation; default remains `off`
- [x] Live MiniLM hard-prompt rescue + out-of-catalogue bypass on Aire (see decisions log)

**Phase 4: CLOSED (2026-07-23).** Results: `docs/PHASE4_DECISIONS_LOG.md`. Artefacts: `results/phase4/`.  
**Next:** Phase 5 (TTL / starvation escape).

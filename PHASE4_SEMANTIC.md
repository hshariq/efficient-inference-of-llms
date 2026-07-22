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
   `catalogue.py`. It must be **non-whitespace** (Llama chat templates `.strip()` message
   content, so trailing newlines never reach the hashed sequence) — never arbitrary or
   random placeholder tokens. We use middle-dot `·` (`PAD_TRAILER`).

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
- `length_class` is **logging-only** (character buckets); it does not select catalogue
  prefixes (task enum does). Confidence is a simple heuristic, not a calibrated probability.
- Tie-breaks use explicit `TASK_PRIORITY` (summarize before extract).

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
- [ ] 4e shared-instruction / different-data pairs smoke on Aire (APC TTFT)
- [x] Light-normalization rules documented and Trimmer-creep absent in code review
- [ ] Optional 4d only after 4b proven

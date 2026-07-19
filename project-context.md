# Optimizer Box — Project Context (MSc Dissertation)

> **Purpose of this file:** Give an AI coding assistant (Cursor) enough grounding to help
> implement the system without re-reading the full literature review. This is the
> condensed architecture + design-decision brief, not the lit review itself.

## 1. One-line pitch

A **non-invasive middleware proxy** that sits in front of a standard vLLM server and
increases KV-cache reuse / GPU throughput for RAG-style workloads by **semantically
grouping and aligning incoming requests before they hit the inference engine** —
without modifying vLLM, without touching model weights, and without requiring client
code changes.

## 2. The core problem being solved

- LLM inference = **prefill** (compute-bound, process whole prompt) + **decode**
  (memory-bound, one token at a time).
- vLLM's PagedAttention/Automatic Prefix Caching (APC) eliminates memory
  fragmentation and *can* share KV cache across requests — but only on **exact,
  character-for-character prefix matches**, and only if requests happen to arrive
  close together (it's reactive, not scheduling-aware).
- Real users phrase semantically identical requests differently ("Summarize this
  contract" vs "Please summarize this contract"), so vLLM/RadixAttention treat them
  as unrelated and recompute the entire prefill from scratch — wasted GPU compute.
- **This is the gap Optimizer Box fills**: a routing/scheduling layer *above* vLLM
  that increases the odds of exact-match hits by grouping and normalizing semantically
  similar requests before they reach the engine.

## 3. System architecture

### 3a. Pipeline / containment diagram (source of truth — see `system_design.png`)

The request flow is **not four parallel siblings** — it's a sequential stage feeding into
a nested containment:

```
Requests
  → [1. "Trimmer" Preprocessing Engine]        (strips noise tokens, normalizes phrasing)
      → [2. Semantic Sub-Batching                (embeds + groups + canonical-prefix rewrite)
            → [3. Continuous Batching technique    (iteration-level scheduling; this is
                                                     where TTL/starvation-escalation lives —
                                                     preemption happens at the token boundary)
                  → [4. KV Caching and Prefix Management]   (vLLM / PagedAttention — backend,
                                                              not built by us)
            ]
        ]
  → Responses
```

Read as: Trimmer is a distinct first stage. Semantic Sub-Batching is the outer layer we
own conceptually; it hands off into Continuous Batching (vLLM's own iteration-level
scheduler — this is also where our **TTL/starvation-prevention** logic hooks in, since
preemption can only actually happen at vLLM's per-token boundary); which in turn relies
on KV Caching/Prefix Management (PagedAttention) as the innermost, vLLM-owned foundation.

> **Open question to confirm:** "Intelligent Prompt Scheduling" (the TTL/starvation logic)
> isn't drawn as its own box — it's currently assumed to live inside "Continuous Batching
> technique" rather than being a separate component. Confirm this before treating it as
> settled in the code structure.

### 3b. Component descriptions

1. **KV Caching and Prefix Management** (foundation layer — this is vLLM/PagedAttention,
   not something we build; we rely on it and cite it as the backend).
2. **Intelligent Prompt Scheduling** — traffic-controller logic that decides *when*
   and *in what order* requests reach vLLM, including the TTL/starvation-prevention logic.
   Per the diagram, this is realized *inside* vLLM's continuous batching loop (we flag a
   request as high-priority; vLLM's own iteration-level scheduler does the actual preemption).
3. **Semantic Sub-Batching** — embeds incoming requests (lightweight model, e.g.
   MPNet/ALBERT via Sbert), clusters/aligns semantically similar ones, and rewrites
   them onto shared **Canonical Task Prefixes** so vLLM's exact-match caching is
   "tricked" into firing on requests that are semantically but not literally identical.
4. **"Trimmer" Preprocessing Engine** — strips non-essential/noise tokens (e.g. "please",
   filler words) so near-duplicate prompts converge onto the same canonical prefix. Runs
   *before* embedding/sub-batching, as the first stage on the request path.

**Taxonomy used in the write-up:**
- Hardware/Model Layer (handled by vLLM): Tensor/Pipeline/Context Parallelism, PagedAttention.
- Network/Request Layer (handled by Optimizer Box): Semantic Sub-Batching, Trimmer, TTL scheduling.

## 4. Explicit design decisions (already made — don't relitigate)

### Implementation scope (dissertation build)

- **"Trimmer" Preprocessing Engine** is part of the *architecture* (diagram / lit positioning) but is
  **deferred to future work** for the coded system. We do **not** implement noise-token stripping
  in the submitted Optimizer Box. Rationale: keep scope on the proxy hop + semantic
  sub-batching / canonical prefixes (+ TTL); Trimmer is complementary and can stack later.
- Ablation study in §7 originally planned (a) semantic alone (b) Trimmer alone (c) combination —
  **drop (b)** and Trimmer-combination cells; report semantic (± TTL) vs baselines instead.

**We ARE building:**
- A stateless-ish proxy in front of vLLM's OpenAI-compatible API (standard JSON in/out,
  zero client-side changes required).
- Lightweight embedding model for semantic similarity (MPNet/ALBERT-class, not an LLM).
- Canonical Task Prefix rewriting to force exact-match cache hits downstream.
- A **dynamic Time-To-Live (TTL) escape hatch**: any request waiting past a threshold
  gets forced priority/bypass regardless of batch efficiency, to prevent starvation
  (this is our answer to SGLang authors' own acknowledged "future work" gap around
  greedy cache-aware scheduling causing starvation).
- **Schema-driven / feature-aware routing** for known RAG domains (deterministic O(1)
  tagging: domain, entity focus, length class) rather than unsupervised clustering —
  chosen because the enterprise RAG schema is known in advance, unlike generic chatbot traffic.
- A fallback/bypass path: low-confidence-tagged queries skip the cache and go straight
  to vLLM (prevents forcing bad matches).
- Adaptive eviction for the **proxy's own metadata/routing table** (not GPU memory —
  vLLM manages that itself), scored by feature rank (high-value RAG contexts weighted higher).
- **Token Saving Ratio** as the primary evaluation metric (tokens saved / total tokens
  that would've been processed without the system) — not raw hit-rate, because hit-rate
  alone is a misleading "vanity metric" (a hit on a 50-token query ≠ a hit on a 5,000-token
  RAG context). Also track: cache hit rate, TTFT, GPU VRAM allocation, output quality/accuracy.

**We are explicitly NOT building (and why — cite as "future work" or "out of scope"):**
- Decoding length prediction (e.g. PARS-style output-length ranking) — vLLM's continuous
  batching already handles this; we focus purely on the **prefill** bottleneck, not decode.
- Text-level batch prompting (stuffing multiple users' questions into one string) —
  proven in literature to degrade accuracy via context blurring; we batch *at the KV/
  hardware level* via PagedAttention, keeping requests independent at the user level.
- Output/response caching (GPTCache-style: return a stored *answer* on a hit) — we cache
  the **intermediate KV state**, not the final text, so responses stay dynamic/personalized.
- Unsupervised clustering (k-means/DBSCAN) at runtime — too slow/non-deterministic for a
  live streaming proxy; only viable for offline/static datasets.
- Custom CUDA kernels, quantization, tensor-level compression (AWQ, PQCache, MiniCache) —
  orthogonal, lossy, hardware-layer; we're a lossless, software/routing-layer optimization
  that stacks on top of whatever compression/quantization is already deployed.
- Hardware-level PD (Prefill-Decode) disaggregation — we argue we reduce the *need* for it
  by shrinking the prefill workload before it ever hits the GPU.
- Predictive/LLM-driven instruction pre-fetching (InstCache-style) — probabilistic, wastes
  compute on wrong guesses; our grouping is deterministic (based on requests actually
  concurrent right now).

## 5. Key positioning statements vs. prior work (for reuse in write-up / code comments)

- **vs vLLM/PagedAttention**: "vLLM provides the foundational lossless memory management;
  it is blind to semantic context. Optimizer Box maximizes PagedAttention's potential by
  deliberately aligning request prefixes upstream."
- **vs SGLang/RadixAttention**: RadixAttention requires exact-match prefixes and its own
  paper admits greedy cache-aware scheduling can starve unique queries (explicit "future
  work" gap) and requires an invasive frontend DSL. Optimizer Box is non-invasive
  (standard API, zero code changes) and solves the starvation gap via TTL.
- **vs SCALM**: SCALM does output caching (returns stored text) and uses k-means/vote-k
  on static offline datasets. Optimizer Box does KV-state caching (supports dynamic,
  personalized generation) and works on live streaming traffic without needing the full
  dataset up front. We adopt SCALM's **Token Saving Ratio** metric.
- **vs MeanCache**: Client-side/edge/federated, returns static text, isolates users from
  each other (1000 users asking the same Q each compute it once). Optimizer Box is
  server-side, so user 2–1000 instantly share user 1's KV compute.
- **vs PARS**: Orthogonal, not competing — PARS reorders the *queue* based on predicted
  *output* length (decode-phase). We group *inputs* based on semantic similarity
  (prefill-phase). Ideal system would use both. We borrow PARS's TTL/starvation-prevention
  philosophy but implement it via simple time-based escalation rather than an ML predictor
  (avoids extra inference overhead).
- **vs KVSwap**: Tensor-level SVD/low-rank approximation for disk offload. We apply the
  same "approximate to reduce work" philosophy but at the semantic/API layer, not the
  tensor layer — non-invasive vs. their invasive hardware/kernel integration.
- **vs Batch Prompting (paper)**: Their method stuffs multiple questions into one text
  block → degrades accuracy (context blurring). We keep requests independent and batch
  at the hardware/KV level → get throughput gains without the accuracy penalty.

## 6. Implementation stack notes

- Proxy sits in front of a standard vLLM OpenAI-compatible endpoint.
- Embedding step: lightweight sentence-embedding model (MPNet-class via Sbert), NOT the
  target LLM — this is the "cheap scout" pattern (same philosophy as BERT-based length
  predictors in PARS, kept intentionally simple to avoid overhead).
- Feature tagging: rule-based/schema-driven, not ML clustering, for O(1) latency.
- TTL/starvation logic: simple timestamp + priority escalation; relies on vLLM's
  iteration-level (continuous batching) scheduling to actually preempt/inject at the next
  token boundary — we don't need to implement preemption ourselves, vLLM already does it
  once a request is flagged high-priority.
- Metadata/routing table (proxy-side) uses its own adaptive eviction (LFU-style scored by
  feature rank), separate from vLLM's own GPU block eviction — don't conflate the two.

## 7. Evaluation plan

Compare four systems under identical simulated RAG workload:
1. Vanilla vLLM (baseline, no caching layer) — measures proxy overhead cost.
2. vLLM + Automatic Prefix Caching (APC) — the real "arch-nemesis" to beat (exact-match only).
3. GPTCache (server-side output cache) — fastest but lowest quality/flexibility comparator.
4. Optimizer Box (ours).

Metrics per system: Cache Hit Rate, Token Saving Ratio, TTFT (measured client-side, not
from inside vLLM logs — queueing delay must be included), GPU VRAM allocation, output
quality/accuracy degradation.

Also run an **ablation study** (à la SCALM Fig. 8): isolate contribution of (a) semantic
clustering/sub-batching alone, (b) Trimmer preprocessing alone, (c) combination — to prove
each component contributes, not just lucky data.

Also test: concurrency=1 baseline (routing overhead floor) and a burst scenario
(e.g. 2000 simultaneous requests) to show resilience under load vs FCFS/APC.

---
*Source: distilled from the full literature-review working document
("Optimizer Box" MSc dissertation notes) covering vLLM/PagedAttention, SGLang/
RadixAttention, SCALM, MeanCache, PARS, KVSwap, Batch Prompting, Speculative
Decoding survey, and "Taming the Titans" survey.*
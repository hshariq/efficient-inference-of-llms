# Phase 2 — FastAPI Proxy Skeleton (pass-through only)

> **Goal:** Transparent OpenAI-compatible hop in front of vLLM. Prove the pipe works and
> measure **proxy overhead in isolation** (evaluation “concurrency=1 baseline”) before any
> Trimmer / semantic / TTL logic.

## Why this phase

Clients → **Optimizer Box (this proxy)** → vLLM. Later phases plug into this process.
Without a working pass-through, rewriting logic has nowhere to live and overhead can’t be
separated from optimisation gains.

## In scope

1. FastAPI app (`src/proxy/`) exposing at least:
   - `POST /v1/chat/completions` (stream + non-stream)
   - `GET /v1/models` (forward upstream)
   - `GET /health`
2. Config: `VLLM_BASE_URL` default `http://localhost:8000/v1`, proxy listen e.g. `:9000`
3. **Pass-through only** — no prompt rewrite, batching, TTL, or routing
4. Same-node Aire run: vLLM `:8000` + proxy `:9000`; smoke test hits the proxy
5. Overhead study: direct vLLM vs via proxy (see measurement rules below)

## Out of scope (explicit — not Phase 2)

- Trimmer preprocessing
- Semantic sub-batching / canonical prefixes
- TTL / starvation escape
- Feature-aware routing / metadata eviction

---

## Engineering constraints (must-haves)

### 1. Streaming SSE must not buffer TTFT away

When forwarding vLLM’s stream through FastAPI:

- Response `media_type="text/event-stream"`
- Do **not** enable gzip / response-buffering middleware on this path
- Stream chunks as they arrive (e.g. `StreamingResponse` + async generator)
- Verify with the existing streaming TTFT client: first-token time must reflect the
  **first upstream chunk**, not a buffered flush

Silent buffering would make “proxy overhead” look artificially large / wrong.

### 2. Overhead = many repeats, not one delta

Single direct-vs-proxy runs are not dissertation-grade (jitter, GPU state, cold start).

- Same prompt, concurrency=1
- **N = 20–30** timed requests per path (direct vLLM `:8000` and proxy `:9000`)
- Discard or separately report **warmup** (e.g. first 2–3) if needed
- Report **mean ± std** (and optionally median / p95) for TTFT and total latency
- Claim “overhead is small” only from that aggregate, not a single pair of numbers

### 3. Persistent upstream HTTP client

- Use one long-lived `httpx.AsyncClient` (app lifespan / startup) for vLLM calls
- **Do not** create a new client per request (that folds TCP handshake into “proxy cost”
  and misrepresents steady-state overhead)

---

## Suggested build order

1. Scaffold `src/proxy/app.py` + config + lifespan `AsyncClient`
2. Implement pass-through chat completions (stream + non-stream) with correct SSE headers
3. `src/proxy/start_proxy.sh` (uvicorn on `:9000`, no gzip)
4. Extend timing harness for N-run direct vs proxy comparison (mean/std)
5. Aire smoke: server up → proxy up → N-run table recorded for methods notes

## Done when

- [x] Scaffold: streaming + non-streaming pass-through, health, models
- [x] Persistent `AsyncClient` (app lifespan)
- [x] SSE `text/event-stream` + no gzip in `start_proxy.sh`
- [x] N-run overhead harness (`src/proxy/bench_overhead.py`)
- [ ] Aire smoke: vLLM → proxy → single request via `:9000`
- [ ] Aire overhead table (N=20–30) saved for methods notes
- [x] No Trimmer/router code merged yet

"""Backends for Phase 6 systems."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from src.eval.schemas import RequestResult, WorkloadItem


def _extract_cached_tokens(usage: dict[str, Any] | None) -> int:
    if not usage:
        return 0
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        if cached is not None:
            try:
                return int(cached)
            except (TypeError, ValueError):
                return 0
    for key in ("cached_tokens", "prefix_cached_tokens"):
        if key in usage:
            try:
                return int(usage[key])
            except (TypeError, ValueError):
                pass
    return 0


def _estimate_prompt_tokens(prompt: str) -> int:
    # Rough fallback when stream usage omitted; decisions log notes this.
    return max(1, len(prompt) // 4)


@dataclass
class BackendResponse:
    ttft_ms: float
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    hit: bool
    disposition: str
    rewrite: str | None = None
    ttl: str | None = None
    ttl_wait_ms: float | None = None
    catalogue_task: str | None = None
    error: str | None = None
    output_preview: str | None = None
    client_send_ts: float | None = None


class EvalBackend(Protocol):
    name: str

    def complete(self, item: WorkloadItem, *, model: str, max_tokens: int) -> BackendResponse:
        ...


class OpenAICompatBackend:
    """Vanilla / APC / Optimizer Box via OpenAI-compatible HTTP."""

    def __init__(self, name: str, base_url: str, *, timeout_s: float = 300.0) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def complete(self, item: WorkloadItem, *, model: str, max_tokens: int) -> BackendResponse:
        t0 = time.perf_counter()
        ttft_ms = -1.0
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_s) as client:
                with client.stream(
                    "POST",
                    "/chat/completions",
                    headers={"Authorization": "Bearer EMPTY"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": item.prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    },
                ) as resp:
                    rewrite = resp.headers.get("x-optimizer-rewrite")
                    ttl = resp.headers.get("x-optimizer-ttl")
                    ttl_wait_raw = resp.headers.get("x-optimizer-ttl-wait-ms")
                    catalogue_task = resp.headers.get("x-optimizer-task")
                    ttl_wait_ms = float(ttl_wait_raw) if ttl_wait_raw else None

                    if resp.status_code >= 400:
                        err_body = resp.read().decode("utf-8", errors="replace")[:500]
                        latency_ms = (time.perf_counter() - t0) * 1000.0
                        return BackendResponse(
                            ttft_ms=latency_ms,
                            latency_ms=latency_ms,
                            prompt_tokens=0,
                            completion_tokens=0,
                            cached_tokens=0,
                            hit=False,
                            disposition="error",
                            rewrite=rewrite,
                            ttl=ttl,
                            ttl_wait_ms=ttl_wait_ms,
                            catalogue_task=catalogue_task,
                            error=f"HTTP {resp.status_code}: {err_body}",
                            client_send_ts=t0,
                        )

                    text_parts: list[str] = []
                    usage: dict[str, Any] = {}
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            payload = line[6:].strip()
                        elif line.startswith("data:"):
                            payload = line[5:].strip()
                        else:
                            continue
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            if ttft_ms < 0:
                                ttft_ms = (time.perf_counter() - t0) * 1000.0
                            text_parts.append(content)

            latency_ms = (time.perf_counter() - t0) * 1000.0
            if ttft_ms < 0:
                ttft_ms = latency_ms

            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            cached_tokens = _extract_cached_tokens(usage)
            if prompt_tokens == 0:
                prompt_tokens = _estimate_prompt_tokens(item.prompt)

            return BackendResponse(
                ttft_ms=ttft_ms,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                hit=cached_tokens > 0,
                disposition="ok",
                rewrite=rewrite,
                ttl=ttl,
                ttl_wait_ms=ttl_wait_ms,
                catalogue_task=catalogue_task,
                output_preview=("".join(text_parts))[:200],
                client_send_ts=t0,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return BackendResponse(
                ttft_ms=latency_ms,
                latency_ms=latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=0,
                hit=False,
                disposition="error",
                error=str(exc)[:500],
                client_send_ts=t0,
            )


class GPTCacheBackend:
    """
    Minimal semantic output cache (Phase 6c).

    Hit: return stored text (LLM bypassed); cached_tokens = stored prompt_tokens.
    Miss: forward to upstream vLLM and store response preview.
    """

    def __init__(
        self,
        upstream_url: str,
        *,
        timeout_s: float = 300.0,
        similarity_threshold: float = 0.92,
    ) -> None:
        self.name = "gptcache"
        self.upstream = OpenAICompatBackend(
            "gptcache_upstream", upstream_url, timeout_s=timeout_s
        )
        self.threshold = similarity_threshold
        self._store: list[tuple[Any, str, str, int]] = []  # emb, prompt, resp, ptoks
        self._encoder = None
        self._encoder_lock = threading.Lock()
        # Eager CPU load before any worker threads (avoids c>1 init races + GPU clash).
        self._ensure_encoder()

    def _ensure_encoder(self) -> None:
        if self._encoder is not None:
            return
        with self._encoder_lock:
            if self._encoder is not None:
                return
            try:
                import os

                # Keep MiniLM off the vLLM GPU even if the parent shell forgot
                # CUDA_VISIBLE_DEVICES=. Must set before importing/loading ST.
                os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

                from sentence_transformers import SentenceTransformer

                # device=cpu + disable meta/low-cpu init: ST 5.x + torch 2.8 can
                # raise "Cannot copy out of meta tensor" under threaded load.
                self._encoder = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    device="cpu",
                    model_kwargs={"low_cpu_mem_usage": False},
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "GPTCacheBackend MiniLM load failed "
                    f"(need sentence-transformers; prefer CPU while vLLM holds GPU): {exc}"
                ) from exc

    def _embed(self, text: str):
        self._ensure_encoder()
        assert self._encoder is not None
        return self._encoder.encode(text, normalize_embeddings=True)

    def _best_hit(self, prompt: str) -> tuple[str, int] | None:
        if not self._store:
            return None
        import numpy as np

        q = self._embed(prompt)
        best_score = -1.0
        best: tuple[str, int] | None = None
        for emb, _p, cached_resp, ptoks in self._store:
            score = float(np.dot(q, emb))
            if score > best_score:
                best_score = score
                best = (cached_resp, ptoks)
        if best is not None and best_score >= self.threshold:
            return best
        return None

    def complete(self, item: WorkloadItem, *, model: str, max_tokens: int) -> BackendResponse:
        t0 = time.perf_counter()
        hit = self._best_hit(item.prompt)
        if hit is not None:
            text, ptoks = hit
            ms = (time.perf_counter() - t0) * 1000.0
            return BackendResponse(
                ttft_ms=ms,
                latency_ms=ms,
                prompt_tokens=ptoks,
                completion_tokens=0,
                cached_tokens=ptoks,
                hit=True,
                disposition="gptcache_hit",
                output_preview=text[:200],
                client_send_ts=t0,
            )

        upstream = self.upstream.complete(item, model=model, max_tokens=max_tokens)
        if upstream.disposition == "ok" and upstream.output_preview:
            emb = self._embed(item.prompt)
            self._store.append(
                (emb, item.prompt, upstream.output_preview, max(upstream.prompt_tokens, 1))
            )
        upstream.disposition = (
            "gptcache_miss" if upstream.disposition == "ok" else upstream.disposition
        )
        upstream.hit = False
        upstream.cached_tokens = 0
        return upstream


def make_backend(system: str, base_url: str, *, timeout_s: float = 300.0) -> EvalBackend:
    system = system.lower()
    if system == "gptcache":
        return GPTCacheBackend(base_url, timeout_s=timeout_s)
    return OpenAICompatBackend(system, base_url, timeout_s=timeout_s)


def to_request_result(
    item: WorkloadItem, system: str, br: BackendResponse
) -> RequestResult:
    return RequestResult(
        req_id=item.req_id,
        system=system,
        tier=item.tier,
        task=item.task,
        doc_id=item.doc_id,
        prompt_chars=len(item.prompt),
        ttft_ms=br.ttft_ms,
        latency_ms=br.latency_ms,
        prompt_tokens=br.prompt_tokens,
        completion_tokens=br.completion_tokens,
        cached_tokens=br.cached_tokens,
        hit=br.hit,
        disposition=br.disposition,
        rewrite=br.rewrite,
        ttl=br.ttl,
        ttl_wait_ms=br.ttl_wait_ms,
        catalogue_task=br.catalogue_task,
        error=br.error,
        output_preview=br.output_preview,
        phrasing_source=item.phrasing_source,
        best_of_n_group=item.best_of_n_group,
        client_send_ts=br.client_send_ts,
    )

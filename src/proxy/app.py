"""
Optimizer Box proxy in front of vLLM.

Phase 2: pass-through HTTP + SSE.
Phase 4: optional schema rewrite onto block-aligned canonical prefixes
         (OPTIMIZER_REWRITE_MODE=on|tag_only|off).
Phase 5: optional admission hold + TTL starvation escape
         (OPTIMIZER_TTL_MODE=on|off).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src.proxy.config import vllm_base_url
from src.proxy.metrics_tsr import extract_usage_tokens, get_tsr_counters
from src.proxy.rewrite import rewrite_request
from src.proxy.rewrite.align import warm_alignment_cache
from src.proxy.ttl import TtlConfig, get_admission_hold

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("optimizer_box.proxy")

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    base = vllm_base_url()
    app.state.http = httpx.AsyncClient(
        base_url=base,
        timeout=httpx.Timeout(600.0, connect=30.0),
        headers={"Authorization": "Bearer EMPTY"},
    )
    app.state.vllm_base_url = base
    app.state.ttl = get_admission_hold(TtlConfig.from_env())
    print(f"[proxy] upstream VLLM_BASE_URL={base}")
    print(
        f"[proxy] TTL/admission-hold mode={app.state.ttl.config.mode} "
        f"hold_ms={app.state.ttl.config.admission_hold_ms} "
        f"max_ttl_ms={app.state.ttl.config.max_ttl_ms} "
        f"peers={app.state.ttl.config.batch_peers}"
    )
    try:
        warm_alignment_cache()
        print("[proxy] rewrite alignment cache warmed")
    except Exception as exc:  # noqa: BLE001 — proxy still serves; rewrites may bypass
        logger.warning("alignment warm-up failed (rewrites may bypass): %s", exc)
        print(f"[proxy] WARNING: alignment warm-up failed: {exc}")
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="Optimizer Box Proxy",
    version="0.6.0",
    description="Pass-through + Phase-4 rewrite + Phase-5 TTL hold + Phase-6 TSR metrics",
    lifespan=lifespan,
)


def _filter_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        if key.lower() == "authorization":
            continue
        out[key] = value
    return out


def _maybe_set_priority(body: dict[str, Any], *, escalated: bool, enabled: bool) -> None:
    if not enabled or not escalated:
        return
    # vLLM: lower priority value = higher scheduling priority (best-effort).
    body["priority"] = 0


@app.get("/health")
async def health() -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http
    upstream_ok = False
    try:
        r = await client.get("/models")
        upstream_ok = r.status_code == 200
    except httpx.HTTPError:
        upstream_ok = False
    ttl = getattr(app.state, "ttl", None)
    return {
        "status": "ok" if upstream_ok else "degraded",
        "upstream": app.state.vllm_base_url,
        "upstream_reachable": upstream_ok,
        "ttl_mode": ttl.config.mode if ttl else "unknown",
        "tsr": get_tsr_counters().snapshot(),
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Phase 6 TSR counters (source of truth for Optimizer Box runs)."""
    return get_tsr_counters().snapshot()


@app.post("/metrics/reset")
async def metrics_reset() -> dict[str, Any]:
    get_tsr_counters().reset()
    return get_tsr_counters().snapshot()


@app.get("/v1/models")
async def list_models() -> Response:
    client: httpx.AsyncClient = app.state.http
    r = await client.get("/models")
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    body = await request.json()
    body, decision = rewrite_request(body)

    ttl_hold = getattr(app.state, "ttl", None) or get_admission_hold()
    ttl_decision = await ttl_hold.admit(
        decision.catalogue_task,
        rewritten=(decision.action == "rewrite"),
    )
    _maybe_set_priority(
        body,
        escalated=ttl_decision.ttl_escalated,
        enabled=ttl_hold.config.set_priority,
    )

    debug_headers = {
        "X-Optimizer-Rewrite": decision.action,
        "X-Optimizer-Reason": decision.reason[:128],
        "X-Optimizer-TTL": ttl_decision.header_value(),
        "X-Optimizer-TTL-Wait-Ms": f"{ttl_decision.wait_ms:.2f}",
    }
    if decision.catalogue_task:
        debug_headers["X-Optimizer-Task"] = decision.catalogue_task

    stream = bool(body.get("stream", False))
    client: httpx.AsyncClient = app.state.http
    headers = _filter_request_headers(request)

    if stream:
        return await _stream_chat(client, body, headers, debug_headers)
    return await _json_chat(client, body, headers, debug_headers)


async def _json_chat(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    headers: dict[str, str],
    extra_headers: dict[str, str],
) -> Response:
    r = await client.post("/chat/completions", json=body, headers=headers)
    if r.status_code < 400:
        try:
            data = r.json()
            prompt_toks, cached_toks = extract_usage_tokens(data.get("usage"))
            get_tsr_counters().record(
                prompt_tokens=prompt_toks, cached_tokens=cached_toks
            )
        except Exception:  # noqa: BLE001 — never fail the client on metrics
            logger.debug("TSR record failed", exc_info=True)
    out_headers = dict(extra_headers)
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
        headers=out_headers,
    )


async def _stream_chat(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    headers: dict[str, str],
    extra_headers: dict[str, str],
) -> StreamingResponse:
    async def byte_stream() -> AsyncIterator[bytes]:
        import json as _json

        usage_acc: dict[str, Any] = {}
        async with client.stream(
            "POST",
            "/chat/completions",
            json=body,
            headers=headers,
        ) as upstream:
            if upstream.status_code >= 400:
                err = await upstream.aread()
                yield err
                return
            async for chunk in upstream.aiter_raw():
                if chunk:
                    # Best-effort parse usage from SSE for TSR counters
                    try:
                        for line in chunk.decode("utf-8", errors="ignore").splitlines():
                            if not line.startswith("data:"):
                                continue
                            payload = line.split(":", 1)[1].strip()
                            if payload == "[DONE]":
                                continue
                            obj = _json.loads(payload)
                            if obj.get("usage"):
                                usage_acc = obj["usage"]
                    except Exception:  # noqa: BLE001
                        pass
                    yield chunk
        if usage_acc:
            prompt_toks, cached_toks = extract_usage_tokens(usage_acc)
            get_tsr_counters().record(
                prompt_tokens=prompt_toks, cached_tokens=cached_toks
            )

    return StreamingResponse(
        byte_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **extra_headers,
        },
    )


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "optimizer-box-proxy",
            "phase": 6,
            "mode": "canonical-prefix-rewrite+ttl+tsr",
            "upstream": app.state.vllm_base_url,
        }
    )

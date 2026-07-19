"""
Optimizer Box proxy in front of vLLM.

Phase 2: pass-through HTTP + SSE.
Phase 4: optional schema rewrite onto block-aligned canonical prefixes
         (OPTIMIZER_REWRITE_MODE=on|tag_only|off).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src.proxy.config import vllm_base_url
from src.proxy.rewrite import rewrite_request
from src.proxy.rewrite.align import warm_alignment_cache

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
    print(f"[proxy] upstream VLLM_BASE_URL={base}")
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
    version="0.4.0",
    description="Pass-through + Phase-4 canonical prefix rewrite",
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


@app.get("/health")
async def health() -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http
    upstream_ok = False
    try:
        r = await client.get("/models")
        upstream_ok = r.status_code == 200
    except httpx.HTTPError:
        upstream_ok = False
    return {
        "status": "ok" if upstream_ok else "degraded",
        "upstream": app.state.vllm_base_url,
        "upstream_reachable": upstream_ok,
    }


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
    # Echo decision in a response header for debugging (SSE-safe).
    debug_headers = {
        "X-Optimizer-Rewrite": decision.action,
        "X-Optimizer-Reason": decision.reason[:128],
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
                    yield chunk

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
            "phase": 4,
            "mode": "canonical-prefix-rewrite",
            "upstream": app.state.vllm_base_url,
        }
    )

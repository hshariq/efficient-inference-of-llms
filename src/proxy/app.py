"""
Phase 2 pass-through FastAPI proxy in front of vLLM.

Clients → this app (:9000) → vLLM (:8000). No Trimmer / routing / TTL yet.
Uses a long-lived httpx.AsyncClient and streams SSE without response buffering.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src.proxy.config import vllm_base_url

# Headers that must not be blindly forwarded client → upstream / upstream → client
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
    # Persistent client — do not create per request (would inflate proxy overhead).
    app.state.http = httpx.AsyncClient(
        base_url=base,
        timeout=httpx.Timeout(600.0, connect=30.0),
        headers={"Authorization": "Bearer EMPTY"},
    )
    app.state.vllm_base_url = base
    print(f"[proxy] upstream VLLM_BASE_URL={base}")
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="Optimizer Box Proxy",
    version="0.2.0",
    description="Phase 2 pass-through only — no optimisation logic",
    lifespan=lifespan,
)


def _filter_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        if key.lower() == "authorization":
            # Upstream vLLM ignores auth; keep a dummy if client sent none.
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
    """Pass-through chat completions (stream or JSON)."""
    body = await request.json()
    stream = bool(body.get("stream", False))
    client: httpx.AsyncClient = app.state.http
    headers = _filter_request_headers(request)

    if stream:
        return await _stream_chat(client, body, headers)
    return await _json_chat(client, body, headers)


async def _json_chat(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    headers: dict[str, str],
) -> Response:
    r = await client.post("/chat/completions", json=body, headers=headers)
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )


async def _stream_chat(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    headers: dict[str, str],
) -> StreamingResponse:
    """
    Forward upstream SSE bytes as they arrive.
    media_type=text/event-stream + no gzip middleware → TTFT stays meaningful.
    """

    async def byte_stream() -> AsyncIterator[bytes]:
        async with client.stream(
            "POST",
            "/chat/completions",
            json=body,
            headers=headers,
        ) as upstream:
            if upstream.status_code >= 400:
                # Drain error body so the client still sees something useful.
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
            # Discourage reverse-proxy buffering if one is ever added in front.
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "optimizer-box-proxy",
            "phase": 2,
            "mode": "pass-through",
            "upstream": app.state.vllm_base_url,
        }
    )

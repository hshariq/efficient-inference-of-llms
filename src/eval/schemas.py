"""Request / result schemas for Phase 6 JSONL logging."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TIERS = ("exact", "semantic", "best_of_n", "lone_wolf")


@dataclass
class WorkloadItem:
    req_id: str
    tier: str  # exact | semantic | best_of_n | lone_wolf
    task: str | None  # catalogue task or None for lone_wolf
    doc_id: str | None
    prompt: str
    phrasing_source: str | None = None  # sharegpt | lmsys | moss | synthetic_doc | None
    best_of_n_group: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkloadItem:
        return cls(
            req_id=str(d["req_id"]),
            tier=str(d["tier"]),
            task=d.get("task"),
            doc_id=d.get("doc_id"),
            prompt=str(d["prompt"]),
            phrasing_source=d.get("phrasing_source"),
            best_of_n_group=d.get("best_of_n_group"),
            meta=dict(d.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RequestResult:
    req_id: str
    system: str
    tier: str
    task: str | None
    doc_id: str | None
    prompt_chars: int
    ttft_ms: float
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    hit: bool
    disposition: str  # ok | error | gptcache_hit | gptcache_miss
    rewrite: str | None = None
    ttl: str | None = None
    ttl_wait_ms: float | None = None
    catalogue_task: str | None = None
    error: str | None = None
    output_preview: str | None = None
    phrasing_source: str | None = None
    best_of_n_group: str | None = None
    client_send_ts: float | None = None  # time.perf_counter() at send
    bon_group_spread_ms: float | None = None  # filled for best_of_n in runner

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.cached_tokens)

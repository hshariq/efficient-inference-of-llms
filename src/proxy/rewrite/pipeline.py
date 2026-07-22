"""
Rewrite pipeline: tag → confidence → bypass or canonical-prefix rewrite.

Modes (env OPTIMIZER_REWRITE_MODE):
  off      — identity, no tagging
  tag_only — tag + log, identity body (Phase 4a)
  on       — full rewrite when confident (Phase 4b); default
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass
from typing import Any

from src.proxy.rewrite.align import align_system_content, light_normalize
from src.proxy.rewrite.catalogue import system_text_for_task
from src.proxy.rewrite.schema import SchemaTags, Task
from src.proxy.rewrite.tagging import TagConfig, tag_with_timing

logger = logging.getLogger("optimizer_box.rewrite")

DEFAULT_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class RewriteDecision:
    action: str  # bypass | rewrite | identity
    reason: str
    tags: SchemaTags | None
    catalogue_task: str | None = None
    rule_ms: float | None = None
    embed_ms: float | None = None
    embed_used: bool = False

    def log_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "action": self.action,
            "reason": self.reason,
            "catalogue_task": self.catalogue_task,
            "rule_ms": self.rule_ms,
            "embed_ms": self.embed_ms,
            "embed_used": self.embed_used,
        }
        if self.tags is not None:
            d["tags"] = {
                "domain": self.tags.domain.value,
                "task": self.tags.task.value,
                "length_class": self.tags.length_class.value,
                "confidence": self.tags.confidence,
                "entity_focus": self.tags.entity_focus.value,
                "action_type": self.tags.action_type.value,
                "excluded_terms": list(self.tags.excluded_terms),
            }
        else:
            d["tags"] = None
        return d


def _rewrite_mode() -> str:
    return os.environ.get("OPTIMIZER_REWRITE_MODE", "on").strip().lower()


def _threshold() -> float:
    return TagConfig.from_env().confidence_threshold


def _last_user_text(messages: list[dict[str, Any]]) -> str | None:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            # Multimodal / list content: flatten text parts only
            if isinstance(content, list):
                parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return "\n".join(parts) if parts else None
    return None


def rewrite_request(body: dict[str, Any]) -> tuple[dict[str, Any], RewriteDecision]:
    """
    Returns (possibly rewritten body, decision).
    Never raises on tag/rewrite failure — falls back to bypass.
    """
    mode = _rewrite_mode()
    if mode in ("off", "0", "false"):
        decision = RewriteDecision("identity", "rewrite_mode_off", None)
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        decision = RewriteDecision("bypass", "no_messages", None)
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    user_text = _last_user_text(messages)
    if not user_text:
        decision = RewriteDecision("bypass", "no_user_text", None)
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    timed = tag_with_timing(user_text, TagConfig.from_env())
    tags = timed.tags

    if mode == "tag_only":
        decision = RewriteDecision(
            "identity",
            "tag_only_mode",
            tags,
            tags.task.value,
            rule_ms=timed.rule_ms,
            embed_ms=timed.embed_ms,
            embed_used=timed.embed_used,
        )
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    # mode == on
    if tags.task == Task.UNKNOWN or tags.confidence < _threshold():
        decision = RewriteDecision(
            "bypass",
            "low_confidence_or_unknown_task",
            tags,
            tags.task.value,
            rule_ms=timed.rule_ms,
            embed_ms=timed.embed_ms,
            embed_used=timed.embed_used,
        )
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    system_proto = system_text_for_task(tags.task)
    if not system_proto:
        decision = RewriteDecision(
            "bypass",
            "no_catalogue_entry",
            tags,
            tags.task.value,
            rule_ms=timed.rule_ms,
            embed_ms=timed.embed_ms,
            embed_used=timed.embed_used,
        )
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

    try:
        system_aligned = align_system_content(system_proto)
        user_norm = light_normalize(user_text)
        new_messages = [
            {"role": "system", "content": system_aligned},
            {"role": "user", "content": user_norm},
        ]
        new_body = copy.deepcopy(body)
        new_body["messages"] = new_messages
        reason = "canonical_prefix_embed" if timed.embed_used else "canonical_prefix"
        decision = RewriteDecision(
            "rewrite",
            reason,
            tags,
            tags.task.value,
            rule_ms=timed.rule_ms,
            embed_ms=timed.embed_ms,
            embed_used=timed.embed_used,
        )
        logger.info("rewrite %s", decision.log_dict())
        return new_body, decision
    except Exception as exc:  # noqa: BLE001 — never break the proxy path
        decision = RewriteDecision(
            "bypass",
            f"align_or_rewrite_error:{type(exc).__name__}",
            tags,
            tags.task.value,
            rule_ms=timed.rule_ms,
            embed_ms=timed.embed_ms,
            embed_used=timed.embed_used,
        )
        logger.warning("rewrite failed, bypassing: %s", exc)
        logger.info("rewrite %s", decision.log_dict())
        return body, decision

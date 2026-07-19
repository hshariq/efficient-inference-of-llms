"""
Phase 4 rewrite package: schema tagging + canonical prefixes + block alignment.

Trimmer (filler stripping / paraphrase) is intentionally NOT implemented here.
"""

from src.proxy.rewrite.pipeline import RewriteDecision, rewrite_request

__all__ = ["RewriteDecision", "rewrite_request"]

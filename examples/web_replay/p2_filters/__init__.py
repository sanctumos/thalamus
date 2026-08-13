#!/usr/bin/env python3
"""
P2 accumulating filter + internal evaluate-to-escalate + P2 refine + breaker.

Non-LLM evidence accumulates until a trip; factoids are enumerated; an internal
Thalamus evaluation agent (not Sanctum/Letta) auto-decides escalate vs decline.
On escalate, P2 refine runs every N turns with a home-topic breaker (hysteresis).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

from .breaker import TopicBreaker, get_topic_state, start_topic_state
from .evaluator import evaluate_review, heuristic_evaluate
from .refine_engine import list_refine_passes, run_refine_pass
from .review import decide_review, get_review, list_reviews
from .schema import ensure_p2_tables, wipe_p2_runtime
from .scorer import P2Scorer, list_score_events, score_segment
from .seed import seed_default_pack
from .store import (
    get_filter_pack,
    get_settings,
    list_filter_packs,
    list_filter_rules,
    patch_filter_pack,
    patch_filter_rule,
    patch_settings,
)

__all__ = [
    "P2Scorer",
    "TopicBreaker",
    "decide_review",
    "ensure_p2_tables",
    "evaluate_review",
    "get_filter_pack",
    "get_review",
    "get_settings",
    "get_topic_state",
    "heuristic_evaluate",
    "list_filter_packs",
    "list_filter_rules",
    "list_refine_passes",
    "list_reviews",
    "list_score_events",
    "patch_filter_pack",
    "patch_filter_rule",
    "patch_settings",
    "run_refine_pass",
    "score_segment",
    "seed_default_pack",
    "start_topic_state",
    "wipe_p2_runtime",
]

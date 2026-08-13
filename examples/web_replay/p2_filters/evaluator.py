#!/usr/bin/env python3
"""
Internal Thalamus P2 evaluation agent — not a Sanctum/Letta agent.

On filter trip, consumes the review packet (window + factoids + structural
sketch + doctor project card) and decides escalate vs decline. Venice when
configured; deterministic heuristic otherwise / on failure.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .review import decide_review, get_review
from .store import get_settings

logger = logging.getLogger(__name__)

EVAL_SYSTEM = """You are Thalamus's internal P2 evaluation agent — not a chatbot.

You decide whether a conversation window that tripped a cheap non-LLM filter
should escalate to P2 conversational refinement (dialog beats / phase labels /
ops-aware cleanup). You are NOT the P2 refiner; you only gate it.

Escalate when the window looks like real multi-party work talk or a handoff
from ambient media into ops dialog (greetings, new speakers, tasking, project
nouns that match the project card).

Decline when the window is still ambient monologue (video/podcast pedagogy),
noise, or the trip looks like a false positive without dialog/ops substance.

Hard rules:
- Use ONLY the provided window text, factoids, structural sketch, and project card.
- Do NOT invent speaker names absent from the window or project card.
- Output ONLY a single JSON object: {"escalate": true|false, "rationale": "…"}.
- Rationale: one or two short sentences. No markdown fences.
"""

DEFAULT_PROJECT_CARD = (
    "Engagement: imaging social-sourcing; tools: Docket queue, RocketReach exports; "
    "operators: Mark + partner (name unknown unless in transcript)."
)


def _factoid_kinds(review: Dict[str, Any]) -> set:
    kinds = set()
    ev = review.get("evidence") or {}
    for hit in ev.get("hits") or []:
        k = hit.get("rule_kind")
        if k:
            kinds.add(str(k))
    for span in ev.get("salient_spans") or []:
        k = span.get("rule_kind")
        if k:
            kinds.add(str(k))
    return kinds


def heuristic_evaluate(review: Dict[str, Any]) -> Tuple[bool, str]:
    """Cheap non-LLM gate used when Venice is off / unavailable."""
    kinds = _factoid_kinds(review)
    strong = {
        "greeting_lexicon",
        "speaker_entry",
        "tasking_lexicon",
        "proper_noun_lexicon",
    }
    hit_strong = kinds & strong
    if "greeting_lexicon" in kinds:
        return True, (
            "Heuristic: greeting lexicon in factoids — ambient→dialog handoff signal."
        )
    if len(hit_strong) >= 2:
        return True, (
            f"Heuristic: multiple dialog/ops factoids ({', '.join(sorted(hit_strong))})."
        )
    if hit_strong:
        return True, (
            f"Heuristic: strong factoid {next(iter(hit_strong))} after filter trip."
        )
    return False, (
        "Heuristic: trip without greeting/tasking/proper-noun/speaker-entry factoids "
        "— treat as false positive."
    )


def _build_user_payload(review: Dict[str, Any], project_card: str) -> str:
    segments = review.get("window_segments") or []
    lines = []
    for s in segments[-40:]:
        sp = s.get("speaker_name") or "?"
        text = (s.get("text") or "").strip()
        lines.append(f"[{sp}] {text}")
    window = "\n".join(lines) if lines else "(empty window)"

    ev = review.get("evidence") or {}
    factoids = []
    for hit in ev.get("hits") or []:
        factoids.append(
            {
                "rule_kind": hit.get("rule_kind"),
                "delta": hit.get("delta"),
                "running_score": hit.get("running_score"),
                "evidence": hit.get("evidence"),
            }
        )
    for span in ev.get("salient_spans") or []:
        if span not in factoids:
            factoids.append({"salient": span})

    payload = {
        "question": review.get("question"),
        "running_score": review.get("running_score"),
        "project_card": project_card,
        "structural": review.get("structural") or {},
        "factoids": factoids,
        "window_transcript": window,
    }
    return (
        "Evaluate whether to escalate this P2 review packet.\n\n"
        + json.dumps(payload, indent=2, default=str)
    )


def _parse_decision(text: str) -> Optional[Tuple[bool, str]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", raw, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if "escalate" not in obj:
        return None
    esc = bool(obj.get("escalate"))
    rationale = str(obj.get("rationale") or obj.get("reason") or "").strip()
    if not rationale:
        rationale = "Evaluator returned escalate=%s with empty rationale." % esc
    return esc, rationale


def venice_evaluate(
    review: Dict[str, Any],
    *,
    project_card: str,
    model: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """Return (escalate, rationale, mode='venice')."""
    from ..llm import VENICE_BASE, active_model, load_venice_key

    key = load_venice_key()
    if not key:
        raise RuntimeError("VENICE_API_KEY not set")
    mid = (model or "").strip() or active_model()
    payload = {
        "model": mid,
        "messages": [
            {"role": "system", "content": EVAL_SYSTEM},
            {"role": "user", "content": _build_user_payload(review, project_card)},
        ],
        "temperature": 0.1,
        "max_tokens": 250,
    }
    req = urllib.request.Request(
        f"{VENICE_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
    content = (body["choices"][0]["message"]["content"] or "").strip()
    parsed = _parse_decision(content)
    if not parsed:
        raise RuntimeError(f"evaluator JSON parse failed: {content[:200]}")
    escalate, rationale = parsed
    return escalate, rationale, "venice"


def evaluate_review(
    db: Any,
    review_id: int,
    *,
    force_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the internal evaluator and persist decide_review.

    Returns hydrated review with evaluator metadata in decision_note / evidence.
    """
    review = get_review(db, review_id)
    if not review:
        raise ValueError(f"review {review_id} not found")
    if review.get("status") != "pending":
        return review

    settings = get_settings(db)
    mode = (force_mode or settings.get("p2_evaluator_mode") or "auto").strip().lower()
    project_card = (
        settings.get("p2_project_card") or DEFAULT_PROJECT_CARD
    ).strip() or DEFAULT_PROJECT_CARD
    model = (settings.get("p2_evaluator_model") or "").strip() or None

    escalate: bool
    rationale: str
    used: str

    if mode == "heuristic":
        escalate, rationale = heuristic_evaluate(review)
        used = "heuristic"
    elif mode == "venice":
        try:
            escalate, rationale, used = venice_evaluate(
                review, project_card=project_card, model=model
            )
        except (
            RuntimeError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            KeyError,
            IndexError,
            TimeoutError,
        ) as e:
            logger.warning("Venice P2 evaluator failed (%s); heuristic fallback", e)
            escalate, rationale = heuristic_evaluate(review)
            used = "heuristic_fallback"
            rationale = f"[venice failed: {e}] {rationale}"
    else:  # auto
        from ..llm import load_venice_key

        if load_venice_key():
            try:
                escalate, rationale, used = venice_evaluate(
                    review, project_card=project_card, model=model
                )
            except (
                RuntimeError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                KeyError,
                IndexError,
                TimeoutError,
            ) as e:
                logger.warning("Venice P2 evaluator failed (%s); heuristic", e)
                escalate, rationale = heuristic_evaluate(review)
                used = "heuristic_fallback"
                rationale = f"[venice failed: {e}] {rationale}"
        else:
            escalate, rationale = heuristic_evaluate(review)
            used = "heuristic"

    note = f"[{used}] {rationale}"
    decided = decide_review(db, review_id, escalate=escalate, note=note)
    # Attach transient fields for SSE / UI (not all persisted as columns)
    if decided:
        decided["evaluator_mode"] = used
        decided["evaluator_rationale"] = rationale
        decided["escalate"] = escalate
    return decided or review

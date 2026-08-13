#!/usr/bin/env python3
"""
P2 refine engine — periodic whole-window conversational refinement.

Runs only after filter escalate. Every N turns (breaker on), re-analyzes the
window in greater context (punctuation, turns, topic) via Venice (stub fallback).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .schema import ensure_p2_tables
from .store import get_settings

logger = logging.getLogger(__name__)

P2_REFINE_SYSTEM = """You are Thalamus's P2 conversational refinement engine.

You re-analyze a rolling window of ASR transcript in greater context — not a
chatbot, not a summarizer for a human. Your output feeds a live pane.

You are given (a) already-refined earlier context and (b) NEW raw turns.

Hard rules:
- Output ONLY the refined lines for the NEW turns — never repeat context lines.
- Preserve speaker turns; use the speaker labels given (SPEAKER_00, etc.).
- Fix punctuation, casing, obvious ASR errors, and run-on fragments using context.
- Do NOT invent names, facts, or commitments not in the window or project card.
- Output format, one per new turn:
  [SPEAKER_XX] cleaned text
- No preface, no markdown fences, no commentary.
"""


def _row_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def _fetch_window_segments(
    db: Any, *, start_raw_id: int, max_segments: int
) -> List[Dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT rs.id, rs.text, rs.start_time, rs.end_time,
                   s.name AS speaker_name
            FROM raw_segments rs
            JOIN speakers s ON s.id = rs.speaker_id
            WHERE rs.id >= ?
            ORDER BY rs.id ASC
            LIMIT ?
            """,
            (int(start_raw_id), int(max_segments)),
        ).fetchall()
    return [_row_dict(r) for r in rows]


def _format_window(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for s in segments:
        sp = s.get("speaker_name") or "SPEAKER"
        text = (s.get("text") or "").strip()
        if text:
            lines.append(f"[{sp}] {text}")
    return "\n".join(lines)


def stub_p2_refine(window_text: str) -> str:
    lines = [l for l in window_text.splitlines() if l.strip()]
    return "\n".join(lines)


def venice_p2_refine(
    context_text: str,
    new_text: str,
    *,
    project_card: str,
    model: Optional[str] = None,
) -> Tuple[str, str]:
    from ..llm import VENICE_BASE, active_model, load_venice_key

    key = load_venice_key()
    if not key:
        raise RuntimeError("VENICE_API_KEY not set")
    mid = (model or "").strip() or active_model()
    user = (
        "Project card (context only — do not invent beyond it):\n"
        f"{project_card}\n\n"
        "Already-refined earlier context (do NOT repeat these lines):\n"
        "<<<CONTEXT>>>\n"
        f"{context_text or '(none — this is the first pass)'}\n"
        "<<<END>>>\n\n"
        "NEW raw turns to refine (output ONLY these, cleaned):\n"
        "<<<NEW>>>\n"
        f"{new_text}\n"
        "<<<END>>>"
    )
    payload = {
        "model": mid,
        "messages": [
            {"role": "system", "content": P2_REFINE_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
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
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode())
    text = (body["choices"][0]["message"]["content"] or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text, "venice"


def run_refine_pass(
    db: Any,
    *,
    anchor_raw_id: int,
    after_raw_id: Optional[int] = None,
    topic_score: Optional[float],
    home_terms: List[str],
    force_stub: bool = False,
) -> Dict[str, Any]:
    """One P2 refine pass over NEW turns only; persists p2_refine_passes row.

    The full rolling window (from anchor_raw_id, capped) is used as *context*,
    but only segments with id > after_raw_id are emitted — each pass is the
    delta vs the previous pass, not a re-render of the whole window.
    """
    ensure_p2_tables(db)
    settings = get_settings(db)
    max_segments = int(settings["p2_refine_max_segments_i"])
    segments = _fetch_window_segments(
        db, start_raw_id=anchor_raw_id, max_segments=max_segments
    )
    after = int(after_raw_id) if after_raw_id is not None else None
    if after is None:
        after = int(anchor_raw_id) - 1
    context_segments = [s for s in segments if int(s["id"]) <= after]
    new_segments = [s for s in segments if int(s["id"]) > after]

    if not new_segments:
        return {
            "id": None,
            "pass_index": None,
            "mode": "stub",
            "text": "",
            "topic_score": topic_score,
            "window_end_raw_id": after,
            "skipped": True,
        }

    # Prompt economy: tail of context is what matters for the new turns
    context_text = _format_window(context_segments[-40:])
    new_text = _format_window(new_segments)
    project_card = settings["p2_project_card"]
    model = settings["p2_refine_model"] or None

    mode = "stub"
    text = ""
    if force_stub:
        text = stub_p2_refine(new_text)
    else:
        try:
            text, mode = venice_p2_refine(
                context_text, new_text, project_card=project_card, model=model
            )
        except (
            RuntimeError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            KeyError,
            IndexError,
            TimeoutError,
        ) as e:
            logger.warning("P2 Venice refine failed (%s); stub", e)
            text = stub_p2_refine(new_text)
            mode = "stub"

    window_end = int(new_segments[-1]["id"])
    window_start = int(new_segments[0]["id"])

    with db.get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO p2_refine_passes
                (pass_index, window_start_raw_id, window_end_raw_id, status,
                 mode, text, topic_score, home_terms_json)
            VALUES (
                (SELECT COALESCE(MAX(pass_index), 0) + 1 FROM p2_refine_passes),
                ?, ?, 'on', ?, ?, ?, ?
            )
            """,
            (
                window_start,
                window_end,
                mode,
                text,
                float(topic_score) if topic_score is not None else None,
                json.dumps(list(home_terms or [])),
            ),
        )
        rid = int(cur.lastrowid)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM p2_refine_passes WHERE id = ?", (rid,)
        ).fetchone()
    out = _row_dict(row)
    out["skipped"] = False
    return out


def list_refine_passes(db: Any, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM p2_refine_passes ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_row_dict(r) for r in rows]

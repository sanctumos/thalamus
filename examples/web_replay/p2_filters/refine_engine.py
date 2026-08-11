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

Hard rules:
- Preserve speaker turns; use the speaker labels given (SPEAKER_00, etc.).
- Fix punctuation, casing, obvious ASR errors, and run-on fragments using context.
- Do NOT invent names, facts, or commitments not in the window or project card.
- Output ONLY the refined transcript lines, one per turn, format:
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
    window_text: str,
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
        "Refine this rolling ASR window into clean turns:\n\n"
        "<<<WINDOW>>>\n"
        f"{window_text}\n"
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
    topic_score: Optional[float],
    home_terms: List[str],
    force_stub: bool = False,
) -> Dict[str, Any]:
    """One P2 refine pass; persists p2_refine_passes row. Returns row dict."""
    ensure_p2_tables(db)
    settings = get_settings(db)
    max_segments = int(settings["p2_refine_max_segments_i"])
    segments = _fetch_window_segments(
        db, start_raw_id=anchor_raw_id, max_segments=max_segments
    )
    window_text = _format_window(segments)
    project_card = settings["p2_project_card"]
    model = settings["p2_refine_model"] or None

    if not window_text.strip():
        return {
            "id": None,
            "pass_index": None,
            "mode": "stub",
            "text": "",
            "topic_score": topic_score,
            "window_end_raw_id": anchor_raw_id,
            "skipped": True,
        }

    mode = "stub"
    text = ""
    if force_stub:
        text = stub_p2_refine(window_text)
    else:
        try:
            text, mode = venice_p2_refine(
                window_text, project_card=project_card, model=model
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
            text = stub_p2_refine(window_text)
            mode = "stub"

    window_end = int(segments[-1]["id"]) if segments else int(anchor_raw_id)
    window_start = int(segments[0]["id"]) if segments else int(anchor_raw_id)

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

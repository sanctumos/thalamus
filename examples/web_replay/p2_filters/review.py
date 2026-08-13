#!/usr/bin/env python3
"""
P2 review prompts — trip snapshots + escalate / decline decisions.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


QUESTION = (
    "Internal evaluator: escalate this window to P2 conversational refinement?"
)


def _row_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def _structural_sketch(segments: List[Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    long_s = float(settings.get("long_segment_seconds_f") or 20)
    short_s = float(settings.get("short_segment_seconds_f") or 8)
    by_speaker: Dict[str, int] = {}
    long_n = short_n = 0
    durations = []
    for s in segments:
        name = getattr(s, "speaker_name", None) or s.get("speaker_name")
        by_speaker[name] = by_speaker.get(name, 0) + 1
        dur = getattr(s, "duration", None)
        if dur is None:
            dur = float(s.get("end_time", 0)) - float(s.get("start_time", 0))
        durations.append(dur)
        if dur >= long_s:
            long_n += 1
        if dur <= short_s:
            short_n += 1
    gap = None
    if len(segments) >= 2:
        a = segments[-2]
        b = segments[-1]
        a_end = getattr(a, "end_time", None) or a.get("end_time")
        b_start = getattr(b, "start_time", None) or b.get("start_time")
        try:
            gap = float(b_start) - float(a_end)
        except Exception:
            gap = None
    return {
        "segment_count": len(segments),
        "speaker_turn_counts": by_speaker,
        "long_monologue_segments": long_n,
        "short_dialog_segments": short_n,
        "mean_duration": (sum(durations) / len(durations)) if durations else 0,
        "wall_gap_before_last": gap,
    }


def create_review_prompt(
    db: Any,
    *,
    pack_id: int,
    running_score: float,
    trip_raw_segment_id: int,
    window_segments: List[Any],
    evidence_hits: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    window_ids = []
    salient = []
    for s in window_segments:
        rid = getattr(s, "raw_id", None)
        if rid is None:
            rid = s.get("raw_id") or s.get("id")
        window_ids.append(int(rid))
    for hit in evidence_hits:
        ev = hit.get("evidence") or {}
        if "matched" in ev:
            salient.append(
                {
                    "rule_kind": hit.get("rule_kind"),
                    "matched": ev.get("matched"),
                    "excerpt": ev.get("text_excerpt"),
                }
            )
        elif hit.get("rule_kind") in ("speaker_entry", "segment_length_flip"):
            salient.append({"rule_kind": hit.get("rule_kind"), **ev})

    structural = _structural_sketch(window_segments, settings)
    evidence = {
        "hits": evidence_hits,
        "salient_spans": salient,
        "trip_threshold": settings.get("trip_threshold_f"),
        "why": (
            "Accumulated non-LLM filter score crossed the trip threshold. "
            "Factoids below feed Thalamus's internal evaluation agent, which "
            "auto-decides whether to escalate to P2 conversational refinement."
        ),
    }

    with db.get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO p2_review_prompts
                (pack_id, status, running_score, trip_raw_segment_id,
                 window_raw_ids_json, evidence_json, structural_json, question)
            VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                pack_id,
                float(running_score),
                int(trip_raw_segment_id),
                json.dumps(window_ids),
                json.dumps(evidence),
                json.dumps(structural),
                QUESTION,
            ),
        )
        rid = int(cur.lastrowid)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM p2_review_prompts WHERE id = ?", (rid,)
        ).fetchone()

    return _hydrate_review(db, _row_dict(row))


def _hydrate_review(db: Any, d: Dict[str, Any]) -> Dict[str, Any]:
    if not d:
        return d
    try:
        d["window_raw_ids"] = json.loads(d.get("window_raw_ids_json") or "[]")
    except json.JSONDecodeError:
        d["window_raw_ids"] = []
    try:
        d["evidence"] = json.loads(d.get("evidence_json") or "{}")
    except json.JSONDecodeError:
        d["evidence"] = {}
    try:
        d["structural"] = json.loads(d.get("structural_json") or "{}")
    except json.JSONDecodeError:
        d["structural"] = {}

    # Attach conversation-so-far texts for the review card
    ids = d.get("window_raw_ids") or []
    segments = []
    if ids:
        placeholders = ",".join("?" * len(ids))
        with db.get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT rs.id, rs.session_id, rs.text, rs.start_time, rs.end_time,
                       s.name AS speaker_name
                FROM raw_segments rs
                JOIN speakers s ON s.id = rs.speaker_id
                WHERE rs.id IN ({placeholders})
                ORDER BY rs.id ASC
                """,
                tuple(ids),
            ).fetchall()
        for r in rows:
            if hasattr(r, "keys"):
                segments.append({k: r[k] for k in r.keys()})
            else:
                segments.append(dict(r))
    d["window_segments"] = segments
    d["question"] = d.get("question") or QUESTION
    return d


def list_reviews(db: Any, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with db.get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM p2_review_prompts WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM p2_review_prompts ORDER BY id DESC"
            ).fetchall()
    return [_hydrate_review(db, _row_dict(r)) for r in rows]


def get_review(db: Any, review_id: int) -> Optional[Dict[str, Any]]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM p2_review_prompts WHERE id = ?", (review_id,)
        ).fetchone()
    if not row:
        return None
    return _hydrate_review(db, _row_dict(row))


def decide_review(
    db: Any,
    review_id: int,
    *,
    escalate: bool,
    note: str = "",
) -> Optional[Dict[str, Any]]:
    status = "escalated" if escalate else "declined"
    with db.get_db() as conn:
        cur = conn.execute(
            """
            UPDATE p2_review_prompts SET
                status = ?,
                decision_note = ?,
                decided_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (status, note or "", review_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            # already decided or missing
            row = conn.execute(
                "SELECT * FROM p2_review_prompts WHERE id = ?", (review_id,)
            ).fetchone()
            if not row:
                return None
            return _hydrate_review(db, _row_dict(row))
    return get_review(db, review_id)

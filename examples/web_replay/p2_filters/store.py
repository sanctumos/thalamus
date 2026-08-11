#!/usr/bin/env python3
"""
Doctor-facing read/write for thalamus_settings, filter packs, and rules.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .schema import ensure_p2_tables

DEFAULT_PROJECT_CARD = (
    "Engagement: imaging social-sourcing; tools: Docket queue, RocketReach exports; "
    "operators: Mark + partner (name unknown unless in transcript)."
)

DEFAULT_SETTINGS = {
    "active_filter_pack_slug": "video_to_dialog_handoff",
    # Cumulative bar — greeting alone must not tip (was 7; hi+speaker ≈ 7).
    "trip_threshold": "12",
    # Trip also requires ≥1 ops/substance factoid in the epoch (not just hi/structure).
    "trip_require_substance": "true",
    "enrichment_gate_enabled": "false",
    "score_decay_per_segment": "0.15",
    "post_trip_tail_segments": "0",
    "long_segment_seconds": "20",
    "short_segment_seconds": "8",
    "monologue_stretch_segments": "3",
    # Internal P2 evaluation agent (not Sanctum/Letta) — auto-decides escalate.
    "p2_evaluator_mode": "auto",  # auto | venice | heuristic
    "p2_evaluator_model": "",  # empty → same Venice refine model
    "p2_project_card": DEFAULT_PROJECT_CARD,
    "p2_auto_evaluate": "true",
    # P2 refine engine (post-escalate) — see P2_REFINE_DESIGN.md
    "p2_refine_every_turns": "5",
    "p2_refine_max_segments": "80",
    "p2_refine_model": "",
    # Home-topic breaker (hysteresis on/off)
    "p2_breaker_enabled": "true",
    "p2_breaker_off_score": "0.18",
    "p2_breaker_on_score": "0.34",
    "p2_breaker_off_streak": "3",
    "p2_breaker_on_streak": "2",
    "p2_breaker_closing_penalty": "0.08",
}


def _row_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def ensure_default_settings(db: Any) -> None:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT INTO thalamus_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, value),
            )
        # One-time bump: old default 7 tipped on greeting alone.
        row = conn.execute(
            "SELECT value FROM thalamus_settings WHERE key = 'trip_threshold'"
        ).fetchone()
        if row is not None:
            cur = row["value"] if hasattr(row, "keys") else row[0]
            if str(cur).strip() == "7":
                conn.execute(
                    """
                    UPDATE thalamus_settings
                    SET value = '12', updated_at = CURRENT_TIMESTAMP
                    WHERE key = 'trip_threshold'
                    """
                )
        conn.commit()


def get_settings(db: Any) -> Dict[str, Any]:
    ensure_default_settings(db)
    with db.get_db() as conn:
        rows = conn.execute("SELECT key, value FROM thalamus_settings").fetchall()
    out = dict(DEFAULT_SETTINGS)
    for r in rows:
        d = _row_dict(r)
        out[str(d["key"])] = str(d["value"])
    # typed helpers for callers
    out["trip_threshold_f"] = float(out.get("trip_threshold") or 7)
    out["score_decay_per_segment_f"] = float(out.get("score_decay_per_segment") or 0.15)
    out["enrichment_gate_enabled_b"] = str(
        out.get("enrichment_gate_enabled") or "false"
    ).lower() in ("1", "true", "yes")
    out["long_segment_seconds_f"] = float(out.get("long_segment_seconds") or 20)
    out["short_segment_seconds_f"] = float(out.get("short_segment_seconds") or 8)
    out["monologue_stretch_segments_i"] = int(
        float(out.get("monologue_stretch_segments") or 3)
    )
    out["p2_auto_evaluate_b"] = str(
        out.get("p2_auto_evaluate") or "true"
    ).lower() in ("1", "true", "yes")
    out["trip_require_substance_b"] = str(
        out.get("trip_require_substance") or "true"
    ).lower() in ("1", "true", "yes")
    out["p2_evaluator_mode"] = (
        str(out.get("p2_evaluator_mode") or "auto").strip().lower() or "auto"
    )
    out["p2_evaluator_model"] = str(out.get("p2_evaluator_model") or "").strip()
    out["p2_project_card"] = str(
        out.get("p2_project_card") or DEFAULT_PROJECT_CARD
    ).strip() or DEFAULT_PROJECT_CARD
    out["p2_refine_every_turns_i"] = int(
        float(out.get("p2_refine_every_turns") or 5)
    )
    out["p2_refine_max_segments_i"] = int(
        float(out.get("p2_refine_max_segments") or 80)
    )
    out["p2_refine_model"] = str(out.get("p2_refine_model") or "").strip()
    out["p2_breaker_enabled_b"] = str(
        out.get("p2_breaker_enabled") or "true"
    ).lower() in ("1", "true", "yes")
    out["p2_breaker_off_score_f"] = float(
        out.get("p2_breaker_off_score") or 0.18
    )
    out["p2_breaker_on_score_f"] = float(
        out.get("p2_breaker_on_score") or 0.34
    )
    out["p2_breaker_off_streak_i"] = int(
        float(out.get("p2_breaker_off_streak") or 3)
    )
    out["p2_breaker_on_streak_i"] = int(
        float(out.get("p2_breaker_on_streak") or 2)
    )
    out["p2_breaker_closing_penalty_f"] = float(
        out.get("p2_breaker_closing_penalty") or 0.08
    )
    return out


def patch_settings(db: Any, updates: Dict[str, Any]) -> Dict[str, Any]:
    ensure_default_settings(db)
    allowed = set(DEFAULT_SETTINGS.keys())
    with db.get_db() as conn:
        for key, value in updates.items():
            if key not in allowed:
                continue
            conn.execute(
                """
                INSERT INTO thalamus_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )
        conn.commit()
    return get_settings(db)


def list_filter_packs(db: Any) -> List[Dict[str, Any]]:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM filter_packs ORDER BY id ASC"
        ).fetchall()
    return [_row_dict(r) for r in rows]


def get_filter_pack(db: Any, pack_id: Optional[int] = None, slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        if pack_id is not None:
            row = conn.execute(
                "SELECT * FROM filter_packs WHERE id = ?", (pack_id,)
            ).fetchone()
        elif slug:
            row = conn.execute(
                "SELECT * FROM filter_packs WHERE slug = ?", (slug,)
            ).fetchone()
        else:
            return None
    return _row_dict(row) if row else None


def list_filter_rules(db: Any, pack_id: int) -> List[Dict[str, Any]]:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM filter_rules
            WHERE pack_id = ?
            ORDER BY priority ASC, id ASC
            """,
            (pack_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        try:
            d["params"] = json.loads(d.get("params_json") or "{}")
        except json.JSONDecodeError:
            d["params"] = {}
        out.append(d)
    return out


def patch_filter_pack(db: Any, pack_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ensure_p2_tables(db)
    fields = []
    vals: List[Any] = []
    for key in ("title", "notes", "enabled"):
        if key not in updates:
            continue
        fields.append(f"{key} = ?")
        val = updates[key]
        if key == "enabled":
            val = 1 if val in (True, 1, "1", "true", "yes") else 0
        vals.append(val)
    if not fields:
        return get_filter_pack(db, pack_id=pack_id)
    fields.append("updated_at = CURRENT_TIMESTAMP")
    vals.append(pack_id)
    with db.get_db() as conn:
        conn.execute(
            f"UPDATE filter_packs SET {', '.join(fields)} WHERE id = ?",
            tuple(vals),
        )
        conn.commit()
    return get_filter_pack(db, pack_id=pack_id)


def patch_filter_rule(db: Any, rule_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ensure_p2_tables(db)
    fields = []
    vals: List[Any] = []
    mapping = {
        "weight": "weight",
        "enabled": "enabled",
        "priority": "priority",
        "kind": "kind",
        "params": "params_json",
        "params_json": "params_json",
    }
    for src, col in mapping.items():
        if src not in updates:
            continue
        fields.append(f"{col} = ?")
        val = updates[src]
        if col == "enabled":
            val = 1 if val in (True, 1, "1", "true", "yes") else 0
        if col == "params_json" and not isinstance(val, str):
            val = json.dumps(val)
        vals.append(val)
    if not fields:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM filter_rules WHERE id = ?", (rule_id,)
            ).fetchone()
        if not row:
            return None
        d = _row_dict(row)
        try:
            d["params"] = json.loads(d.get("params_json") or "{}")
        except json.JSONDecodeError:
            d["params"] = {}
        return d
    fields.append("updated_at = CURRENT_TIMESTAMP")
    vals.append(rule_id)
    with db.get_db() as conn:
        conn.execute(
            f"UPDATE filter_rules SET {', '.join(fields)} WHERE id = ?",
            tuple(vals),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM filter_rules WHERE id = ?", (rule_id,)
        ).fetchone()
    if not row:
        return None
    d = _row_dict(row)
    try:
        d["params"] = json.loads(d.get("params_json") or "{}")
    except json.JSONDecodeError:
        d["params"] = {}
    return d


def active_pack_and_rules(db: Any) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    settings = get_settings(db)
    slug = settings.get("active_filter_pack_slug") or "video_to_dialog_handoff"
    pack = get_filter_pack(db, slug=slug)
    if not pack or not int(pack.get("enabled") or 0):
        return pack, [], settings
    rules = [r for r in list_filter_rules(db, int(pack["id"])) if int(r.get("enabled") or 0)]
    return pack, rules, settings

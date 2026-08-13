#!/usr/bin/env python3
"""
Demo DB helpers — reuse examples/database.py schema with an isolated path.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

EXAMPLES_DIR = Path(__file__).resolve().parents[1]


def _ensure_examples_path() -> None:
    p = str(EXAMPLES_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def load_database(db_path: Path):
    """Import database module pointed at db_path."""
    _ensure_examples_path()
    import database as db  # type: ignore

    db.DB_PATH = str(db_path)
    return db


def reset_db(db_path: Path):
    """Wipe demo replay tables only — preserve app_secrets + doctor filter config."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = load_database(db_path)
    db.init_db()
    from .secrets_store import ensure_secrets_table
    from .p2_filters.schema import ensure_p2_tables, wipe_p2_runtime
    from .p2_filters.seed import seed_default_pack

    ensure_secrets_table(db)
    ensure_p2_tables(db)
    with db.get_db() as conn:
        conn.execute("DELETE FROM segment_usage")
        conn.execute("DELETE FROM refined_segments")
        conn.execute("DELETE FROM raw_segments")
        conn.execute("DELETE FROM speakers")
        conn.execute("DELETE FROM sessions")
        # Reset autoincrement counters for demo tables if present
        try:
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('segment_usage','refined_segments','raw_segments','speakers','sessions')"
            )
        except Exception:
            pass
        conn.commit()
    wipe_p2_runtime(db)
    seed_default_pack(db)
    return db


def open_db(db_path: Path):
    """Open existing demo DB (or create empty schema) without wiping rows."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = load_database(db_path)
    db.init_db()
    from .secrets_store import ensure_secrets_table
    from .p2_filters.schema import ensure_p2_tables
    from .p2_filters.seed import seed_default_pack

    ensure_secrets_table(db)
    ensure_p2_tables(db)
    seed_default_pack(db)
    return db


def ingest_event(db, event: Dict[str, Any]) -> List[int]:
    """Insert one NDJSON event into raw_segments. Returns new raw ids.

    Stores the **text** session_id on raw_segments (schema is TEXT) so refine
    queries match — unlike the legacy integer quirk in thalamus_app.
    """
    from datetime import datetime

    current_timestamp = datetime.fromisoformat(
        event["log_timestamp"].replace("Z", "+00:00")
    )
    session_key = event["session_id"]
    db.get_or_create_session(session_key)
    ids: List[int] = []
    for segment in event.get("segments") or []:
        speaker_id = int(segment["speaker_id"])
        db_speaker_id = db.get_or_create_speaker(
            speaker_id=speaker_id,
            speaker_name=segment["speaker"],
            is_user=segment.get("is_user", False),
        )
        rid = db.insert_segment(
            session_id=session_key,
            speaker_id=db_speaker_id,
            text=segment["text"],
            start_time=segment["start"],
            end_time=segment["end"],
            log_timestamp=current_timestamp,
        )
        ids.append(int(rid))
    return ids


def snapshot(db) -> Dict[str, Any]:
    with db.get_db() as conn:
        raw = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rs.id, rs.session_id, rs.text, rs.start_time, rs.end_time,
                       rs.timestamp, s.name AS speaker_name
                FROM raw_segments rs
                JOIN speakers s ON s.id = rs.speaker_id
                ORDER BY rs.id ASC
                """
            )
        ]
        refined = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rf.id, rf.session_id, rf.text, rf.start_time, rf.end_time,
                       rf.source_segments, s.name AS speaker_name
                FROM refined_segments rf
                JOIN speakers s ON s.id = rf.refined_speaker_id
                ORDER BY rf.id ASC
                """
            )
        ]
        usage = [
            dict(r)
            for r in conn.execute(
                "SELECT raw_segment_id, refined_segment_id FROM segment_usage ORDER BY raw_segment_id"
            )
        ]
    return {"raw_segments": raw, "refined_segments": refined, "segment_usage": usage}

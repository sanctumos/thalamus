#!/usr/bin/env python3
"""
App secrets in the demo SQLite DB — survive Play/Reset (demo tables only wiped).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import db_util

VENICE_KEY_NAME = "VENICE_API_KEY"
VENICE_MODEL_NAME = "VENICE_MODEL"


def ensure_secrets_table(db) -> None:
    with db.get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_secrets (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def get_secret(db_path: Path, key: str) -> Optional[str]:
    db = db_util.open_db(Path(db_path))
    ensure_secrets_table(db)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    val = (row["value"] if hasattr(row, "keys") else row[0]) or ""
    val = str(val).strip()
    return val or None


def set_secret(db_path: Path, key: str, value: str) -> None:
    db = db_util.open_db(Path(db_path))
    ensure_secrets_table(db)
    value = (value or "").strip()
    with db.get_db() as conn:
        if not value:
            conn.execute("DELETE FROM app_secrets WHERE key = ?", (key,))
        else:
            conn.execute(
                """
                INSERT INTO app_secrets (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
        conn.commit()


def secret_present(db_path: Path, key: str) -> bool:
    return bool(get_secret(db_path, key))


def secret_hint(db_path: Path, key: str) -> str:
    """Masked hint for UI — never returns the full secret."""
    val = get_secret(db_path, key)
    if not val:
        return ""
    if len(val) <= 4:
        return "••••"
    return "••••" + val[-4:]

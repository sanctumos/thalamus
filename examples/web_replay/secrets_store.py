#!/usr/bin/env python3
"""
App secrets in the demo SQLite DB — survive Play/Reset (demo tables only wiped).

Secrets I/O uses direct sqlite3 connections to the given path. It must NEVER
go through db_util.open_db/load_database: those re-point the process-global
database.DB_PATH, so a per-call key lookup would silently redirect every other
thread's replay reads/writes to the secrets file. (Latent bug — invisible in
the server where both paths are the same file, corrupting everywhere else.)

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

VENICE_KEY_NAME = "VENICE_API_KEY"
VENICE_MODEL_NAME = "VENICE_MODEL"

_CREATE = """
CREATE TABLE IF NOT EXISTS app_secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE)
    conn.commit()
    return conn


def ensure_secrets_table(db) -> None:
    with db.get_db() as conn:
        conn.execute(_CREATE)
        conn.commit()


def get_secret(db_path: Path, key: str) -> Optional[str]:
    conn = _connect(Path(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    val = (row["value"] if hasattr(row, "keys") else row[0]) or ""
    val = str(val).strip()
    return val or None


def set_secret(db_path: Path, key: str, value: str) -> None:
    value = (value or "").strip()
    conn = _connect(Path(db_path))
    try:
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
    finally:
        conn.close()


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

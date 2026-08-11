#!/usr/bin/env python3
"""
P2 / Thalamus-doctor SQLite schema.

Config tables survive Play/Reset (like app_secrets). Runtime score/review
rows are wiped with replay tables.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

from typing import Any


def ensure_p2_tables(db: Any) -> None:
    """Idempotent CREATE for doctor config + runtime P2 tables."""
    with db.get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS thalamus_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS filter_packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS filter_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER NOT NULL REFERENCES filter_packs(id),
                kind TEXT NOT NULL,
                params_json TEXT NOT NULL DEFAULT '{}',
                weight REAL NOT NULL DEFAULT 1.0,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_filter_rules_pack
                ON filter_rules(pack_id, enabled, priority);

            CREATE TABLE IF NOT EXISTS p2_score_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER,
                raw_segment_id INTEGER,
                rule_id INTEGER,
                rule_kind TEXT,
                delta REAL NOT NULL,
                running_score REAL NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                tripped INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS p2_review_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                running_score REAL NOT NULL DEFAULT 0,
                trip_raw_segment_id INTEGER,
                window_raw_ids_json TEXT NOT NULL DEFAULT '[]',
                evidence_json TEXT NOT NULL DEFAULT '{}',
                structural_json TEXT NOT NULL DEFAULT '{}',
                question TEXT NOT NULL DEFAULT
                    'Escalate this window to P2 conversational refinement?',
                decision_note TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decided_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS p2_refine_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pass_index INTEGER NOT NULL,
                window_start_raw_id INTEGER,
                window_end_raw_id INTEGER,
                status TEXT NOT NULL DEFAULT 'on',
                mode TEXT NOT NULL DEFAULT 'stub',
                text TEXT NOT NULL DEFAULT '',
                topic_score REAL,
                home_terms_json TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS p2_topic_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL DEFAULT 'on',
                home_text TEXT NOT NULL DEFAULT '',
                home_terms_json TEXT NOT NULL DEFAULT '[]',
                on_streak INTEGER NOT NULL DEFAULT 0,
                off_streak INTEGER NOT NULL DEFAULT 0,
                last_pass_raw_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


def wipe_p2_runtime(db: Any) -> None:
    """Clear runtime P2 rows (not doctor config). Called on Play/Reset."""
    ensure_p2_tables(db)
    with db.get_db() as conn:
        conn.execute("DELETE FROM p2_score_events")
        conn.execute("DELETE FROM p2_review_prompts")
        conn.execute("DELETE FROM p2_refine_passes")
        conn.execute("DELETE FROM p2_topic_state")
        try:
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('p2_score_events','p2_review_prompts','p2_refine_passes','p2_topic_state')"
            )
        except Exception:
            pass
        conn.commit()

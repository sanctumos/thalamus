#!/usr/bin/env python3
"""
Conversation catalog for web replay — selectable NDJSON feeds.

Each entry points at a Cochlea-shaped NDJSON file (same schema as
examples/raw_data_log.json): one JSON object per line with
session_id, log_timestamp, segments[].

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
CONVERSATIONS_DIR = ROOT / "conversations"
CATALOG_PATH = CONVERSATIONS_DIR / "catalog.json"


def _load_catalog() -> Dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_conversations() -> List[Dict[str, Any]]:
    """Return catalog rows with resolved absolute path + exists flag."""
    data = _load_catalog()
    out: List[Dict[str, Any]] = []
    for row in data.get("conversations") or []:
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        rel = str(row.get("file") or "").strip()
        path = (CONVERSATIONS_DIR / rel).resolve() if rel else None
        item = {
            "id": cid,
            "label": row.get("label") or cid,
            "default": bool(row.get("default")),
            "path": str(path) if path else None,
            "exists": bool(path and path.is_file()),
            "omi_conversation_id": row.get("omi_conversation_id"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "title": row.get("title"),
            "notes": row.get("notes"),
        }
        out.append(item)
    return out


def default_conversation_id() -> str:
    for c in list_conversations():
        if c.get("default") and c.get("exists"):
            return c["id"]
    for c in list_conversations():
        if c.get("exists"):
            return c["id"]
    raise FileNotFoundError("no conversation feeds found in catalog")


def resolve_conversation(conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Resolve id (or default) to a catalog row; raises KeyError / FileNotFoundError."""
    wanted = (conversation_id or "").strip() or default_conversation_id()
    for c in list_conversations():
        if c["id"] == wanted:
            if not c["exists"]:
                raise FileNotFoundError(f"conversation file missing: {c.get('path')}")
            return c
    raise KeyError(f"unknown conversation_id: {wanted}")


def conversations_payload(selected_id: Optional[str] = None) -> Dict[str, Any]:
    rows = list_conversations()
    selected = (selected_id or "").strip()
    if not selected:
        try:
            selected = default_conversation_id()
        except FileNotFoundError:
            selected = rows[0]["id"] if rows else ""
    return {
        "conversations": [
            {
                "id": r["id"],
                "label": r["label"],
                "default": r["default"],
                "exists": r["exists"],
                "omi_conversation_id": r.get("omi_conversation_id"),
                "started_at": r.get("started_at"),
                "title": r.get("title"),
            }
            for r in rows
        ],
        "conversation_id": selected,
    }

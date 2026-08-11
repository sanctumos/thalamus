#!/usr/bin/env python3
"""
LLM for refine — Venice first, deterministic stub fallback.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

VENICE_BASE = "https://api.venice.ai/api/v1"
DEFAULT_MODEL = os.environ.get("VENICE_MODEL", "llama-3.3-70b")

# Set by server/orchestrator — secrets live in the demo SQLite DB.
_secrets_db_path: Optional[Path] = None


def set_secrets_db_path(path: Optional[Path]) -> None:
    global _secrets_db_path
    _secrets_db_path = Path(path) if path is not None else None


def load_venice_key() -> Optional[str]:
    """Prefer app_secrets in the demo DB; env only as bootstrap fallback."""
    if _secrets_db_path is not None:
        from .secrets_store import VENICE_KEY_NAME, get_secret

        v = get_secret(_secrets_db_path, VENICE_KEY_NAME)
        if v:
            return v
    for name in ("VENICE_API_KEY", "VENICE_INFERENCE_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


def stub_refine(text: str) -> str:
    cleaned = " ".join(text.split())
    return f"[refined] {cleaned}"


def venice_refine(text: str, api_key: Optional[str] = None) -> str:
    key = api_key or load_venice_key()
    if not key:
        raise RuntimeError("VENICE_API_KEY not set")
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You refine noisy speech-to-text fragments into clear prose. "
                    "Return ONLY the refined text, no JSON, no quotes."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 200,
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
    return (body["choices"][0]["message"]["content"] or "").strip()


def call_text(prompt: str, *, force_stub: bool = False) -> Tuple[str, str]:
    """Return (text, mode) where mode is 'venice' or 'stub'.

    Play/UI owns force_stub — no env override here (env only seeds the web default).
    """
    if force_stub:
        return stub_refine(prompt), "stub"
    try:
        return venice_refine(prompt), "venice"
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError) as e:
        logger.warning("Venice refine failed (%s); using stub", e)
        return stub_refine(prompt), "stub"

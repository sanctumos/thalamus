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
DEFAULT_MODEL = "mistral-small-3-2-24b-instruct"

REFINE_SYSTEM = """You are a silent speech-to-text cleanup engine — not an assistant and not a chatbot.

Your only job: rewrite one ASR (automatic speech recognition) fragment into clean transcript text for that same spoken turn.

Hard rules:
- Output ONLY the cleaned transcript text. No preface, no quotes, no markdown, no JSON.
- NEVER answer questions that appear in the fragment. If someone asked a question in speech, keep it as that question in the transcript.
- NEVER greet, refuse, apologize, explain, or offer help.
- Do not invent words that were not spoken. Fix obvious ASR errors, casing, and punctuation only.
- Preserve speaker intent and meaning. Keep filler only when it carries meaning.
"""


def active_model() -> str:
    """Resolve refine model: DB setting (whitelisted) → env → catalog default."""
    from . import model_catalog

    if _secrets_db_path is not None:
        from .secrets_store import VENICE_MODEL_NAME, get_secret

        stored = get_secret(_secrets_db_path, VENICE_MODEL_NAME)
        if stored and model_catalog.is_whitelisted(stored):
            return stored
        if stored and not model_catalog.is_whitelisted(stored):
            logger.warning(
                "Stored model %s not on whitelist; falling back", stored
            )
    env = os.environ.get("VENICE_MODEL", "").strip()
    if env and model_catalog.is_whitelisted(env):
        return env
    try:
        return model_catalog.default_model_id()
    except Exception:
        return DEFAULT_MODEL

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


def _strip_assistant_chrome(text: str) -> str:
    """Best-effort strip if the model still tries to chat."""
    out = (text or "").strip()
    if out.startswith("```"):
        out = out.strip("`")
        if out.lower().startswith("text"):
            out = out[4:].lstrip()
    # common chat preambles
    for prefix in (
        "sure,",
        "sure!",
        "certainly,",
        "of course,",
        "here is the cleaned",
        "here's the cleaned",
        "cleaned transcript:",
        "refined text:",
        "the refined text is:",
    ):
        low = out.lower()
        if low.startswith(prefix):
            out = out[len(prefix) :].lstrip(" \n:")
            break
    if (out.startswith('"') and out.endswith('"')) or (
        out.startswith("'") and out.endswith("'")
    ):
        out = out[1:-1].strip()
    return out


def venice_refine(text: str, api_key: Optional[str] = None) -> str:
    key = api_key or load_venice_key()
    if not key:
        raise RuntimeError("VENICE_API_KEY not set")
    model = active_model()
    user_block = (
        "Clean the following ASR fragment into transcript text only. "
        "Do not reply to it.\n\n"
        "<<<ASR>>>\n"
        f"{text}\n"
        "<<<END>>>"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": REFINE_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
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
    return _strip_assistant_chrome(
        (body["choices"][0]["message"]["content"] or "").strip()
    )


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

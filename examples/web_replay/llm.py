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


def load_venice_key() -> Optional[str]:
    for name in ("VENICE_API_KEY", "VENICE_INFERENCE_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    pass_path = Path.home() / ".ssh" / "venice.pass"
    if pass_path.exists():
        for line in pass_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, val = line.split("=", 1)
            k, val = k.strip(), val.strip().strip("'").strip('"')
            if k in ("VENICE_API_KEY", "VENICE_INFERENCE_KEY") and val:
                os.environ.setdefault(k, val)
                return val
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
    """Return (text, mode) where mode is 'venice' or 'stub'."""
    if force_stub or os.environ.get("THALAMUS_WEB_FORCE_STUB", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return stub_refine(prompt), "stub"
    try:
        return venice_refine(prompt), "venice"
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError) as e:
        logger.warning("Venice refine failed (%s); using stub", e)
        return stub_refine(prompt), "stub"

#!/usr/bin/env python3
"""
Streaming refine loop — groups raw segments, calls Venice/stub, writes refined + usage.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from . import llm as llm_mod

logger = logging.getLogger(__name__)


def refine_unrefined(db, *, force_stub: bool = False, call_text=None) -> List[Dict[str, Any]]:
    """Process all unrefined raw segments into refined_segments. Returns created rows."""
    call = call_text or llm_mod.call_text
    segments = db.get_unrefined_segments()
    if not segments:
        return []

    # Group consecutive same-speaker segments (simple thalamus-style batch)
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for seg in sorted(segments, key=lambda s: (s["session_id"], s["start_time"], s["id"])):
        if current and (
            current[-1]["session_id"] != seg["session_id"]
            or current[-1]["speaker_id"] != seg["speaker_id"]
        ):
            groups.append(current)
            current = []
        current.append(seg)
    if current:
        groups.append(current)

    created: List[Dict[str, Any]] = []
    for group in groups:
        session_id = group[0]["session_id"]
        speaker_name = group[0]["speaker_name"]
        speaker_id = group[0]["speaker_id"]
        refined_speaker_id = db.get_or_create_speaker(speaker_id, speaker_name)
        combined = " ".join(s["text"] for s in group)
        refined_text, mode = call(combined, force_stub=force_stub)
        start_time = min(s["start_time"] for s in group)
        end_time = max(s["end_time"] for s in group)
        source_ids = [s["id"] for s in group]
        rid = db.insert_refined_segment(
            session_id=session_id,
            refined_speaker_id=refined_speaker_id,
            text=refined_text,
            start_time=start_time,
            end_time=end_time,
            source_segments=json.dumps(source_ids),
        )
        created.append(
            {
                "id": rid,
                "session_id": session_id,
                "text": refined_text,
                "speaker_name": speaker_name,
                "source_segments": source_ids,
                "mode": mode,
            }
        )
        logger.info("refined group -> id=%s mode=%s", rid, mode)
    return created

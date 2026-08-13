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


def refine_unrefined(
    db,
    *,
    force_stub: bool = False,
    call_text=None,
    should_stop: Optional[Callable[[], bool]] = None,
    max_groups: Optional[int] = None,
    lock: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Process unrefined raw segments into refined_segments. Returns created rows.

    should_stop: checked between groups so Stop can halt mid-backlog.
    max_groups: optional cap (orchestrator uses 1 so Venice can't block Stop for long).
    lock: optional threading lock — held only around DB reads/writes, never around LLM.
    """
    call = call_text or llm_mod.call_text

    def _db(fn):
        if lock is None:
            return fn()
        with lock:
            return fn()

    segments = _db(lambda: db.get_unrefined_segments())
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
        if should_stop is not None and should_stop():
            break
        if max_groups is not None and len(created) >= max_groups:
            break
        session_id = group[0]["session_id"]
        speaker_name = group[0]["speaker_name"]
        speaker_id = group[0]["speaker_id"]
        combined = " ".join(s["text"] for s in group)
        # LLM outside any DB lock so ingest/Stop stay responsive
        refined_text, mode = call(combined, force_stub=force_stub)
        if should_stop is not None and should_stop():
            break
        start_time = min(s["start_time"] for s in group)
        end_time = max(s["end_time"] for s in group)
        source_ids = [s["id"] for s in group]

        def _write():
            refined_speaker_id = db.get_or_create_speaker(speaker_id, speaker_name)
            return db.insert_refined_segment(
                session_id=session_id,
                refined_speaker_id=refined_speaker_id,
                text=refined_text,
                start_time=start_time,
                end_time=end_time,
                source_segments=json.dumps(source_ids),
            )

        rid = _db(_write)
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

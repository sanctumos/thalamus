#!/usr/bin/env python3
"""
NDJSON streamer for raw_data_log.json — releases only via TimeSimulator.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from .time_simulator import TimeSimulator

DEFAULT_LOG = Path(__file__).resolve().parents[1] / "raw_data_log.json"


def iter_events(path: Optional[Path] = None) -> Iterator[Dict[str, Any]]:
    data_path = Path(path or DEFAULT_LOG)
    with data_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def stream_events(
    simulator: TimeSimulator,
    path: Optional[Path] = None,
    on_wait: Optional[Any] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield events only after the time simulator releases each one."""
    for event in iter_events(path):
        waited = simulator.wait_before(event["log_timestamp"])
        if on_wait is not None and waited > 0:
            on_wait(waited, event["log_timestamp"])
        yield event

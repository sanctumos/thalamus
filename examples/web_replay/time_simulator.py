#!/usr/bin/env python3
"""
Time simulator — same inter-event gating as thalamus_app.main().

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional


def parse_log_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TimeSimulator:
    """Gate stream releases on log_timestamp deltas (original Omi demo behavior).

    Production Play uses speed=1.0 (real waits). Tests inject sleep_fn / speed.
    """

    def __init__(
        self,
        speed: float = 1.0,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self.speed = float(speed)
        self._sleep = sleep_fn if sleep_fn is not None else __import__("time").sleep
        self._last: Optional[datetime] = None
        self.waits: list[float] = []

    def reset(self) -> None:
        self._last = None
        self.waits.clear()

    def wait_before(self, log_timestamp: str | datetime) -> float:
        """Sleep for delta since previous event; return seconds slept (wall intent)."""
        current = (
            log_timestamp
            if isinstance(log_timestamp, datetime)
            else parse_log_timestamp(log_timestamp)
        )
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        waited = 0.0
        if self._last is not None:
            delta = (current - self._last).total_seconds()
            if delta > 0:
                waited = delta / self.speed
                self._sleep(waited)
                self.waits.append(waited)
        self._last = current
        return waited

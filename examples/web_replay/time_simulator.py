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

import time
from datetime import datetime, timezone
from typing import Callable, Optional


def parse_log_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TimeSimulator:
    """Gate stream releases on log_timestamp deltas (original Omi demo behavior).

    Production Play uses speed=1.0 (real waits). Tests inject sleep_fn / speed.
    Optional stop_event makes long waits interruptible (Stop button).
    """

    def __init__(
        self,
        speed: float = 1.0,
        sleep_fn: Optional[Callable[[float], None]] = None,
        stop_event: Optional[object] = None,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self.speed = float(speed)
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._stop_event = stop_event
        self._last: Optional[datetime] = None
        self.waits: list[float] = []
        self.interrupted = False

    def reset(self) -> None:
        self._last = None
        self.waits.clear()
        self.interrupted = False

    def _interruptible_sleep(self, seconds: float) -> float:
        """Sleep up to seconds; return actual slept. Honors stop_event in ~0.1s slices."""
        if seconds <= 0:
            return 0.0
        if self._stop_event is None:
            self._sleep(seconds)
            return seconds
        remaining = float(seconds)
        slept = 0.0
        while remaining > 0:
            if getattr(self._stop_event, "is_set", lambda: False)():
                self.interrupted = True
                break
            chunk = min(0.1, remaining)
            # Event.wait returns True if set; still sleep via wait when available
            wait = getattr(self._stop_event, "wait", None)
            if wait is not None:
                if wait(chunk):
                    self.interrupted = True
                    slept += chunk  # approximate; stop mid-chunk
                    break
            else:
                self._sleep(chunk)
            slept += chunk
            remaining -= chunk
        return slept

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
                target = delta / self.speed
                waited = self._interruptible_sleep(target)
                self.waits.append(waited)
        self._last = current
        return waited

#!/usr/bin/env python3
"""
Play orchestrator — time-sim stream → ingest → refine → event callbacks.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .db_util import ingest_event, open_db, reset_db, snapshot
from .refine import refine_unrefined
from .streamer import stream_events
from .time_simulator import TimeSimulator

logger = logging.getLogger(__name__)

EventHandler = Callable[[Dict[str, Any]], None]


class Orchestrator:
    def __init__(
        self,
        db_path: Path,
        data_log: Optional[Path] = None,
        speed: float = 1.0,
        force_stub: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.data_log = data_log
        self.speed = speed
        self.force_stub = force_stub
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._handlers: List[EventHandler] = []
        self._lock = threading.Lock()
        self.state = "idle"
        self.llm_mode = "unknown"
        self.db = None

    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def _emit(self, event: Dict[str, Any]) -> None:
        for h in list(self._handlers):
            try:
                h(event)
            except Exception:
                logger.exception("event handler failed")

    def ensure_db(self):
        """Attach existing demo DB without wiping (reload / stop / status)."""
        if self.db is None:
            self.db = open_db(self.db_path)
        return self.db

    def status(self) -> Dict[str, Any]:
        self.ensure_db()
        snap = snapshot(self.db) if self.db else {
            "raw_segments": [],
            "refined_segments": [],
            "segment_usage": [],
        }
        return {
            "state": self.state,
            "llm_mode": self.llm_mode,
            "force_stub": self.force_stub,
            "speed": self.speed,
            "counts": {
                "raw": len(snap["raw_segments"]),
                "refined": len(snap["refined_segments"]),
                "usage": len(snap["segment_usage"]),
            },
            "snapshot": snap,
        }

    def reset(self) -> Dict[str, Any]:
        self.stop()
        self.db = reset_db(self.db_path)
        self.state = "idle"
        self.llm_mode = "unknown"
        self._emit({"type": "console", "level": "INFO", "message": "DB reset"})
        self._emit({"type": "snapshot", **snapshot(self.db)})
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._stop.clear()
        # Keep DB rows; emit snapshot so UIs can hydrate after stop/reload
        if self.db is not None:
            self._emit({"type": "snapshot", **snapshot(self.db)})

    def play(self) -> Dict[str, Any]:
        with self._lock:
            if self.state == "playing":
                return self.status()
            self.stop()
            self.db = reset_db(self.db_path)
            self.state = "playing"
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        self._emit({"type": "console", "level": "INFO", "message": f"Play start speed={self.speed}"})
        return self.status()

    def _run(self) -> None:
        assert self.db is not None
        sim = TimeSimulator(speed=self.speed)

        def on_wait(waited: float, ts: str) -> None:
            self._emit(
                {
                    "type": "console",
                    "level": "INFO",
                    "message": f"time-sim wait {waited:.2f}s before {ts}",
                }
            )

        try:
            for event in stream_events(sim, path=self.data_log, on_wait=on_wait):
                if self._stop.is_set():
                    self.state = "stopped"
                    self._emit({"type": "console", "level": "WARN", "message": "Play stopped"})
                    return
                raw_ids = ingest_event(self.db, event)
                for rid in raw_ids:
                    row = next(
                        (
                            r
                            for r in snapshot(self.db)["raw_segments"]
                            if r["id"] == rid
                        ),
                        None,
                    )
                    if row:
                        self._emit({"type": "raw", "row": row})
                created = refine_unrefined(self.db, force_stub=self.force_stub)
                for c in created:
                    self.llm_mode = c.get("mode", self.llm_mode)
                    self._emit({"type": "refined", "row": c})
                    self._emit(
                        {
                            "type": "console",
                            "level": "INFO",
                            "message": f"refine mode={c.get('mode')} id={c.get('id')}",
                        }
                    )
                for u in snapshot(self.db)["segment_usage"]:
                    if u["refined_segment_id"] in {c["id"] for c in created}:
                        self._emit({"type": "provenance", "row": u})
            self.state = "done"
            self._emit({"type": "console", "level": "INFO", "message": "Play complete"})
            self._emit({"type": "snapshot", **snapshot(self.db)})
        except Exception as e:
            self.state = "error"
            logger.exception("play failed")
            self._emit({"type": "console", "level": "ERROR", "message": str(e)})

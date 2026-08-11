#!/usr/bin/env python3
"""
Play orchestrator — time-sim ingest and refine run on separate threads.

Intake is never blocked on Venice/stub latency; refine may lag.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import logging
import threading
import time
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
        self._ingest_thread: Optional[threading.Thread] = None
        self._refine_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ingest_done = threading.Event()
        self._handlers: List[EventHandler] = []
        self._lock = threading.Lock()
        self._db_write_lock = threading.Lock()
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
            "ingest_done": self._ingest_done.is_set(),
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
        self._ingest_done.clear()
        self._emit({"type": "console", "level": "INFO", "message": "DB reset"})
        self._emit({"type": "snapshot", **snapshot(self.db)})
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        for t in (self._ingest_thread, self._refine_thread):
            if t and t.is_alive():
                t.join(timeout=8)
        self._ingest_thread = None
        self._refine_thread = None
        self._stop.clear()
        if self.db is not None:
            self._emit({"type": "snapshot", **snapshot(self.db)})

    def play(self) -> Dict[str, Any]:
        with self._lock:
            if self.state == "playing":
                return self.status()
            self.stop()
            self.db = reset_db(self.db_path)
            self.state = "playing"
            self._ingest_done.clear()
            self._stop.clear()
            self._ingest_thread = threading.Thread(
                target=self._run_ingest, daemon=True, name="web-replay-ingest"
            )
            self._refine_thread = threading.Thread(
                target=self._run_refine, daemon=True, name="web-replay-refine"
            )
            self._ingest_thread.start()
            self._refine_thread.start()
        self._emit(
            {
                "type": "console",
                "level": "INFO",
                "message": (
                    f"Play start speed={self.speed} "
                    "(ingest∥refine — intake not blocked on LLM)"
                ),
            }
        )
        return self.status()

    def _run_ingest(self) -> None:
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
                    self._emit(
                        {"type": "console", "level": "WARN", "message": "Play stopped"}
                    )
                    return
                with self._db_write_lock:
                    raw_ids = ingest_event(self.db, event)
                    snap_raw = snapshot(self.db)["raw_segments"]
                for rid in raw_ids:
                    row = next((r for r in snap_raw if r["id"] == rid), None)
                    if row:
                        self._emit({"type": "raw", "row": row})
            if not self._stop.is_set():
                self._emit(
                    {
                        "type": "console",
                        "level": "INFO",
                        "message": "Intake complete — refine may still be catching up",
                    }
                )
        except Exception as e:
            self.state = "error"
            logger.exception("ingest failed")
            self._emit({"type": "console", "level": "ERROR", "message": str(e)})
        finally:
            self._ingest_done.set()

    def _emit_refine_results(self, created: List[Dict[str, Any]]) -> None:
        if not created:
            return
        with self._db_write_lock:
            usage = snapshot(self.db)["segment_usage"]
        created_ids = {c["id"] for c in created}
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
        for u in usage:
            if u["refined_segment_id"] in created_ids:
                self._emit({"type": "provenance", "row": u})

    def _run_refine(self) -> None:
        assert self.db is not None
        try:
            while not self._stop.is_set():
                with self._db_write_lock:
                    created = refine_unrefined(self.db, force_stub=self.force_stub)
                self._emit_refine_results(created)
                if created:
                    continue  # drain backlog without sleeping
                if self._ingest_done.is_set():
                    # one more pass in case last ingest raced the empty poll
                    with self._db_write_lock:
                        created = refine_unrefined(self.db, force_stub=self.force_stub)
                    self._emit_refine_results(created)
                    if not created:
                        break
                    continue
                # Idle briefly while intake is still running
                self._stop.wait(0.05)
            if self._stop.is_set():
                if self.state != "error":
                    self.state = "stopped"
                return
            if self.state != "error":
                self.state = "done"
                self._emit(
                    {"type": "console", "level": "INFO", "message": "Play complete"}
                )
                with self._db_write_lock:
                    snap = snapshot(self.db)
                self._emit({"type": "snapshot", **snap})
        except Exception as e:
            self.state = "error"
            logger.exception("refine failed")
            self._emit({"type": "console", "level": "ERROR", "message": str(e)})

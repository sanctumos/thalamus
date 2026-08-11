#!/usr/bin/env python3
"""
Flask web replay server — open during dev. SSE for live pane events.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, Response, jsonify, request, send_from_directory

from .orchestrator import Orchestrator
from .llm import load_venice_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("THALAMUS_WEB_DATA", str(ROOT / "data")))
DB_PATH = Path(os.environ.get("THALAMUS_WEB_DB", str(DATA_DIR / "web_replay.db")))
DATA_LOG = Path(
    os.environ.get(
        "THALAMUS_WEB_DATA_LOG",
        str(ROOT.parent / "raw_data_log.json"),
    )
)

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")

_subscribers: List[queue.Queue] = []
_sub_lock = threading.Lock()

orch = Orchestrator(
    db_path=DB_PATH,
    data_log=DATA_LOG,
    speed=float(os.environ.get("THALAMUS_WEB_SPEED", "1.0")),
    force_stub=os.environ.get("THALAMUS_WEB_FORCE_STUB", "1").strip().lower()
    in ("1", "true", "yes", ""),
)


def _broadcast(event: Dict[str, Any]) -> None:
    payload = json.dumps(event, default=str)
    with _sub_lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


orch.on_event(_broadcast)


def create_app(
    db_path: Path | None = None,
    data_log: Path | None = None,
    speed: float = 1000.0,
    force_stub: bool = True,
) -> Flask:
    """Factory for tests."""
    global orch, DB_PATH, DATA_LOG
    if db_path is not None:
        DB_PATH = Path(db_path)
    if data_log is not None:
        DATA_LOG = Path(data_log)
    orch = Orchestrator(
        db_path=DB_PATH, data_log=DATA_LOG, speed=speed, force_stub=force_stub
    )
    orch.on_event(_broadcast)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    orch.reset()
    return app


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "state": orch.state,
            "llm_mode": orch.llm_mode,
            "force_stub": orch.force_stub,
            "venice_key_present": bool(load_venice_key()),
        }
    )


@app.get("/api/status")
def status():
    payload = orch.status()
    payload["venice_key_present"] = bool(load_venice_key())
    return jsonify(payload)


@app.get("/api/controls")
def controls():
    """Defaults the web control surface should show."""
    return jsonify(
        {
            "speed": orch.speed,
            "force_stub": orch.force_stub,
            "venice_key_present": bool(load_venice_key()),
            "llm_mode": orch.llm_mode,
            "state": orch.state,
        }
    )


@app.post("/api/reset")
def reset():
    return jsonify(orch.reset())


@app.post("/api/play")
def play():
    body = request.get_json(silent=True) or {}
    if "speed" in body and body["speed"] is not None:
        orch.speed = float(body["speed"])
    if "force_stub" in body and body["force_stub"] is not None:
        orch.force_stub = bool(body["force_stub"])
    return jsonify(orch.play())


@app.post("/api/stop")
def stop():
    orch.stop()
    orch.state = "stopped"
    return jsonify(orch.status())


@app.get("/api/events")
def events_sse():
    q: queue.Queue = queue.Queue(maxsize=500)
    with _sub_lock:
        _subscribers.append(q)

    def gen():
        try:
            # initial status
            yield f"data: {json.dumps({'type': 'status', **orch.status()}, default=str)}\n\n"
            while True:
                try:
                    payload = q.get(timeout=25)
                    yield f"data: {payload}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sub_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    orch.reset()
    host = os.environ.get("THALAMUS_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("THALAMUS_WEB_PORT", "8787"))
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()

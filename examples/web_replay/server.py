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

from . import llm as llm_mod
from .conversations import (
    conversations_payload,
    resolve_conversation,
)
from .llm import active_model, load_venice_key, set_secrets_db_path
from .model_catalog import is_whitelisted, settings_models_payload
from .orchestrator import Orchestrator
from .secrets_store import (
    VENICE_KEY_NAME,
    VENICE_MODEL_NAME,
    secret_hint,
    secret_present,
    set_secret,
)
from .p2_filters import (
    decide_review,
    evaluate_review,
    get_filter_pack,
    get_review,
    get_settings as p2_get_settings,
    get_topic_state,
    list_filter_packs,
    list_filter_rules,
    list_refine_passes,
    list_reviews,
    patch_filter_pack,
    patch_filter_rule,
    patch_settings as p2_patch_settings,
    seed_default_pack,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("THALAMUS_WEB_DATA", str(ROOT / "data")))
DB_PATH = Path(os.environ.get("THALAMUS_WEB_DB", str(DATA_DIR / "web_replay.db")))


def _boot_conversation():
    env_log = os.environ.get("THALAMUS_WEB_DATA_LOG", "").strip()
    env_cid = os.environ.get("THALAMUS_WEB_CONVERSATION", "").strip()
    if env_log:
        path = Path(env_log)
        cid = env_cid or path.stem
        return cid, path
    try:
        row = resolve_conversation(env_cid or None)
        return row["id"], Path(row["path"])
    except (KeyError, FileNotFoundError):
        fallback = ROOT.parent / "raw_data_log.json"
        return "cochlea-10min-committee", fallback


_BOOT_CID, DATA_LOG = _boot_conversation()

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")

_subscribers: List[queue.Queue] = []
_sub_lock = threading.Lock()

set_secrets_db_path(DB_PATH)

orch = Orchestrator(
    db_path=DB_PATH,
    data_log=DATA_LOG,
    conversation_id=_BOOT_CID,
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


def _settings_payload() -> Dict[str, Any]:
    selected = active_model()
    payload = {
        "venice_api_key_set": secret_present(DB_PATH, VENICE_KEY_NAME),
        "venice_api_key_hint": secret_hint(DB_PATH, VENICE_KEY_NAME),
        "venice_key_present": bool(load_venice_key()),
    }
    payload.update(settings_models_payload(selected))
    payload.update(conversations_payload(orch.conversation_id))
    return payload


def create_app(
    db_path: Path | None = None,
    data_log: Path | None = None,
    speed: float = 1000.0,
    force_stub: bool = True,
    conversation_id: str | None = None,
) -> Flask:
    """Factory for tests."""
    global orch, DB_PATH, DATA_LOG
    if db_path is not None:
        DB_PATH = Path(db_path)
    if data_log is not None:
        DATA_LOG = Path(data_log)
        cid = conversation_id or Path(data_log).stem
    elif conversation_id:
        row = resolve_conversation(conversation_id)
        DATA_LOG = Path(row["path"])
        cid = row["id"]
    else:
        cid = conversation_id or _BOOT_CID
    set_secrets_db_path(DB_PATH)
    orch = Orchestrator(
        db_path=DB_PATH,
        data_log=DATA_LOG,
        conversation_id=cid,
        speed=speed,
        force_stub=force_stub,
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
            **_settings_payload(),
        }
    )


@app.get("/api/status")
def status():
    payload = orch.status()
    payload.update(_settings_payload())
    return jsonify(payload)


@app.get("/api/controls")
def controls():
    """Defaults the web control surface should show."""
    return jsonify(
        {
            # Speed is a UI Play param — always advertise 1.0 so hydrate never
            # inherits a leftover orch.speed from a prior smoke/test run.
            "speed": 1.0,
            "force_stub": orch.force_stub,
            "llm_mode": orch.llm_mode,
            "state": orch.state,
            **_settings_payload(),
        }
    )


@app.get("/api/conversations")
def get_conversations():
    return jsonify(conversations_payload(orch.conversation_id))


@app.get("/api/settings")
def get_settings():
    return jsonify(_settings_payload())


@app.post("/api/settings")
def post_settings():
    """Save secrets/settings into app_secrets (survives Play/Reset). Never echo raw key."""
    body = request.get_json(silent=True) or {}
    if "venice_api_key" in body:
        raw = body.get("venice_api_key")
        if raw is None:
            raw = ""
        set_secret(DB_PATH, VENICE_KEY_NAME, str(raw))
        logger.info(
            "Venice API key %s in app_secrets",
            "updated" if str(raw).strip() else "cleared",
        )
    if "venice_model" in body and body.get("venice_model") is not None:
        mid = str(body.get("venice_model") or "").strip()
        if not mid:
            set_secret(DB_PATH, VENICE_MODEL_NAME, "")
            logger.info("Venice model cleared (will use catalog default)")
        elif not is_whitelisted(mid):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"model not whitelisted (lab pass < threshold): {mid}",
                        **_settings_payload(),
                    }
                ),
                400,
            )
        else:
            set_secret(DB_PATH, VENICE_MODEL_NAME, mid)
            logger.info("Venice refine model set to %s", mid)
    return jsonify(_settings_payload())


@app.post("/api/reset")
def reset():
    return jsonify(orch.reset())


@app.post("/api/play")
def play():
    body = request.get_json(silent=True) or {}
    if "speed" in body and body["speed"] is not None:
        try:
            speed = float(body["speed"])
        except (TypeError, ValueError):
            speed = 1.0
        # UI default is 1.0; reject nonsense / leftover test values
        if speed <= 0 or speed > 1000:
            speed = 1.0
        orch.speed = speed
    if "force_stub" in body and body["force_stub"] is not None:
        orch.force_stub = bool(body["force_stub"])
    if "conversation_id" in body and body.get("conversation_id") is not None:
        cid = str(body.get("conversation_id") or "").strip()
        if cid:
            try:
                row = resolve_conversation(cid)
            except KeyError as e:
                return jsonify({"ok": False, "error": str(e), **orch.status()}), 400
            except FileNotFoundError as e:
                return jsonify({"ok": False, "error": str(e), **orch.status()}), 400
            orch.set_conversation(row["id"], Path(row["path"]))
            global DATA_LOG
            DATA_LOG = Path(row["path"])
    return jsonify(orch.play())


@app.post("/api/stop")
def stop():
    orch.stop()
    if orch.state not in ("done", "error", "idle"):
        orch.state = "stopped"
    return jsonify(orch.status())


def _doctor_db():
    return orch.ensure_db()


@app.get("/api/doctor/settings")
def doctor_get_settings():
    db = _doctor_db()
    return jsonify({"ok": True, "settings": p2_get_settings(db)})


@app.patch("/api/doctor/settings")
def doctor_patch_settings():
    db = _doctor_db()
    body = request.get_json(silent=True) or {}
    settings = p2_patch_settings(db, body)
    return jsonify({"ok": True, "settings": settings})


@app.get("/api/doctor/filter-packs")
def doctor_list_packs():
    db = _doctor_db()
    packs = list_filter_packs(db)
    out = []
    for p in packs:
        rules = list_filter_rules(db, int(p["id"]))
        out.append({**p, "rules": rules})
    return jsonify({"ok": True, "packs": out})


@app.get("/api/doctor/filter-packs/<int:pack_id>")
def doctor_get_pack(pack_id: int):
    db = _doctor_db()
    pack = get_filter_pack(db, pack_id=pack_id)
    if not pack:
        return jsonify({"ok": False, "error": "pack not found"}), 404
    pack = {**pack, "rules": list_filter_rules(db, pack_id)}
    return jsonify({"ok": True, "pack": pack})


@app.patch("/api/doctor/filter-packs/<int:pack_id>")
def doctor_patch_pack(pack_id: int):
    db = _doctor_db()
    body = request.get_json(silent=True) or {}
    pack = patch_filter_pack(db, pack_id, body)
    if not pack:
        return jsonify({"ok": False, "error": "pack not found"}), 404
    pack = {**pack, "rules": list_filter_rules(db, pack_id)}
    return jsonify({"ok": True, "pack": pack})


@app.patch("/api/doctor/filter-rules/<int:rule_id>")
def doctor_patch_rule(rule_id: int):
    db = _doctor_db()
    body = request.get_json(silent=True) or {}
    rule = patch_filter_rule(db, rule_id, body)
    if not rule:
        return jsonify({"ok": False, "error": "rule not found"}), 404
    return jsonify({"ok": True, "rule": rule})


@app.post("/api/doctor/seed")
def doctor_seed():
    db = _doctor_db()
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force_rules"))
    result = seed_default_pack(db, force_rules=force)
    return jsonify({"ok": True, **result, "settings": p2_get_settings(db)})


@app.get("/api/doctor/reviews")
def doctor_list_reviews():
    db = _doctor_db()
    status = request.args.get("status")
    return jsonify({"ok": True, "reviews": list_reviews(db, status=status)})


@app.get("/api/doctor/reviews/<int:review_id>")
def doctor_get_review(review_id: int):
    db = _doctor_db()
    rev = get_review(db, review_id)
    if not rev:
        return jsonify({"ok": False, "error": "review not found"}), 404
    return jsonify({"ok": True, "review": rev})


@app.get("/api/doctor/refine-passes")
def doctor_list_refine_passes():
    db = _doctor_db()
    return jsonify({"ok": True, "passes": list_refine_passes(db)})


@app.get("/api/doctor/topic-state")
def doctor_topic_state():
    db = _doctor_db()
    return jsonify({"ok": True, "topic_state": get_topic_state(db)})


@app.post("/api/doctor/reviews/<int:review_id>/evaluate")
def doctor_evaluate_review(review_id: int):
    """Run internal Thalamus evaluator (not HITL)."""
    db = _doctor_db()
    try:
        rev = evaluate_review(db, review_id)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    escalate = bool(
        rev.get("escalate")
        if "escalate" in rev
        else rev.get("status") == "escalated"
    )
    if orch.p2_scorer is not None and rev.get("status") in (
        "escalated",
        "declined",
    ):
        orch.p2_scorer.on_review_decided(escalate)
    orch._emit(
        {
            "type": "p2_review",
            "review": rev,
            "decided": True,
            "escalate": escalate,
        }
    )
    return jsonify({"ok": True, "review": rev})


@app.post("/api/doctor/reviews/<int:review_id>/decide")
def doctor_decide_review(review_id: int):
    """Doctor override — normal path is /evaluate (auto). Kept for tooling."""
    db = _doctor_db()
    body = request.get_json(silent=True) or {}
    if "escalate" not in body:
        return jsonify({"ok": False, "error": "escalate bool required"}), 400
    escalate = bool(body.get("escalate"))
    note = str(body.get("note") or "doctor override")
    if not note.startswith("["):
        note = f"[doctor_override] {note}"
    rev = decide_review(db, review_id, escalate=escalate, note=note)
    if not rev:
        return jsonify({"ok": False, "error": "review not found"}), 404
    if orch.p2_scorer is not None:
        orch.p2_scorer.on_review_decided(escalate)
    orch._emit(
        {
            "type": "console",
            "level": "INFO",
            "message": (
                f"P2 review #{review_id} "
                f"{'escalated' if escalate else 'declined'} (override)"
                + (f" — {note}" if note else "")
            ),
        }
    )
    orch._emit(
        {
            "type": "p2_review",
            "review": rev,
            "decided": True,
            "escalate": escalate,
        }
    )
    return jsonify({"ok": True, "review": rev})


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
    set_secrets_db_path(DB_PATH)
    # Do not wipe on boot — reload should show progress-so-far until Reset/Play
    orch.ensure_db()
    host = os.environ.get("THALAMUS_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("THALAMUS_WEB_PORT", "8787"))
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()

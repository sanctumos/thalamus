#!/usr/bin/env python3
"""Integration — DB ingest, Play/Reset, HTTP/SSE routes."""

from __future__ import annotations

import io
import json
import queue
import time
import urllib.error

import pytest

from web_replay.db_util import ingest_event, reset_db, snapshot
from web_replay import llm as llm_mod
from web_replay.llm import call_text, stub_refine, load_venice_key, venice_refine
from web_replay.orchestrator import Orchestrator
from web_replay.refine import refine_unrefined
from web_replay import server as server_mod
from web_replay.server import create_app


@pytest.fixture
def mini_log(tmp_path):
    p = tmp_path / "mini.json"
    lines = []
    for i, (ts, text) in enumerate(
        [
            ("2025-03-26T22:48:00.000000Z", "Hello there"),
            ("2025-03-26T22:48:00.500000Z", "Testing connection"),
        ]
    ):
        lines.append(
            json.dumps(
                {
                    "session_id": "test-session",
                    "log_timestamp": ts,
                    "segments": [
                        {
                            "text": text,
                            "speaker": "SPEAKER_0",
                            "speaker_id": 0,
                            "start": float(i),
                            "end": float(i) + 0.5,
                        }
                    ],
                }
            )
        )
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_ingest_and_snapshot(tmp_path, mini_log):
    db = reset_db(tmp_path / "t.db")
    event = json.loads(mini_log.read_text().splitlines()[0])
    ids = ingest_event(db, event)
    assert len(ids) == 1
    snap = snapshot(db)
    assert snap["raw_segments"][0]["text"] == "Hello there"


def test_refine_stub(tmp_path, mini_log):
    db = reset_db(tmp_path / "t.db")
    for line in mini_log.read_text().splitlines():
        ingest_event(db, json.loads(line))
    created = refine_unrefined(db, force_stub=True)
    assert created[0]["mode"] == "stub"
    assert created[0]["text"].startswith("[refined]")
    assert snapshot(db)["segment_usage"]


def test_stub_refine_helper():
    assert stub_refine("  hi   there ") == "[refined] hi there"


def test_call_text_force_stub():
    text, mode = call_text("hello world", force_stub=True)
    assert mode == "stub"
    assert text.startswith("[refined]")


def test_call_text_env_no_longer_overrides(monkeypatch):
    """Env FORCE_STUB must not override an explicit force_stub=False from the UI."""
    monkeypatch.setenv("THALAMUS_WEB_FORCE_STUB", "1")
    monkeypatch.setenv("VENICE_API_KEY", "k")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "from-venice"}}]}
            ).encode()

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", lambda *a, **k: Resp())
    text, mode = call_text("hello", force_stub=False)
    assert mode == "venice"
    assert text == "from-venice"


def test_load_venice_key_from_env(monkeypatch):
    monkeypatch.setenv("VENICE_API_KEY", "env-key")
    assert load_venice_key() == "env-key"


def test_load_venice_key_from_db(tmp_path, monkeypatch):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    db_path = tmp_path / "sec.db"
    from web_replay.secrets_store import VENICE_KEY_NAME, set_secret
    from web_replay.llm import set_secrets_db_path

    set_secret(db_path, VENICE_KEY_NAME, "db-stored-key")
    set_secrets_db_path(db_path)
    assert load_venice_key() == "db-stored-key"


def test_secrets_survive_reset(tmp_path, mini_log):
    from web_replay.secrets_store import VENICE_KEY_NAME, get_secret, set_secret

    db_path = tmp_path / "survive.db"
    set_secret(db_path, VENICE_KEY_NAME, "keep-me-secret")
    orch = Orchestrator(
        db_path=db_path, data_log=mini_log, speed=1000.0, force_stub=True
    )
    orch.play()
    deadline = time.time() + 10
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    orch.reset()
    assert get_secret(db_path, VENICE_KEY_NAME) == "keep-me-secret"
    assert orch.status()["counts"]["raw"] == 0


def test_settings_api_masks_key(tmp_path, mini_log):
    app = create_app(
        db_path=tmp_path / "set.db",
        data_log=mini_log,
        speed=1000.0,
        force_stub=True,
    )
    app.config["TESTING"] = True
    client = app.test_client()
    r = client.post(
        "/api/settings",
        json={"venice_api_key": "super-secret-token-abcd"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["venice_api_key_set"] is True
    assert body["venice_api_key_hint"].startswith("••••")
    assert "super-secret" not in json.dumps(body)
    g = client.get("/api/settings").get_json()
    assert g["venice_api_key_hint"].endswith("abcd")


def test_load_venice_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    from web_replay.llm import set_secrets_db_path

    set_secrets_db_path(tmp_path / "empty-missing.db")
    assert load_venice_key() is None


def test_venice_refine_success(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": " clean text "}}]}
            ).encode()

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert venice_refine("noisy", api_key="k") == "clean text"


def test_strip_assistant_chrome():
    from web_replay.llm import _strip_assistant_chrome

    assert _strip_assistant_chrome('Sure! "Hello there"') == "Hello there"
    assert _strip_assistant_chrome("Hello?") == "Hello?"


def test_venice_refine_no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    from web_replay.llm import set_secrets_db_path

    set_secrets_db_path(tmp_path / "empty-nokey.db")
    with pytest.raises(RuntimeError):
        venice_refine("x")


def test_call_text_venice_then_stub_on_http_error(monkeypatch):
    monkeypatch.delenv("THALAMUS_WEB_FORCE_STUB", raising=False)
    monkeypatch.setenv("VENICE_API_KEY", "k")

    def boom(*a, **k):
        raise urllib.error.HTTPError(
            "https://api.venice.ai/x", 500, "err", hdrs=None, fp=io.BytesIO(b"")
        )

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
    text, mode = call_text("hello", force_stub=False)
    assert mode == "stub"
    assert text.startswith("[refined]")


def test_refine_empty_and_split_speakers(tmp_path, mini_log):
    db = reset_db(tmp_path / "split.db")
    assert refine_unrefined(db, force_stub=True) == []
    event = {
        "session_id": "s1",
        "log_timestamp": "2025-03-26T22:48:00.000000Z",
        "segments": [
            {
                "text": "A",
                "speaker": "SPEAKER_0",
                "speaker_id": 0,
                "start": 0.0,
                "end": 0.5,
            },
            {
                "text": "B",
                "speaker": "SPEAKER_1",
                "speaker_id": 1,
                "start": 0.5,
                "end": 1.0,
            },
        ],
    }
    ingest_event(db, event)
    created = refine_unrefined(db, force_stub=True)
    assert len(created) == 2


def test_orchestrator_handler_exception_and_double_play(tmp_path, mini_log):
    orch = Orchestrator(
        db_path=tmp_path / "dbl.db", data_log=mini_log, speed=1000.0, force_stub=True
    )

    def bad(_e):
        raise RuntimeError("boom")

    orch.on_event(bad)
    orch.play()
    st = orch.play()
    assert st["state"] == "playing"
    deadline = time.time() + 10
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    orch.stop()


def test_orchestrator_error_path(tmp_path):
    missing = tmp_path / "nope.json"
    orch = Orchestrator(
        db_path=tmp_path / "err.db", data_log=missing, speed=1000.0, force_stub=True
    )
    events = []
    orch.on_event(events.append)
    orch.play()
    deadline = time.time() + 5
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    assert orch.state == "error"
    assert any(e.get("level") == "ERROR" for e in events)


def test_orchestrator_play_sped(tmp_path, mini_log):
    events = []
    orch = Orchestrator(
        db_path=tmp_path / "play.db", data_log=mini_log, speed=1000.0, force_stub=True
    )
    orch.on_event(events.append)
    orch.play()
    deadline = time.time() + 10
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    assert orch.state == "done"
    types = {e.get("type") for e in events}
    assert {"raw", "refined", "console"} <= types


def test_intake_not_blocked_by_slow_refine(tmp_path, mini_log, monkeypatch):
    """Raw events must advance on time-sim even when refine is deliberately slow."""
    import web_replay.llm as llm_mod

    def slow_call(prompt, *, force_stub=False):
        time.sleep(0.35)
        return llm_mod.stub_refine(prompt), "stub"

    monkeypatch.setattr(llm_mod, "call_text", slow_call)

    raw_times: list[float] = []
    refined_times: list[float] = []

    orch = Orchestrator(
        db_path=tmp_path / "uncoupled.db",
        data_log=mini_log,
        speed=1000.0,
        force_stub=True,
    )
    orch.on_event(
        lambda e: (
            raw_times.append(time.time())
            if e.get("type") == "raw"
            else refined_times.append(time.time())
            if e.get("type") == "refined"
            else None
        )
    )
    t0 = time.time()
    orch.play()
    # Setup (schema + seed) is synchronous and environment-dependent; the
    # decoupling budget applies to streaming after play() returns.
    t_stream = time.time()
    deadline = time.time() + 15
    while len(raw_times) < 2 and time.time() < deadline:
        time.sleep(0.02)
    # Both raws should land well before 2*0.35s if ingest is unblocked
    assert len(raw_times) >= 2
    assert raw_times[-1] - t_stream < 0.5
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    assert orch.state == "done"
    assert len(refined_times) >= 1
    # First refine still paid the slow cost; second raw did not wait on it
    assert raw_times[1] < refined_times[0] + 0.05 or raw_times[1] < refined_times[0]


def test_orchestrator_reset(tmp_path, mini_log):
    orch = Orchestrator(
        db_path=tmp_path / "r.db", data_log=mini_log, speed=1000.0, force_stub=True
    )
    orch.play()
    deadline = time.time() + 10
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    st = orch.reset()
    assert st["counts"]["raw"] == 0


@pytest.fixture
def client(tmp_path, mini_log):
    app = create_app(
        db_path=tmp_path / "api.db",
        data_log=mini_log,
        speed=1000.0,
        force_stub=True,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_route(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "venice_key_present" in body


def test_controls_route(client):
    r = client.get("/api/controls")
    assert r.status_code == 200
    data = r.get_json()
    assert data["speed"] == 1.0
    assert "force_stub" in data
    assert "venice_key_present" in data


def test_status_route(client):
    assert "state" in client.get("/api/status").get_json()


def test_reset_route(client):
    assert client.post("/api/reset").get_json()["counts"]["raw"] == 0


def test_play_rejects_insane_speed(client):
    r = client.post("/api/play", json={"speed": 5000, "force_stub": True})
    assert r.status_code == 200
    # clamped to 1.0 — do not accept leftover smoke values
    assert client.get("/api/status").get_json()["speed"] == 1.0
    client.post("/api/stop")


def test_play_and_stop_routes(client):
    r = client.post("/api/play", json={"speed": 1000, "force_stub": True})
    assert r.status_code == 200
    assert client.post("/api/stop").status_code == 200
    assert client.get("/api/status").get_json()["state"] == "stopped"


def test_index_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Thalamus" in r.data


def test_sse_events_stream(client):
    # First event on SSE is status
    with client.get("/api/events", buffered=False) as r:
        assert r.status_code == 200
        assert r.mimetype == "text/event-stream"
        chunk = next(r.response)
        assert b"data:" in chunk


def test_broadcast_full_queue():
    q = queue.Queue(maxsize=1)
    q.put_nowait("full")
    with server_mod._sub_lock:
        server_mod._subscribers.append(q)
    try:
        server_mod._broadcast({"type": "console", "message": "x"})
    finally:
        with server_mod._sub_lock:
            if q in server_mod._subscribers:
                server_mod._subscribers.remove(q)


def test_main_runs(monkeypatch, tmp_path):
    called = {}

    def fake_run(host=None, port=None, threaded=None):
        called["host"] = host
        called["port"] = port
        called["threaded"] = threaded

    monkeypatch.setenv("THALAMUS_WEB_HOST", "127.0.0.1")
    monkeypatch.setenv("THALAMUS_WEB_PORT", "8799")
    monkeypatch.setenv("THALAMUS_WEB_DB", str(tmp_path / "main.db"))
    monkeypatch.setattr(server_mod.app, "run", fake_run)
    # recreate orch with temp db via create_app side effects
    create_app(db_path=tmp_path / "main.db", force_stub=True)
    server_mod.main()
    assert called == {"host": "127.0.0.1", "port": 8799, "threaded": True}


def test_stop_keeps_db_and_status_hydrates(tmp_path, mini_log):
    orch = Orchestrator(
        db_path=tmp_path / "keep.db", data_log=mini_log, speed=1000.0, force_stub=True
    )
    orch.play()
    deadline = time.time() + 10
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)
    # Simulate mid-play stop by starting again then stopping quickly
    orch2 = Orchestrator(
        db_path=tmp_path / "keep2.db", data_log=mini_log, speed=0.01, force_stub=True
    )
    # Use real file with long waits via tiny speed on many events — just ingest then stop
    orch2.play()
    time.sleep(0.15)
    orch2.stop()
    orch2.state = "stopped"
    st = orch2.status()
    assert st["counts"]["raw"] >= 1
    # Re-open path without wipe
    orch3 = Orchestrator(db_path=tmp_path / "keep2.db", force_stub=True)
    st3 = orch3.status()
    assert st3["counts"]["raw"] == st["counts"]["raw"]

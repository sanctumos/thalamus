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


def test_call_text_env_force_stub(monkeypatch):
    monkeypatch.setenv("THALAMUS_WEB_FORCE_STUB", "1")
    text, mode = call_text("hello", force_stub=False)
    assert mode == "stub"


def test_load_venice_key_from_env(monkeypatch):
    monkeypatch.setenv("VENICE_API_KEY", "env-key")
    assert load_venice_key() == "env-key"


def test_load_venice_key_from_passfile(tmp_path, monkeypatch):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "venice.pass").write_text(
        "# comment\n\nVENICE_API_KEY=pass-key\n", encoding="utf-8"
    )
    monkeypatch.setattr(llm_mod.Path, "home", classmethod(lambda cls: tmp_path))
    assert load_venice_key() == "pass-key"


def test_load_venice_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    monkeypatch.setattr(llm_mod.Path, "home", classmethod(lambda cls: tmp_path))
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


def test_venice_refine_no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_INFERENCE_KEY", raising=False)
    monkeypatch.setattr(llm_mod.Path, "home", classmethod(lambda cls: tmp_path))
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
    assert r.get_json()["ok"] is True


def test_status_route(client):
    assert "state" in client.get("/api/status").get_json()


def test_reset_route(client):
    assert client.post("/api/reset").get_json()["counts"]["raw"] == 0


def test_play_and_stop_routes(client):
    r = client.post("/api/play", json={"speed": 1000, "force_stub": True})
    assert r.status_code == 200
    assert client.post("/api/stop").status_code == 200


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

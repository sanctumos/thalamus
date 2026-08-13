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


def _write_trip_log(path) -> None:
    """11 segments: monologue → dialog seam that trips the seeded P2 pack,
    then 5 post-trip turns so one P2 refine tick becomes due."""
    segs = [
        # (speaker_id, speaker, duration, text)
        (0, "SPEAKER_0", 25.0, "The market recap continues with bond yields and another long explainer about rates."),
        (0, "SPEAKER_0", 25.0, "More monologue about housing prices and the broader economy this week."),
        (0, "SPEAKER_0", 25.0, "Still the video explainer running through amortization tables in detail."),
        (1, "SPEAKER_1", 2.0, "hey dude"),
        (1, "SPEAKER_1", 3.0, "can you knock out the upload and email it to me"),
        (0, "SPEAKER_0", 3.0, "sure, put them all together in docket today"),
        (1, "SPEAKER_1", 3.0, "I will add some different columns to the docket queue"),
        (0, "SPEAKER_0", 3.0, "the rocketreach export is ready for review"),
        (1, "SPEAKER_1", 3.0, "great, upload those to the shared drive"),
        (0, "SPEAKER_0", 3.0, "modality list is cleaned up too"),
        (1, "SPEAKER_1", 3.0, "send that over when you can"),
    ]
    lines = []
    t = 0.0
    for i, (sid, name, dur, text) in enumerate(segs):
        ts = f"2025-03-26T22:{48 + (i // 60):02d}:{(i % 60):02d}.000000Z"
        lines.append(
            json.dumps(
                {
                    "session_id": "trip-session",
                    "log_timestamp": ts,
                    "segments": [
                        {
                            "text": text,
                            "speaker": name,
                            "speaker_id": sid,
                            "start": t,
                            "end": t + dur,
                        }
                    ],
                }
            )
        )
        t += dur
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def trip_log(tmp_path):
    p = tmp_path / "trip.json"
    _write_trip_log(p)
    return p


def _wait_done(orch, timeout=15.0):
    deadline = time.time() + timeout
    while orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)


def test_secrets_io_does_not_repoint_global_db(tmp_path, mini_log):
    """Regression: get/set_secret must not mutate database.DB_PATH.

    secrets_store used to call db_util.open_db(path), which rebinds the
    process-global database module. Every load_venice_key (per P1 group, per
    evaluator run) silently redirected all replay reads/writes to the secrets
    file — invisible in the server (same file), corrupting elsewhere.
    """
    import database as db_mod
    from web_replay.db_util import load_database
    from web_replay.secrets_store import (
        VENICE_KEY_NAME,
        get_secret,
        secret_hint,
        set_secret,
    )

    replay_db = tmp_path / "replay.db"
    load_database(replay_db)
    secrets_db = tmp_path / "secrets.db"
    set_secret(secrets_db, VENICE_KEY_NAME, "isolation-key")
    assert db_mod.DB_PATH == str(replay_db)
    assert get_secret(secrets_db, VENICE_KEY_NAME) == "isolation-key"
    assert secret_hint(secrets_db, VENICE_KEY_NAME).endswith("key")
    assert db_mod.DB_PATH == str(replay_db)


def test_evaluator_runs_off_ingest_thread(tmp_path, trip_log, monkeypatch):
    """A slow evaluator must not delay P0 intake — it runs on the P2 thread."""
    import web_replay.orchestrator as orch_mod

    def slow_evaluate(db, review_id, **kwargs):
        time.sleep(1.0)
        return {
            "id": review_id,
            "status": "escalated",
            "escalate": True,
            "evaluator_mode": "fake",
            "evaluator_rationale": "slow fake evaluator",
            "trip_raw_segment_id": 6,
            "window_raw_ids": [],
            "window_segments": [],
        }

    monkeypatch.setattr(orch_mod, "evaluate_review", slow_evaluate)

    raw_times: list[float] = []
    decided_times: list[float] = []
    orch = Orchestrator(
        db_path=tmp_path / "p2thread.db",
        data_log=trip_log,
        speed=1000.0,
        force_stub=True,
    )

    def rec(e):
        if e.get("type") == "raw":
            raw_times.append(time.time())
        elif e.get("type") == "p2_review" and e.get("decided"):
            decided_times.append(time.time())

    orch.on_event(rec)
    orch.play()
    # All 11 raws must stream regardless of the evaluator's 1.0s sleep. The
    # sharp decoupling check: raws after the trip (index 5) must not wait for
    # the evaluator — if it ran on the ingest thread they'd be ≥1.0s behind.
    deadline = time.time() + 10
    while len(raw_times) < 11 and time.time() < deadline:
        time.sleep(0.02)
    assert len(raw_times) == 11
    assert raw_times[-1] - raw_times[5] < 0.9
    # The decision arrives later, on the P2 thread, and still escalates.
    while not decided_times and time.time() < deadline:
        time.sleep(0.02)
    assert decided_times and decided_times[0] >= raw_times[5]
    _wait_done(orch)
    st = orch.status()
    assert st["p2"]["mode"] is True
    assert st["p2"]["escalated_latched"] is True


def test_p2_tick_pipeline_on_worker_thread(tmp_path, trip_log):
    """Full path with real (heuristic) evaluator + stub refine: trip →
    escalate on P2 thread → every-5-turns tick → refine pass row + breaker."""
    orch = Orchestrator(
        db_path=tmp_path / "p2tick.db",
        data_log=trip_log,
        speed=1000.0,
        force_stub=True,
    )
    events: list[dict] = []
    orch.on_event(events.append)
    orch.play()
    _wait_done(orch)
    # P2 worker may trail the refine thread's "done" by a few ms — poll.
    deadline = time.time() + 5
    while time.time() < deadline:
        st = orch.status()
        if st["p2"].get("refine_passes"):
            break
        time.sleep(0.05)
    st = orch.status()
    p2 = st["p2"]
    assert p2["mode"] is True
    assert p2["escalated_latched"] is True
    passes = p2.get("refine_passes") or []
    assert passes, "expected at least one P2 refine pass"
    assert passes[0]["mode"] == "stub"
    assert p2.get("breaker_state") == "on"
    br = p2.get("breaker") or {}
    assert br.get("off_need") == 3 and br.get("on_need") == 2
    # P1 fully drained on natural completion — no pending lag remains.
    assert st["counts"]["p1_pending"] == 0
    assert st["counts"]["refined"] >= 1
    assert any(
        e.get("type") == "p2_breaker" and "off_need" in e for e in events
    ), "breaker events should carry streak thresholds"


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

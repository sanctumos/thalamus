#!/usr/bin/env python3
"""Conversation catalog + play-by-id."""

from __future__ import annotations

import json
import time

import pytest

from web_replay.conversations import (
    default_conversation_id,
    list_conversations,
    resolve_conversation,
)
from web_replay.db_util import ingest_event, reset_db, snapshot
from web_replay.server import create_app
from web_replay.streamer import iter_events


def test_catalog_lists_default_and_vertex():
    rows = list_conversations()
    ids = {r["id"] for r in rows}
    assert "cochlea-10min-committee" in ids
    assert "vertex-security-pilot-2026-08-03" in ids
    assert all(r["exists"] for r in rows)
    assert default_conversation_id() == "cochlea-10min-committee"


def test_vertex_ndjson_matches_raw_schema():
    row = resolve_conversation("vertex-security-pilot-2026-08-03")
    events = list(iter_events(row["path"]))
    assert len(events) >= 50
    first = events[0]
    assert first["session_id"] == "13041a6c-820b-4dc4-8644-f9fee88eac27"
    assert first["log_timestamp"].endswith("Z")
    seg = first["segments"][0]
    for key in ("text", "speaker", "speaker_id", "start", "end"):
        assert key in seg
    assert "Vertex" in " ".join(s["text"] for e in events for s in e["segments"]) or any(
        "vertex" in (s["text"] or "").lower() for e in events for s in e["segments"]
    )


def test_vertex_ingests(tmp_path):
    row = resolve_conversation("vertex-security-pilot-2026-08-03")
    db = reset_db(tmp_path / "v.db")
    event = next(iter_events(row["path"]))
    ids = ingest_event(db, event)
    assert ids
    assert snapshot(db)["raw_segments"][0]["text"]


def test_api_conversations_and_play_switch(tmp_path, mini_log):
    # create_app with mini_log still exposes catalog; play can switch to vertex
    app = create_app(
        db_path=tmp_path / "c.db",
        data_log=mini_log,
        speed=1000.0,
        force_stub=True,
        conversation_id="test-mini",
    )
    client = app.test_client()
    r = client.get("/api/conversations")
    assert r.status_code == 200
    body = r.get_json()
    assert any(c["id"] == "vertex-security-pilot-2026-08-03" for c in body["conversations"])

    r = client.post(
        "/api/play",
        json={
            "speed": 10000,
            "force_stub": True,
            "conversation_id": "vertex-security-pilot-2026-08-03",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["conversation_id"] == "vertex-security-pilot-2026-08-03"
    # wait briefly for ingest to land some rows
    deadline = time.time() + 8
    while time.time() < deadline:
        st = client.get("/api/status").get_json()
        if st["counts"]["raw"] > 0:
            break
        time.sleep(0.05)
    st = client.get("/api/status").get_json()
    assert st["counts"]["raw"] > 0
    client.post("/api/stop")


def test_play_unknown_conversation(tmp_path, mini_log):
    app = create_app(
        db_path=tmp_path / "u.db", data_log=mini_log, speed=1000.0, force_stub=True
    )
    client = app.test_client()
    r = client.post(
        "/api/play",
        json={"speed": 1000, "force_stub": True, "conversation_id": "no-such-feed"},
    )
    assert r.status_code == 400
    assert "unknown" in (r.get_json().get("error") or "").lower()

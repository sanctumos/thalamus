#!/usr/bin/env python3
"""
P2 refine engine + home-topic breaker tests.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import pytest

from web_replay.db_util import reset_db
from web_replay.p2_filters.breaker import TopicBreaker, score_batch, start_topic_state
from web_replay.p2_filters.refine_engine import list_refine_passes, run_refine_pass
from web_replay.p2_filters.store import get_settings, patch_settings


@pytest.fixture()
def p2_db(tmp_path):
    db_path = tmp_path / "p2_refine.db"
    db = reset_db(db_path)
    yield db


def _seed_segments(db, texts):
    from web_replay.db_util import ingest_event
    import time

    ids = []
    for i, text in enumerate(texts):
        ev = {
            "log_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1700000000 + i)),
            "session_id": "s1",
            "segments": [
                {
                    "speaker_id": 1,
                    "speaker": "SPEAKER_00",
                    "text": text,
                    "start": float(i * 5),
                    "end": float(i * 5 + 4),
                }
            ],
        }
        ids.extend(ingest_event(db, ev))
    return ids


def test_refine_pass_stub_writes_row(p2_db):
    db = p2_db
    ids = _seed_segments(db, ["hello world", "let us talk about the docket queue"])
    row = run_refine_pass(
        db,
        anchor_raw_id=ids[0],
        topic_score=0.5,
        home_terms=["docket", "queue"],
        force_stub=True,
    )
    assert row["mode"] == "stub"
    assert "SPEAKER_00" in row["text"]
    assert row["window_start_raw_id"] == ids[0]
    passes = list_refine_passes(db)
    assert len(passes) == 1
    assert passes[0]["pass_index"] == 1


def test_breaker_hysteresis_off_then_on(p2_db):
    db = p2_db
    patch_settings(
        db,
        {
            "p2_breaker_off_score": "0.18",
            "p2_breaker_on_score": "0.34",
            "p2_breaker_off_streak": "2",
            "p2_breaker_on_streak": "2",
        },
    )
    st = start_topic_state(
        db,
        home_text="docket queue rocketreach exports imaging",
        project_card="docket queue rocketreach",
        anchor_raw_id=1,
    )
    assert st["state"] == "on"
    br = TopicBreaker(db)
    assert br.is_on

    off_text = "the weather is nice and the video game was fun"
    r1 = br.observe_batch(off_text)
    assert r1["state"] == "on"  # streak 1, not flipped yet
    r2 = br.observe_batch(off_text)
    assert r2["state"] == "off"
    assert r2["flipped"] is True

    on_text = "back to the docket queue and rocketreach exports for imaging"
    r3 = br.observe_batch(on_text)
    assert r3["state"] == "off"  # streak 1
    r4 = br.observe_batch(on_text)
    assert r4["state"] == "on"
    assert r4["flipped"] is True


def test_breaker_closing_cue_weak_penalty(p2_db):
    db = p2_db
    patch_settings(
        db,
        {
            "p2_breaker_off_score": "0.18",
            "p2_breaker_on_score": "0.34",
            "p2_breaker_off_streak": "3",
            "p2_breaker_on_streak": "2",
        },
    )
    start_topic_state(
        db,
        home_text="docket queue rocketreach exports imaging",
        project_card="docket queue",
        anchor_raw_id=1,
    )
    br = TopicBreaker(db)
    # On-topic but with a closing cue — penalty should not flip alone
    r = br.observe_batch("sounds good, see you dude — docket queue rocketreach exports")
    assert r["state"] == "on"
    assert r["flipped"] is False
    assert "sounds good" in (r["detail"].get("closing_cues") or [])


def test_score_batch_overlap():
    score, detail = score_batch(
        "docket queue and rocketreach exports",
        ["docket", "queue", "rocketreach", "exports"],
    )
    assert score > 0.3
    assert "docket" in detail["matched"]


def test_settings_defaults_present(p2_db):
    s = get_settings(p2_db)
    assert s["p2_refine_every_turns_i"] == 5
    assert s["p2_refine_max_segments_i"] == 80
    assert s["p2_breaker_enabled_b"] is True
    assert s["p2_breaker_off_streak_i"] == 3
    assert s["p2_breaker_on_streak_i"] == 2

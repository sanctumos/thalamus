#!/usr/bin/env python3
"""
P2 filter scorer — mortgage NDJSON: no trip on hi alone; cumulative ops substance.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web_replay.db_util import ingest_event, open_db
from web_replay.p2_filters.evaluator import evaluate_review, heuristic_evaluate
from web_replay.p2_filters.review import decide_review, list_reviews
from web_replay.p2_filters.scorer import P2Scorer, SegmentView
from web_replay.p2_filters.seed import seed_default_pack
from web_replay.p2_filters.store import get_settings, list_filter_packs, patch_settings

CONV = (
    Path(__file__).resolve().parents[1]
    / "conversations"
    / "omi-live-webhook-mortgage-2026-08-11.ndjson"
)


def _load_events():
    assert CONV.is_file(), f"missing feed {CONV}"
    return [
        json.loads(line)
        for line in CONV.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _observe_event(db, scorer, ev):
    results = []
    raw_ids = ingest_event(db, ev)
    segs = ev.get("segments") or []
    for rid, seg in zip(raw_ids, segs):
        results.append(
            (
                seg,
                scorer.observe(
                    SegmentView(
                        raw_id=int(rid),
                        speaker_id=int(seg.get("speaker_id") or 0),
                        speaker_name=str(seg.get("speaker") or ""),
                        text=str(seg.get("text") or ""),
                        start_time=float(seg.get("start") or 0),
                        end_time=float(seg.get("end") or 0),
                    )
                ),
            )
        )
    return results


@pytest.fixture
def p2_db(tmp_path):
    db_path = tmp_path / "p2.db"
    db = open_db(db_path)
    seed_default_pack(db, force_rules=True)
    patch_settings(db, {"p2_evaluator_mode": "heuristic"})
    return db


def test_seed_pack_present(p2_db):
    packs = list_filter_packs(p2_db)
    assert any(p["slug"] == "video_to_dialog_handoff" for p in packs)
    settings = get_settings(p2_db)
    assert float(settings["trip_threshold"]) == 12.0
    assert settings["trip_require_substance_b"] is True
    assert settings["enrichment_gate_enabled"].lower() in ("false", "0")


def test_mortgage_no_trip_on_greeting_alone_then_trips_on_ops(p2_db):
    events = _load_events()
    scorer = P2Scorer(p2_db)

    # Video head + Hey Chief greeting — accumulate, but do not trip yet
    for ei, ev in enumerate(events[:10]):
        for seg, result in _observe_event(p2_db, scorer, ev):
            assert not result.tripped, (
                f"too-early trip at ev{ei:03d}: {(seg.get('text') or '')[:80]}"
            )

    assert not scorer.awaiting_review
    assert scorer.running_score > 0  # greeting/structure contributed

    # Continue until first trip — should be ops substance (upload / columns / knock)
    review = None
    tripped_text = None
    tripped_ei = None
    for ei, ev in enumerate(events[10:], start=10):
        for seg, result in _observe_event(p2_db, scorer, ev):
            if result.tripped:
                tripped_ei = ei
                tripped_text = (seg.get("text") or "")[:100]
                review = result.review
                kinds = {
                    h.get("rule_kind")
                    for h in (review.get("evidence") or {}).get("hits") or []
                }
                assert kinds & {"tasking_lexicon", "proper_noun_lexicon"}
                break
        if review:
            break

    assert review is not None, "expected cumulative ops trip after greeting"
    assert tripped_ei is not None and tripped_ei >= 10
    assert "chief" not in (tripped_text or "").lower()

    decided = evaluate_review(p2_db, int(review["id"]), force_mode="heuristic")
    assert decided["status"] == "escalated"
    scorer.on_review_decided(True)
    assert scorer.escalated_latched

    for ev in events[tripped_ei + 1 :]:
        for _seg, result in _observe_event(p2_db, scorer, ev):
            assert result.deltas == []
            assert not result.tripped
    assert len(list_reviews(p2_db, status="escalated")) == 1


def test_heuristic_escalates_on_greeting_factoid():
    fake = {
        "evidence": {
            "hits": [
                {
                    "rule_kind": "greeting_lexicon",
                    "delta": 2,
                    "evidence": {"matched": "hey chief"},
                }
            ],
            "salient_spans": [{"rule_kind": "greeting_lexicon", "matched": "hey chief"}],
        }
    }
    esc, rationale = heuristic_evaluate(fake)
    assert esc is True
    assert "greeting" in rationale.lower()


def test_decline_rearms_filter(p2_db):
    events = _load_events()
    scorer = P2Scorer(p2_db)
    review = None
    for ev in events[:20]:
        for _seg, result in _observe_event(p2_db, scorer, ev):
            if result.tripped:
                review = result.review
                break
        if review:
            break
    assert review is not None
    decide_review(p2_db, int(review["id"]), escalate=False, note="not yet")
    scorer.on_review_decided(False)
    assert not scorer.escalated_latched
    assert not scorer.awaiting_review
    assert scorer.running_score == 0.0

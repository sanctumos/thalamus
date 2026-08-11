#!/usr/bin/env python3
"""Unit tests — TimeSimulator + streamer (≥90% gate for slice 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web_replay.streamer import iter_events, stream_events
from web_replay.time_simulator import TimeSimulator, parse_log_timestamp


def test_parse_log_timestamp_z():
    dt = parse_log_timestamp("2025-03-26T22:48:11.021743Z")
    assert dt.year == 2025
    assert dt.tzinfo is not None


def test_speed_must_be_positive():
    with pytest.raises(ValueError):
        TimeSimulator(speed=0)


def test_first_event_no_wait():
    sleeps = []
    sim = TimeSimulator(speed=1.0, sleep_fn=lambda s: sleeps.append(s))
    waited = sim.wait_before("2025-03-26T22:48:11.021743Z")
    assert waited == 0.0
    assert sleeps == []


def test_second_event_waits_delta():
    sleeps = []
    sim = TimeSimulator(speed=1.0, sleep_fn=lambda s: sleeps.append(s))
    sim.wait_before("2025-03-26T22:48:11.000000Z")
    waited = sim.wait_before("2025-03-26T22:48:13.000000Z")
    assert waited == pytest.approx(2.0)
    assert sleeps == [pytest.approx(2.0)]


def test_speed_multiplier_shortens_wait():
    sleeps = []
    sim = TimeSimulator(speed=10.0, sleep_fn=lambda s: sleeps.append(s))
    sim.wait_before("2025-03-26T22:48:00.000000Z")
    waited = sim.wait_before("2025-03-26T22:48:10.000000Z")
    assert waited == pytest.approx(1.0)
    assert sim.waits == [pytest.approx(1.0)]


def test_reset_clears_last():
    sleeps = []
    sim = TimeSimulator(speed=1.0, sleep_fn=lambda s: sleeps.append(s))
    sim.wait_before("2025-03-26T22:48:00.000000Z")
    sim.reset()
    waited = sim.wait_before("2025-03-26T22:48:05.000000Z")
    assert waited == 0.0
    assert sleeps == []


def test_iter_events_reads_real_log():
    events = list(iter_events())
    assert len(events) >= 10
    assert "log_timestamp" in events[0]
    assert "segments" in events[0]


def test_stream_events_respects_sim(tmp_path):
    sample = tmp_path / "mini.json"
    sample.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": "s1",
                        "log_timestamp": "2025-03-26T22:48:00.000000Z",
                        "segments": [
                            {
                                "text": "a",
                                "speaker": "SPEAKER_0",
                                "speaker_id": 0,
                                "start": 0,
                                "end": 1,
                            }
                        ],
                    }
                ),
                "",
                json.dumps(
                    {
                        "session_id": "s1",
                        "log_timestamp": "2025-03-26T22:48:04.000000Z",
                        "segments": [
                            {
                                "text": "b",
                                "speaker": "SPEAKER_0",
                                "speaker_id": 0,
                                "start": 1,
                                "end": 2,
                            }
                        ],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    waits = []
    waited_cb = []
    sim = TimeSimulator(speed=1.0, sleep_fn=lambda s: waits.append(s))
    out = list(
        stream_events(
            sim, path=sample, on_wait=lambda w, ts: waited_cb.append((w, ts))
        )
    )
    assert len(out) == 2
    assert waits == [pytest.approx(4.0)]
    assert waited_cb[0][0] == pytest.approx(4.0)
    assert out[0]["segments"][0]["text"] == "a"


def test_naive_datetime_gets_utc():
    from datetime import datetime

    sleeps = []
    sim = TimeSimulator(speed=1.0, sleep_fn=lambda s: sleeps.append(s))
    waited = sim.wait_before(datetime(2025, 3, 26, 22, 48, 0))
    assert waited == 0.0
    assert sim._last.tzinfo is not None

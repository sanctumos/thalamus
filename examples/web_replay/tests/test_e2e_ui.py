#!/usr/bin/env python3
"""E2E — Play under sped sim: trickle order + UI assets."""

from __future__ import annotations

import json
import time

from web_replay.orchestrator import Orchestrator
from web_replay.server import create_app


def test_e2e_trickle_order_not_batch(tmp_path):
    mini = tmp_path / "e2e.json"
    mini.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": "e2e",
                        "log_timestamp": "2025-03-26T22:48:00.000000Z",
                        "segments": [
                            {
                                "text": "First utterance",
                                "speaker": "SPEAKER_0",
                                "speaker_id": 0,
                                "start": 0,
                                "end": 1,
                            }
                        ],
                    }
                ),
                json.dumps(
                    {
                        "session_id": "e2e",
                        "log_timestamp": "2025-03-26T22:48:01.000000Z",
                        "segments": [
                            {
                                "text": "Second utterance",
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

    app = create_app(
        db_path=tmp_path / "e2e.db",
        data_log=mini,
        speed=500.0,
        force_stub=True,
    )
    # Grab orchestrator from server module after factory
    import web_replay.server as server

    timeline = []
    server.orch.on_event(lambda e: timeline.append(e.get("type")))

    client = app.test_client()
    assert client.get("/").status_code == 200
    assert b"Raw / Cochlea" in client.get("/").data
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200

    r = client.post("/api/play", json={"speed": 500, "force_stub": True})
    assert r.status_code == 200

    deadline = time.time() + 15
    while server.orch.state == "playing" and time.time() < deadline:
        time.sleep(0.05)

    assert server.orch.state == "done"
    assert "raw" in timeline and "refined" in timeline
    assert timeline.index("raw") < timeline.index("refined")

    st = client.get("/api/status").get_json()
    assert st["counts"]["raw"] >= 1
    assert st["counts"]["refined"] >= 1

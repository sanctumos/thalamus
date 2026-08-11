#!/usr/bin/env python3
"""Reusable checks for refine-model whitelist (lab ≥85%).

Default: offline schema + score floor.
With network: assert whitelisted IDs still exist on Venice.
With VENICE_LAB=1: re-run full ladder (slow/paid) — see lab_model_ladder.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from web_replay.model_catalog import (
    PASS_PCT_MIN,
    WHITELIST_PATH,
    default_model_id,
    is_whitelisted,
    load_whitelist,
    whitelist_ids,
    write_whitelist_from_lab_summaries,
)


def test_whitelist_file_exists_and_schema():
    data = load_whitelist()
    assert data["version"] >= 1
    assert float(data["pass_pct_min"]) == PASS_PCT_MIN
    assert data["models"]
    assert default_model_id() in whitelist_ids()


def test_whitelist_only_models_at_or_above_threshold():
    data = load_whitelist()
    floor = float(data["pass_pct_min"])
    for m in data["models"]:
        assert float(m["pass_pct"]) >= floor, m
        assert "cost_rating" in m and m["cost_rating"] in ("$", "$$", "$$$")
        assert float(m["cost_rel"]) >= 1.0
        assert "price" in m


def test_write_whitelist_from_summaries_roundtrip(tmp_path):
    summaries = [
        {
            "model": "cheap-ok",
            "pass_pct": 92.0,
            "mean_quality": 0.9,
            "hard_fails": 0,
            "mean_latency_ms": 100,
            "price": {"input_usd_per_m": 0.1, "output_usd_per_m": 0.2},
        },
        {
            "model": "fail-low",
            "pass_pct": 50.0,
            "mean_quality": 0.4,
            "hard_fails": 5,
            "mean_latency_ms": 100,
            "price": {"input_usd_per_m": 0.05, "output_usd_per_m": 0.05},
        },
        {
            "model": "spendier-ok",
            "pass_pct": 100.0,
            "mean_quality": 0.95,
            "hard_fails": 0,
            "mean_latency_ms": 100,
            "price": {"input_usd_per_m": 1.0, "output_usd_per_m": 2.0},
        },
    ]
    out = tmp_path / "wl.json"
    data = write_whitelist_from_lab_summaries(
        summaries, lab_date="2099-01-01", path=out, pass_pct_min=85.0
    )
    ids = {m["id"] for m in data["models"]}
    assert ids == {"cheap-ok", "spendier-ok"}
    assert data["models"][0]["id"] == "cheap-ok"
    assert data["models"][0]["cost_rating"] == "$"
    assert data["models"][-1]["cost_rating"] == "$$$"


def test_settings_rejects_non_whitelist(tmp_path, mini_log_path=None):
    from web_replay.server import create_app

    # reuse mini log from sibling test fixture pattern
    import json
    from pathlib import Path

    p = tmp_path / "mini.json"
    p.write_text(
        json.dumps(
            {
                "session_id": "s",
                "log_timestamp": "2025-03-26T22:48:00.000000Z",
                "segments": [
                    {
                        "text": "hi",
                        "speaker": "SPEAKER_0",
                        "speaker_id": 0,
                        "start": 0,
                        "end": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(db_path=tmp_path / "m.db", data_log=p, force_stub=True)
    client = app.test_client()
    bad = client.post("/api/settings", json={"venice_model": "not-a-real-model-xyz"})
    assert bad.status_code == 400
    good_id = default_model_id()
    assert is_whitelisted(good_id)
    ok = client.post("/api/settings", json={"venice_model": good_id})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["venice_model"] == good_id
    assert body["venice_model_options"]
    assert all(o["pass_pct"] >= PASS_PCT_MIN for o in body["venice_model_options"])
    # options expose score + cost for UI
    sample = body["venice_model_options"][0]
    assert "cost_rating" in sample and "pass_pct" in sample


@pytest.mark.network
def test_whitelisted_models_still_listed_on_venice():
    """When Venice catalog changes, fail if a whitelisted id disappears."""
    if os.environ.get("VENICE_SKIP_NETWORK") == "1":
        pytest.skip("VENICE_SKIP_NETWORK=1")
    key = os.environ.get("VENICE_API_KEY") or os.environ.get("VENICE_INFERENCE_KEY")
    if not key:
        key = _load_venice_key_from_disk()
    if not key:
        pytest.skip("no Venice key in env for network check")

    req = urllib.request.Request(
        "https://api.venice.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    live = {m["id"] for m in data.get("data") or []}
    missing = [mid for mid in whitelist_ids() if mid not in live]
    assert not missing, (
        f"Whitelisted refine models missing from Venice listings: {missing}. "
        f"Re-run: PYTHONPATH=examples python3 -m web_replay.lab_model_ladder"
    )


def _load_venice_key_from_disk():
    from pathlib import Path

    for p in (
        Path.home() / ".ssh" / "venice.pass",
        Path("/root/.config/private-docs-venice.env"),
    ):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() in ("VENICE_API_KEY", "VENICE_INFERENCE_KEY") and v.strip():
                return v.strip().strip("'").strip('"')
    return None


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("VENICE_LAB") != "1", reason="Set VENICE_LAB=1 to re-run paid ladder")
def test_rerun_full_model_ladder_updates_whitelist():
    """Paid regression: full ladder + rewrite whitelist. Opt-in only."""
    from web_replay.lab_model_ladder import main

    main()
    data = load_whitelist()
    assert WHITELIST_PATH.exists()
    assert all(float(m["pass_pct"]) >= PASS_PCT_MIN for m in data["models"])

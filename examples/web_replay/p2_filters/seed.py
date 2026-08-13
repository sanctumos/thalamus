#!/usr/bin/env python3
"""
Idempotent seed for video_to_dialog_handoff filter pack (mortgage→Jim seam).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .schema import ensure_p2_tables
from .store import ensure_default_settings, get_filter_pack, list_filter_rules

PACK_SLUG = "video_to_dialog_handoff"
PACK_TITLE = "Video → dialog handoff"
PACK_NOTES = (
    "Non-LLM P2 accumulator for ambient monologue → real multi-party work talk. "
    "Tuned on 2026-08-11 Omi live webhook (mortgage YouTube → Mark/partner ops). "
    "Greeting alone does not tip — cumulative score + ops substance (tasking/nouns); "
    "internal Thalamus evaluator auto-decides escalate."
)

# Strong signals first, confirmers lower weight.
# Greeting is a weak opener (personal/business "hi") — must accumulate with ops
# substance before trip (see trip_threshold + trip_require_substance).
RULE_SPECS: List[Dict[str, Any]] = [
    {
        "kind": "greeting_lexicon",
        "priority": 10,
        "weight": 2.0,
        "params": {
            "phrases": [
                "hey chief",
                "how's it going",
                "hows it going",
                "hey dude",
                "okay dude",
                "see you dude",
            ]
        },
    },
    {
        "kind": "speaker_entry",
        "priority": 20,
        "weight": 3.0,
        "params": {
            # New speaker after this many consecutive other-speaker segments
            "min_prior_stretch": 3,
        },
    },
    {
        "kind": "segment_length_flip",
        "priority": 30,
        "weight": 3.0,
        "params": {
            # Use settings long/short defaults; params override if present
            "min_prior_long": 2,
        },
    },
    {
        "kind": "tasking_lexicon",
        "priority": 40,
        "weight": 2.0,
        "params": {
            "phrases": [
                "can you knock",
                "send you over",
                "send that over",
                "email it",
                "email it to",
                "upload",
                "instructions on uploading",
                "put them all together",
                "add some different columns",
            ]
        },
    },
    {
        "kind": "proper_noun_lexicon",
        "priority": 50,
        "weight": 2.0,
        "params": {
            "phrases": [
                "cameron",
                "docket",
                "gmail",
                "claude",
                "rocket reach",
                "rocketreach",
                "radiologist-technologist",
                "radiologist technologist",
                "modality",
                "jazz hands",
            ]
        },
    },
    {
        "kind": "backchannel_burst",
        "priority": 60,
        "weight": 1.0,
        "params": {
            "phrases": ["mm-hmm", "mmhmm", "okay", "yeah", "right", "uh-huh"],
            "max_chars": 24,
            "after_long": True,
        },
    },
]


def seed_default_pack(db: Any, *, force_rules: bool = False) -> Dict[str, Any]:
    """Upsert pack + rules by kind within pack. Idempotent."""
    ensure_p2_tables(db)
    ensure_default_settings(db)

    with db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO filter_packs (slug, title, enabled, notes, updated_at)
            VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (PACK_SLUG, PACK_TITLE, PACK_NOTES),
        )
        conn.commit()

    pack = get_filter_pack(db, slug=PACK_SLUG)
    assert pack is not None
    pack_id = int(pack["id"])

    existing = {r["kind"]: r for r in list_filter_rules(db, pack_id)}
    with db.get_db() as conn:
        for spec in RULE_SPECS:
            kind = spec["kind"]
            params_json = json.dumps(spec["params"])
            if kind in existing and not force_rules:
                conn.execute(
                    """
                    UPDATE filter_rules SET
                        weight = ?,
                        priority = ?,
                        params_json = ?,
                        enabled = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        float(spec["weight"]),
                        int(spec["priority"]),
                        params_json,
                        int(existing[kind]["id"]),
                    ),
                )
            elif kind in existing and force_rules:
                conn.execute(
                    """
                    UPDATE filter_rules SET
                        weight = ?,
                        priority = ?,
                        params_json = ?,
                        enabled = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        float(spec["weight"]),
                        int(spec["priority"]),
                        params_json,
                        int(existing[kind]["id"]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO filter_rules
                        (pack_id, kind, params_json, weight, enabled, priority)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (
                        pack_id,
                        kind,
                        params_json,
                        float(spec["weight"]),
                        int(spec["priority"]),
                    ),
                )
        conn.commit()

    return {
        "pack": get_filter_pack(db, slug=PACK_SLUG),
        "rules": list_filter_rules(db, pack_id),
    }

#!/usr/bin/env python3
"""
P2 home-topic breaker — hysteresis on/off for P2 refine.

Home topic = content terms from the last on-topic refine pass + project card.
Score each new segment batch vs home; flip off only after N consecutive low
batches, back on after M consecutive high batches. Closing cues are a weak
penalty, never a sole flip.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .schema import ensure_p2_tables
from .store import get_settings

STOPWORDS = frozenset(
    """
    a an and are as at be but by for from had has have he her his i if in into is
    it its just like me my of on or our so that the their them they this to was we
    what when who will with you your yeah okay right uh um mm mm-hmm mmhmm going got
    do does did can could would should not no yes well now then there here out over
    about really very some any all one two get go see know think say said says
    """.split()
)

CLOSING_CUES = (
    "talk to you later",
    "talk soon",
    "see you dude",
    "see you later",
    "sounds good",
    "let's wrap",
    "lets wrap",
    "wrap it up",
    "gotta go",
    "got to go",
    "catch you later",
    "bye",
)


def _tokens(text: str) -> List[str]:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9\s'-]", " ", t)
    return [w for w in t.split() if len(w) > 2 and w not in STOPWORDS]


def _top_terms(text: str, limit: int = 24) -> List[str]:
    freq: Dict[str, int] = {}
    for w in _tokens(text):
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _row_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def get_topic_state(db: Any) -> Optional[Dict[str, Any]]:
    ensure_p2_tables(db)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM p2_topic_state ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = _row_dict(row)
    try:
        d["home_terms"] = json.loads(d.get("home_terms_json") or "[]")
    except json.JSONDecodeError:
        d["home_terms"] = []
    return d


def start_topic_state(
    db: Any,
    *,
    home_text: str,
    project_card: str,
    anchor_raw_id: int,
    last_pass_raw_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Seed home topic at escalate (window text + project card nouns).

    last_pass_raw_id: refine passes emit only segments after this id. Pass
    window_start - 1 so the first pass covers the whole trip window.
    """
    ensure_p2_tables(db)
    terms = _top_terms(f"{home_text}\n{project_card}", limit=24)
    last_id = int(last_pass_raw_id) if last_pass_raw_id is not None else int(anchor_raw_id)
    with db.get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO p2_topic_state
                (state, home_text, home_terms_json, on_streak, off_streak,
                 last_pass_raw_id)
            VALUES ('on', ?, ?, 0, 0, ?)
            """,
            (home_text[:4000], json.dumps(terms), last_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM p2_topic_state WHERE id = ?", (int(cur.lastrowid),)
        ).fetchone()
    d = _row_dict(row)
    d["home_terms"] = terms
    return d


def score_batch(
    batch_text: str, home_terms: List[str], *, closing_penalty: float = 0.0
) -> Tuple[float, Dict[str, Any]]:
    """Weighted overlap of batch content terms vs home terms (0..1-ish)."""
    batch_terms = _tokens(batch_text)
    if not batch_terms or not home_terms:
        return 0.0, {"matched": [], "batch_terms": len(batch_terms)}
    home = set(home_terms)
    matched = sorted({w for w in batch_terms if w in home})
    # coverage of home + density in batch
    cov = len(matched) / max(1, len(home))
    dens = len(matched) / max(1, len(set(batch_terms)))
    score = (0.65 * cov) + (0.35 * dens)
    low = (batch_text or "").lower()
    closing_hits = [c for c in CLOSING_CUES if c in low]
    if closing_hits:
        score = max(0.0, score - closing_penalty)
    return score, {
        "matched": matched[:12],
        "coverage": round(cov, 3),
        "density": round(dens, 3),
        "closing_cues": closing_hits,
    }


class TopicBreaker:
    """Stateful breaker for one Play (P2 mode)."""

    def __init__(self, db: Any) -> None:
        self.db = db
        ensure_p2_tables(db)
        st = get_topic_state(db)
        self.state = (st or {}).get("state") or "off"
        self.home_terms: List[str] = list((st or {}).get("home_terms") or [])
        self.on_streak = int((st or {}).get("on_streak") or 0)
        self.off_streak = int((st or {}).get("off_streak") or 0)
        self.last_pass_raw_id = int((st or {}).get("last_pass_raw_id") or 0)
        self.last_topic_score: Optional[float] = None

    @property
    def is_on(self) -> bool:
        return self.state == "on"

    def mark_pass(self, raw_id: int) -> None:
        """Record refine coverage — next pass emits only segments after this."""
        self.last_pass_raw_id = int(raw_id)
        with self.db.get_db() as conn:
            row = conn.execute(
                "SELECT id FROM p2_topic_state ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return
            rid = row["id"] if hasattr(row, "keys") else row[0]
            conn.execute(
                """
                UPDATE p2_topic_state SET
                    last_pass_raw_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (self.last_pass_raw_id, rid),
            )
            conn.commit()

    def _persist(self) -> None:
        with self.db.get_db() as conn:
            row = conn.execute(
                "SELECT id FROM p2_topic_state ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return
            rid = row["id"] if hasattr(row, "keys") else row[0]
            conn.execute(
                """
                UPDATE p2_topic_state SET
                    state = ?, on_streak = ?, off_streak = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (self.state, self.on_streak, self.off_streak, rid),
            )
            conn.commit()

    def update_home(self, refine_text: str, project_card: str) -> None:
        """Slow home drift — only on successful on-topic refine passes."""
        terms = _top_terms(f"{refine_text}\n{project_card}", limit=24)
        if not terms:
            return
        self.home_terms = terms
        with self.db.get_db() as conn:
            row = conn.execute(
                "SELECT id FROM p2_topic_state ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return
            rid = row["id"] if hasattr(row, "keys") else row[0]
            conn.execute(
                """
                UPDATE p2_topic_state SET
                    home_text = ?, home_terms_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (refine_text[:4000], json.dumps(terms), rid),
            )
            conn.commit()

    def observe_batch(self, batch_text: str) -> Dict[str, Any]:
        """
        Score a new batch of raw segments; maybe flip state (hysteresis).
        Returns {state, topic_score, flipped, reason, detail, on_streak,
        off_streak, on_score, off_score, on_need, off_need}.
        """
        settings = get_settings(self.db)
        if not settings["p2_breaker_enabled_b"]:
            return {
                "state": self.state,
                "topic_score": None,
                "flipped": False,
                "reason": "breaker disabled",
                "detail": {},
            }

        off_score = settings["p2_breaker_off_score_f"]
        on_score = settings["p2_breaker_on_score_f"]
        off_need = settings["p2_breaker_off_streak_i"]
        on_need = settings["p2_breaker_on_streak_i"]
        closing_pen = settings["p2_breaker_closing_penalty_f"]

        score, detail = score_batch(
            batch_text, self.home_terms, closing_penalty=closing_pen
        )
        self.last_topic_score = score
        flipped = False
        reason = ""

        if self.state == "on":
            if score < off_score:
                self.off_streak += 1
                self.on_streak = 0
                if self.off_streak >= off_need:
                    self.state = "off"
                    flipped = True
                    reason = (
                        f"off: {self.off_streak} batches < {off_score} "
                        f"(last {score:.2f})"
                    )
            else:
                self.off_streak = 0
                if score >= on_score:
                    self.on_streak = min(self.on_streak + 1, on_need)
        else:  # off
            if score >= on_score:
                self.on_streak += 1
                self.off_streak = 0
                if self.on_streak >= on_need:
                    self.state = "on"
                    flipped = True
                    reason = (
                        f"on: {self.on_streak} batches >= {on_score} "
                        f"(last {score:.2f})"
                    )
            else:
                self.on_streak = 0
                if score < off_score:
                    self.off_streak = min(self.off_streak + 1, off_need)

        # Persist every tick (not just flips) so a refresh / restart
        # rehydrates the exact streak state for the breaker badge.
        self._persist()
        return {
            "state": self.state,
            "topic_score": round(score, 3),
            "flipped": flipped,
            "reason": reason,
            "detail": detail,
            "on_streak": self.on_streak,
            "off_streak": self.off_streak,
            "on_score": on_score,
            "off_score": off_score,
            "on_need": on_need,
            "off_need": off_need,
        }

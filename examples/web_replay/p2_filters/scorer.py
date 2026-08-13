#!/usr/bin/env python3
"""
Pure-Python P2 accumulator — no LLM.

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .review import create_review_prompt
from .schema import ensure_p2_tables
from .seed import seed_default_pack
from .store import active_pack_and_rules

# Ops / project evidence — "hi" alone is not enough to trip.
SUBSTANCE_KINDS = frozenset({"tasking_lexicon", "proper_noun_lexicon"})


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^\w\s'-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _phrase_hit(text: str, phrases: List[str]) -> Optional[str]:
    norm = _norm(text)
    for p in phrases:
        pn = _norm(p)
        if pn and pn in norm:
            return p
    return None


@dataclass
class SegmentView:
    raw_id: int
    speaker_id: int
    speaker_name: str
    text: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))


@dataclass
class ScoreResult:
    deltas: List[Dict[str, Any]] = field(default_factory=list)
    running_score: float = 0.0
    tripped: bool = False
    review: Optional[Dict[str, Any]] = None
    awaiting_review: bool = False


class P2Scorer:
    """Stateful accumulator for one Play / epoch."""

    def __init__(self, db: Any) -> None:
        self.db = db
        ensure_p2_tables(db)
        seed_default_pack(db)
        self.running_score = 0.0
        self.history: List[SegmentView] = []
        self.awaiting_review = False
        self._pending_review_id: Optional[int] = None
        # After a successful escalate, stop filter/eval for the rest of this Play.
        self.escalated_latched = False
        self._epoch_kinds: set = set()
        self._epoch_hits: List[Dict[str, Any]] = []

    def reset_epoch(self) -> None:
        self.running_score = 0.0
        self.awaiting_review = False
        self._pending_review_id = None
        self.escalated_latched = False
        self._epoch_kinds = set()
        self._epoch_hits = []
        # keep history for structural sketch across epoch? clear for new play
        self.history = []

    def observe(self, segment: SegmentView) -> ScoreResult:
        """Score one ingested raw segment. May open a review on trip."""
        pack, rules, settings = active_pack_and_rules(self.db)
        result = ScoreResult(running_score=self.running_score)

        # Successful escalate → done for this Play (no more hits/trips/evals).
        if self.escalated_latched:
            result.running_score = self.running_score
            return result

        if self.awaiting_review:
            result.awaiting_review = True
            result.running_score = self.running_score
            self.history.append(segment)
            return result

        if not pack or not rules:
            self.history.append(segment)
            return result

        threshold = float(settings["trip_threshold_f"])
        decay = float(settings["score_decay_per_segment_f"])
        long_s = float(settings["long_segment_seconds_f"])
        short_s = float(settings["short_segment_seconds_f"])
        require_substance = bool(settings.get("trip_require_substance_b", True))

        # Soft decay each segment before adding new hits
        if self.running_score > 0 and decay > 0:
            self.running_score = max(0.0, self.running_score - decay)

        hits: List[Tuple[Dict[str, Any], float, Dict[str, Any]]] = []
        for rule in rules:
            kind = rule["kind"]
            params = rule.get("params") or {}
            weight = float(rule.get("weight") or 0)
            evidence = self._eval_rule(
                kind, params, segment, long_s=long_s, short_s=short_s
            )
            if evidence is not None:
                hits.append((rule, weight, evidence))

        for rule, weight, evidence in hits:
            self.running_score += weight
            row = {
                "rule_id": int(rule["id"]),
                "rule_kind": rule["kind"],
                "delta": weight,
                "running_score": self.running_score,
                "evidence": evidence,
                "tripped": 0,
            }
            result.deltas.append(row)
            self._epoch_kinds.add(str(rule["kind"]))
            self._epoch_hits.append(row)
            self._persist_hit(
                pack_id=int(pack["id"]),
                raw_segment_id=segment.raw_id,
                rule=rule,
                delta=weight,
                evidence=evidence,
                tripped=False,
            )

        self.history.append(segment)
        result.running_score = self.running_score

        has_substance = bool(self._epoch_kinds & SUBSTANCE_KINDS)
        score_ready = self.running_score >= threshold and bool(hits)
        substance_ok = (not require_substance) or has_substance
        if score_ready and substance_ok:
            result.tripped = True
            # mark last hit as trip
            if result.deltas:
                result.deltas[-1]["tripped"] = 1
                self._mark_last_trip(segment.raw_id)
            review = create_review_prompt(
                self.db,
                pack_id=int(pack["id"]),
                running_score=self.running_score,
                trip_raw_segment_id=segment.raw_id,
                window_segments=list(self.history),
                evidence_hits=list(self._epoch_hits),
                settings=settings,
            )
            result.review = review
            self.awaiting_review = True
            self._pending_review_id = int(review["id"])
            result.awaiting_review = True

        return result

    def _eval_rule(
        self,
        kind: str,
        params: Dict[str, Any],
        segment: SegmentView,
        *,
        long_s: float,
        short_s: float,
    ) -> Optional[Dict[str, Any]]:
        if kind == "greeting_lexicon":
            hit = _phrase_hit(segment.text, list(params.get("phrases") or []))
            if hit:
                return {"matched": hit, "text_excerpt": segment.text[:120]}
            return None

        if kind == "tasking_lexicon":
            hit = _phrase_hit(segment.text, list(params.get("phrases") or []))
            if hit:
                return {"matched": hit, "text_excerpt": segment.text[:120]}
            return None

        if kind == "proper_noun_lexicon":
            hit = _phrase_hit(segment.text, list(params.get("phrases") or []))
            if hit:
                return {"matched": hit, "text_excerpt": segment.text[:120]}
            return None

        if kind == "backchannel_burst":
            max_chars = int(params.get("max_chars") or 24)
            text = (segment.text or "").strip()
            if len(text) > max_chars:
                return None
            hit = _phrase_hit(text, list(params.get("phrases") or []))
            if not hit:
                return None
            if params.get("after_long", True):
                if not self.history:
                    return None
                prev = self.history[-1]
                if prev.duration < long_s:
                    return None
            return {"matched": hit, "text_excerpt": text}

        if kind == "speaker_entry":
            min_stretch = int(params.get("min_prior_stretch") or 3)
            if len(self.history) < min_stretch:
                return None
            prior = self.history[-min_stretch:]
            if any(p.speaker_id == segment.speaker_id for p in prior):
                return None
            # all prior stretch same speaker, different from current
            if len({p.speaker_id for p in prior}) != 1:
                return None
            if prior[0].speaker_id == segment.speaker_id:
                return None
            return {
                "new_speaker": segment.speaker_name,
                "prior_speaker": prior[0].speaker_name,
                "prior_stretch": min_stretch,
            }

        if kind == "segment_length_flip":
            min_prior_long = int(params.get("min_prior_long") or 2)
            if segment.duration > short_s:
                return None
            if len(self.history) < min_prior_long:
                return None
            prior = self.history[-min_prior_long:]
            if not all(p.duration >= long_s for p in prior):
                return None
            return {
                "segment_duration": segment.duration,
                "prior_long_durations": [p.duration for p in prior],
            }

        return None

    def _persist_hit(
        self,
        *,
        pack_id: int,
        raw_segment_id: int,
        rule: Dict[str, Any],
        delta: float,
        evidence: Dict[str, Any],
        tripped: bool,
    ) -> None:
        with self.db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO p2_score_events
                    (pack_id, raw_segment_id, rule_id, rule_kind, delta,
                     running_score, evidence_json, tripped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pack_id,
                    raw_segment_id,
                    int(rule["id"]),
                    rule["kind"],
                    float(delta),
                    float(self.running_score),
                    json.dumps(evidence),
                    1 if tripped else 0,
                ),
            )
            conn.commit()

    def _mark_last_trip(self, raw_segment_id: int) -> None:
        with self.db.get_db() as conn:
            conn.execute(
                """
                UPDATE p2_score_events SET tripped = 1
                WHERE id = (
                    SELECT id FROM p2_score_events
                    WHERE raw_segment_id = ?
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (raw_segment_id,),
            )
            conn.commit()

    def on_review_decided(self, escalate: bool) -> None:
        """After internal evaluator decides.

        Escalate: latch off — do not keep checking for the rest of this Play.
        Decline: clear score/window and keep the filter armed for another trip.
        """
        self.running_score = 0.0
        self.awaiting_review = False
        self._pending_review_id = None
        self.history = []
        self._epoch_kinds = set()
        self._epoch_hits = []
        if escalate:
            self.escalated_latched = True
        else:
            self.escalated_latched = False


def score_segment(db: Any, scorer: P2Scorer, segment: SegmentView) -> ScoreResult:
    return scorer.observe(segment)


def list_score_events(db: Any, limit: int = 40) -> List[Dict[str, Any]]:
    """Recent filter factoids, chronological — used to rehydrate the P2 pane."""
    ensure_p2_tables(db)
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, raw_segment_id, rule_kind, delta, running_score,
                   evidence_json, tripped, created_at
            FROM p2_score_events
            ORDER BY id DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in reversed(rows):  # chronological for the UI
        d = {k: r[k] for k in r.keys()} if hasattr(r, "keys") else dict(r)
        try:
            d["evidence"] = json.loads(d.get("evidence_json") or "{}")
        except json.JSONDecodeError:
            d["evidence"] = {}
        out.append(d)
    return out

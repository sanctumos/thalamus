#!/usr/bin/env python3
"""
Play orchestrator — one thread per layer: P0 ingest, P1 refine, P2 worker.

P0 (ingest thread): intake + non-LLM P2 filter scoring only — never an LLM call.
P1 (refine thread): light ASR cleanup, Venice-bound, may lag under speed.
P2 (worker thread): evaluator decisions + breaker + refine passes, fed by a
queue so no P2 LLM latency ever touches P0 intake or P1 cleanup.
Stop is cooperative and must return quickly (interruptible waits; one group per refine).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import logging
import queue
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .db_util import ingest_event, open_db, reset_db, snapshot
from .llm import set_secrets_db_path
from .p2_filters.breaker import TopicBreaker, get_topic_state, start_topic_state
from .p2_filters.evaluator import evaluate_review
from .p2_filters.refine_engine import list_refine_passes, run_refine_pass
from .p2_filters.review import list_reviews
from .p2_filters.scorer import P2Scorer, SegmentView, list_score_events
from .p2_filters.store import get_settings as p2_get_settings
from .refine import refine_unrefined
from .streamer import stream_events
from .time_simulator import TimeSimulator

logger = logging.getLogger(__name__)

EventHandler = Callable[[Dict[str, Any]], None]


class Orchestrator:
    def __init__(
        self,
        db_path: Path,
        data_log: Optional[Path] = None,
        speed: float = 1.0,
        force_stub: bool = False,
        conversation_id: Optional[str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.data_log = data_log
        self.conversation_id = conversation_id or ""
        self.speed = float(speed) if speed else 1.0
        self.force_stub = force_stub
        self._ingest_thread: Optional[threading.Thread] = None
        self._refine_thread: Optional[threading.Thread] = None
        self._p2_thread: Optional[threading.Thread] = None
        self._p2_queue: "queue.Queue[tuple]" = queue.Queue()
        self._stop = threading.Event()
        self._ingest_done = threading.Event()
        self._handlers: List[EventHandler] = []
        self._lock = threading.Lock()
        self._db_write_lock = threading.Lock()
        self._run_id = 0
        self.state = "idle"
        self.llm_mode = "unknown"
        self.db = None
        self.p2_scorer: Optional[P2Scorer] = None
        # P2 refine mode (post-escalate)
        self.p2_mode = False
        self.p2_breaker: Optional[TopicBreaker] = None
        self._p2_anchor_raw_id = 0
        self._p2_turns_since_pass = 0
        self._p2_pending_batch: List[str] = []
        self._p2_latest_raw_id = 0

    def set_conversation(self, conversation_id: str, data_log: Path) -> None:
        """Select which NDJSON feed Play will stream (must not be mid-play)."""
        self.conversation_id = conversation_id
        self.data_log = Path(data_log)

    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def _emit(self, event: Dict[str, Any]) -> None:
        for h in list(self._handlers):
            try:
                h(event)
            except Exception:
                logger.exception("event handler failed")

    def ensure_db(self):
        """Attach existing demo DB without wiping (reload / stop / status)."""
        if self.db is None:
            self.db = open_db(self.db_path)
            set_secrets_db_path(self.db_path)
            self.p2_scorer = P2Scorer(self.db)
        return self.db

    def status(self) -> Dict[str, Any]:
        self.ensure_db()
        snap = snapshot(self.db) if self.db else {
            "raw_segments": [],
            "refined_segments": [],
            "segment_usage": [],
        }
        p2 = {
            "running_score": self.p2_scorer.running_score if self.p2_scorer else 0,
            "awaiting_review": bool(
                self.p2_scorer and self.p2_scorer.awaiting_review
            ),
            "escalated_latched": bool(
                self.p2_scorer and self.p2_scorer.escalated_latched
            ),
            "mode": self.p2_mode,
            "breaker_state": (self.p2_breaker.state if self.p2_breaker else None),
            "topic_score": (
                self.p2_breaker.last_topic_score if self.p2_breaker else None
            ),
        }
        p1_pending = 0
        if self.db is not None:
            try:
                p1_pending = int(self.db.count_unrefined_segments())
            except Exception:
                logger.exception("p1 pending count failed")
        # Rehydrate detail from DB so the P2 pane survives page refresh
        # (and server restart) — runtime rows live until next Play/Reset.
        if self.db is not None:
            try:
                hits = list_score_events(self.db, limit=40)
                reviews = list_reviews(self.db)
                latest_review = reviews[0] if reviews else None
                if latest_review:
                    note = latest_review.get("decision_note") or ""
                    m = re.match(r"^\[([^\]]+)\]\s*(.*)$", note, re.S)
                    if m:
                        latest_review["evaluator_mode"] = m.group(1)
                        latest_review["evaluator_rationale"] = m.group(2).strip()
                    latest_review["escalate"] = (
                        latest_review.get("status") == "escalated"
                    )
                topic = get_topic_state(self.db)
                passes = list_refine_passes(self.db, limit=6)
                p2["hits"] = hits
                p2["review"] = latest_review
                p2["refine_passes"] = list(reversed(passes))  # chronological
                if topic:
                    p2["mode"] = True
                    if not p2["breaker_state"]:
                        p2["breaker_state"] = topic.get("state")
                    try:
                        s = p2_get_settings(self.db)
                        p2["breaker"] = {
                            "state": topic.get("state"),
                            "on_streak": int(topic.get("on_streak") or 0),
                            "off_streak": int(topic.get("off_streak") or 0),
                            "on_score": float(s["p2_breaker_on_score_f"]),
                            "off_score": float(s["p2_breaker_off_score_f"]),
                            "on_need": int(s["p2_breaker_on_streak_i"]),
                            "off_need": int(s["p2_breaker_off_streak_i"]),
                        }
                    except Exception:
                        logger.exception("breaker settings hydration failed")
                if latest_review and latest_review.get("status") == "escalated":
                    p2["escalated_latched"] = True
                if latest_review and latest_review.get("status") == "pending":
                    p2["awaiting_review"] = True
                if not p2["running_score"] and hits:
                    if latest_review and latest_review.get("status") == "pending":
                        p2["running_score"] = hits[-1].get("running_score") or 0
            except Exception:
                logger.exception("p2 status hydration failed")
        return {
            "state": self.state,
            "llm_mode": self.llm_mode,
            "force_stub": self.force_stub,
            "speed": self.speed,
            "conversation_id": self.conversation_id,
            "data_log": str(self.data_log) if self.data_log else None,
            "ingest_done": self._ingest_done.is_set(),
            "counts": {
                "raw": len(snap["raw_segments"]),
                "refined": len(snap["refined_segments"]),
                "usage": len(snap["segment_usage"]),
                "p1_pending": p1_pending,
            },
            "p2": p2,
            "snapshot": snap,
        }

    def reset(self) -> Dict[str, Any]:
        self.stop()
        self.db = reset_db(self.db_path)
        set_secrets_db_path(self.db_path)
        self.p2_scorer = P2Scorer(self.db)
        self.p2_mode = False
        self.p2_breaker = None
        self._p2_anchor_raw_id = 0
        self._p2_turns_since_pass = 0
        self._p2_pending_batch = []
        self._p2_latest_raw_id = 0
        self._fresh_p2_queue()
        self.state = "idle"
        self.llm_mode = "unknown"
        self.speed = 1.0
        self._ingest_done.clear()
        self._emit({"type": "console", "level": "INFO", "message": "DB reset"})
        self._emit({"type": "snapshot", **snapshot(self.db)})
        return self.status()

    def _fresh_p2_queue(self) -> None:
        # New instance per run: a stale P2 worker from a prior Play holds the
        # old queue object and can never consume the new run's work items.
        self._p2_queue = queue.Queue()

    def stop(self) -> None:
        """Request halt. Returns quickly; does not wait on Venice HTTP."""
        self._stop.set()
        if self.state not in ("error", "idle"):
            self.state = "stopped"
        self._emit(
            {
                "type": "console",
                "level": "WARN",
                "message": "Stop — ingest/refine will halt (Venice call may finish one in-flight)",
            }
        )
        for t in (self._ingest_thread, self._refine_thread, self._p2_thread):
            if t and t.is_alive():
                t.join(timeout=0.5)
        if not (self._ingest_thread and self._ingest_thread.is_alive()):
            self._ingest_thread = None
        if not (self._refine_thread and self._refine_thread.is_alive()):
            self._refine_thread = None
        if not (self._p2_thread and self._p2_thread.is_alive()):
            self._p2_thread = None
        # Keep _stop set so any orphaned worker still exits; Play clears it.
        if self.db is not None:
            self._emit({"type": "snapshot", **snapshot(self.db)})

    def play(self) -> Dict[str, Any]:
        with self._lock:
            if self.state == "playing" and (
                (self._ingest_thread and self._ingest_thread.is_alive())
                or (self._refine_thread and self._refine_thread.is_alive())
                or (self._p2_thread and self._p2_thread.is_alive())
            ):
                return self.status()
            self.stop()
            self._run_id += 1
            run_id = self._run_id
            self.db = reset_db(self.db_path)
            set_secrets_db_path(self.db_path)
            self.p2_scorer = P2Scorer(self.db)
            self.p2_mode = False
            self.p2_breaker = None
            self._p2_anchor_raw_id = 0
            self._p2_turns_since_pass = 0
            self._p2_pending_batch = []
            self._p2_latest_raw_id = 0
            self._fresh_p2_queue()
            self.state = "playing"
            self._ingest_done.clear()
            self._stop.clear()
            self._ingest_thread = threading.Thread(
                target=self._run_ingest,
                args=(run_id,),
                daemon=True,
                name="web-replay-ingest",
            )
            self._refine_thread = threading.Thread(
                target=self._run_refine,
                args=(run_id,),
                daemon=True,
                name="web-replay-refine",
            )
            self._p2_thread = threading.Thread(
                target=self._run_p2,
                args=(run_id,),
                daemon=True,
                name="web-replay-p2",
            )
            self._ingest_thread.start()
            self._refine_thread.start()
            self._p2_thread.start()
        self._emit(
            {
                "type": "console",
                "level": "INFO",
                "message": (
                    f"Play start conversation={self.conversation_id or '?'} "
                    f"speed={self.speed} "
                    "(ingest∥p1-refine∥p2 — intake never blocked on LLM)"
                ),
            }
        )
        return self.status()

    def _still_this_run(self, run_id: int) -> bool:
        return run_id == self._run_id and not self._stop.is_set()

    def _run_ingest(self, run_id: int) -> None:
        assert self.db is not None
        sim = TimeSimulator(speed=self.speed, stop_event=self._stop)

        def on_wait(waited: float, ts: str) -> None:
            self._emit(
                {
                    "type": "console",
                    "level": "INFO",
                    "message": f"time-sim wait {waited:.2f}s before {ts}",
                }
            )

        try:
            for event in stream_events(sim, path=self.data_log, on_wait=on_wait):
                if not self._still_this_run(run_id):
                    if self.state != "error":
                        self.state = "stopped"
                    self._emit(
                        {"type": "console", "level": "WARN", "message": "Play stopped"}
                    )
                    return
                with self._db_write_lock:
                    if not self._still_this_run(run_id):
                        return
                    raw_ids = ingest_event(self.db, event)
                    snap_raw = snapshot(self.db)["raw_segments"]
                    p2_results = []
                    segs = event.get("segments") or []
                    if self.p2_scorer and raw_ids and len(segs) == len(raw_ids):
                        for rid, seg in zip(raw_ids, segs):
                            view = SegmentView(
                                raw_id=int(rid),
                                speaker_id=int(seg.get("speaker_id") or 0),
                                speaker_name=str(seg.get("speaker") or "SPEAKER"),
                                text=str(seg.get("text") or ""),
                                start_time=float(seg.get("start") or 0),
                                end_time=float(seg.get("end") or 0),
                            )
                            p2_results.append(self.p2_scorer.observe(view))
                    # P2 refine mode: batch turns for breaker + cadence.
                    # Batching starts at TRIP (awaiting_review), not at
                    # escalation — the evaluator decides asynchronously on the
                    # P2 thread, and turns spoken during evaluation belong to
                    # the post-trip conversation. A decline discards the
                    # pending batch; FIFO queue order guarantees any tick
                    # enqueued here is processed after the evaluate decision.
                    p2_collecting = self.p2_mode or bool(
                        self.p2_scorer and self.p2_scorer.awaiting_review
                    )
                    if p2_collecting and raw_ids and segs:
                        self._p2_latest_raw_id = max(int(r) for r in raw_ids)
                        for rid, seg in zip(raw_ids, segs):
                            self._p2_pending_batch.append(str(seg.get("text") or ""))
                            self._p2_turns_since_pass += 1
                        settings = p2_get_settings(self.db)
                        every = int(settings["p2_refine_every_turns_i"])
                        if self._p2_turns_since_pass >= every:
                            batch_text = " ".join(self._p2_pending_batch)
                            self._p2_pending_batch = []
                            self._p2_turns_since_pass = 0
                            self._p2_queue.put(
                                ("tick", batch_text, int(self._p2_latest_raw_id))
                            )
                    try:
                        p1_pending = int(self.db.count_unrefined_segments())
                    except Exception:
                        p1_pending = None
                for rid in raw_ids:
                    row = next((r for r in snap_raw if r["id"] == rid), None)
                    if row:
                        self._emit({"type": "raw", "row": row})
                if p1_pending is not None:
                    self._emit({"type": "p1_pending", "pending": p1_pending})
                for pr in p2_results:
                    for hit in pr.deltas:
                        self._emit(
                            {
                                "type": "p2_hit",
                                "rule_kind": hit.get("rule_kind"),
                                "delta": hit.get("delta"),
                                "running_score": hit.get("running_score"),
                                "evidence": hit.get("evidence"),
                            }
                        )
                    if pr.tripped:
                        self._emit(
                            {
                                "type": "p2_trip",
                                "running_score": pr.running_score,
                                "review_id": (pr.review or {}).get("id"),
                            }
                        )
                        self._emit(
                            {
                                "type": "console",
                                "level": "WARN",
                                "message": (
                                    f"P2 trip score={pr.running_score:.1f} — "
                                    "handing factoids to internal evaluator"
                                ),
                            }
                        )
                    if pr.review:
                        review = pr.review
                        self._emit({"type": "p2_review", "review": review})
                        # Auto-evaluate (not HITL) unless doctor disabled it.
                        # The evaluator is an LLM call — it runs on the P2
                        # worker thread, never inline on P0 intake.
                        settings = p2_get_settings(self.db)
                        if settings.get("p2_auto_evaluate_b", True):
                            self._p2_queue.put(("evaluate", int(review["id"])))
            if self._still_this_run(run_id):
                self._emit(
                    {
                        "type": "console",
                        "level": "INFO",
                        "message": "Intake complete — refine may still be catching up",
                    }
                )
        except Exception as e:
            if run_id == self._run_id:
                self.state = "error"
                logger.exception("ingest failed")
                self._emit({"type": "console", "level": "ERROR", "message": str(e)})
        finally:
            self._ingest_done.set()

    def _p2_evaluate(self, review_id: int) -> None:
        """Run the internal evaluator on the P2 thread (LLM off P0/P1)."""
        if self.db is None:
            return
        try:
            decided = evaluate_review(self.db, review_id)
        except Exception as e:
            logger.exception("P2 evaluate failed")
            self._emit(
                {
                    "type": "console",
                    "level": "ERROR",
                    "message": f"P2 evaluator failed: {e}",
                }
            )
            return
        escalate = bool(
            decided.get("escalate")
            if "escalate" in decided
            else decided.get("status") == "escalated"
        )
        if self.p2_scorer is not None:
            self.p2_scorer.on_review_decided(escalate)
        if not escalate:
            # Declined — turns batched during evaluation are not P2 material.
            with self._db_write_lock:
                self._p2_pending_batch = []
                self._p2_turns_since_pass = 0
        self._emit(
            {
                "type": "p2_review",
                "review": decided,
                "decided": True,
                "escalate": escalate,
            }
        )
        self._emit(
            {
                "type": "console",
                "level": "P2",
                "message": (
                    f"Evaluator "
                    f"{decided.get('evaluator_mode') or '?'} → "
                    f"{'ESCALATE' if escalate else 'DECLINE'} — "
                    f"{(decided.get('evaluator_rationale') or decided.get('decision_note') or '')[:180]}"
                ),
            }
        )
        if escalate:
            self._emit(
                {
                    "type": "console",
                    "level": "INFO",
                    "message": (
                        "P2 filter latched off for this Play "
                        "(successful escalate — no further trips)"
                    ),
                }
            )
            self._start_p2_mode(decided)

    def _run_p2(self, run_id: int) -> None:
        """P2 layer thread: evaluator decisions + breaker/refine ticks.

        Fed by a queue from the ingest thread. All P2 LLM latency lives here
        so it never blocks P0 intake or P1 cleanup.
        """
        assert self.db is not None

        def should_stop() -> bool:
            return not self._still_this_run(run_id)

        while True:
            if should_stop():
                return
            try:
                item = self._p2_queue.get(timeout=0.1)
            except queue.Empty:
                # Ingest finished and no P2 work remains — nothing more can
                # be enqueued (trips/ticks only originate from live ingest).
                if self._ingest_done.is_set() and self._p2_queue.empty():
                    return
                continue
            if should_stop():
                return
            kind = item[0]
            try:
                if kind == "evaluate":
                    self._p2_evaluate(int(item[1]))
                elif kind == "tick":
                    for ev in self._p2_tick(str(item[1]), int(item[2])):
                        self._emit(ev)
            except Exception as e:
                logger.exception("P2 worker failed on %s", kind)
                self._emit(
                    {
                        "type": "console",
                        "level": "ERROR",
                        "message": f"P2 {kind} failed: {e}",
                    }
                )

    def _start_p2_mode(self, decided_review: Dict[str, Any]) -> None:
        """Enter P2 refine mode after successful escalate."""
        if self.db is None or self.p2_mode:
            return
        settings = p2_get_settings(self.db)
        window_ids = decided_review.get("window_raw_ids") or []
        anchor = int(
            window_ids[0]
            if window_ids
            else (decided_review.get("trip_raw_segment_id") or 0)
        )
        window_text = "\n".join(
            f"[{s.get('speaker_name') or '?'}] {(s.get('text') or '').strip()}"
            for s in (decided_review.get("window_segments") or [])
        )
        start_topic_state(
            self.db,
            home_text=window_text,
            project_card=settings["p2_project_card"],
            anchor_raw_id=anchor,
            # First pass covers the whole trip window; later passes are deltas.
            last_pass_raw_id=anchor - 1,
        )
        self.p2_mode = True
        self._p2_anchor_raw_id = anchor
        # Keep _p2_turns_since_pass / _p2_pending_batch: turns batched while
        # the evaluator was deciding count toward the first pass cadence.
        self.p2_breaker = TopicBreaker(self.db)
        self._emit(
            {
                "type": "p2_breaker",
                "state": "on",
                "topic_score": None,
                "reason": "P2 refine mode started (escalate)",
            }
        )
        self._emit(
            {
                "type": "console",
                "level": "P2",
                "message": (
                    f"P2 refine mode ON — every {settings['p2_refine_every_turns_i']} turns, "
                    "home-topic breaker armed"
                ),
            }
        )

    def _p2_tick(self, batch_text: str, latest_raw_id: int) -> List[Dict[str, Any]]:
        """Every-N-turns: breaker score, maybe flip, maybe refine pass."""
        events: List[Dict[str, Any]] = []
        if not self.p2_mode or self.db is None:
            return events
        if self.p2_breaker is None:
            self.p2_breaker = TopicBreaker(self.db)

        br = self.p2_breaker.observe_batch(batch_text)
        if br.get("topic_score") is not None:
            events.append(
                {
                    "type": "p2_breaker",
                    "state": br["state"],
                    "topic_score": br["topic_score"],
                    "flipped": br.get("flipped", False),
                    "reason": br.get("reason") or "",
                    "detail": br.get("detail") or {},
                    "on_streak": br.get("on_streak"),
                    "off_streak": br.get("off_streak"),
                    "on_score": br.get("on_score"),
                    "off_score": br.get("off_score"),
                    "on_need": br.get("on_need"),
                    "off_need": br.get("off_need"),
                }
            )
        if br.get("flipped"):
            events.append(
                {
                    "type": "console",
                    "level": "P2",
                    "message": f"P2 breaker → {br['state'].upper()} ({br.get('reason') or ''})",
                }
            )

        if not self.p2_breaker.is_on:
            # Off-topic stretch: advance coverage so it is never refined into
            # the pane when the breaker flips back on.
            if latest_raw_id:
                self.p2_breaker.mark_pass(latest_raw_id)
                for ev in events:
                    if ev.get("type") == "p2_breaker":
                        ev["skipped"] = True
                        ev["covered_through_raw_id"] = int(latest_raw_id)
            return events

        settings = p2_get_settings(self.db)
        try:
            row = run_refine_pass(
                self.db,
                anchor_raw_id=self._p2_anchor_raw_id,
                after_raw_id=self.p2_breaker.last_pass_raw_id,
                topic_score=br.get("topic_score"),
                home_terms=self.p2_breaker.home_terms,
                force_stub=self.force_stub,
            )
        except Exception as e:
            logger.exception("P2 refine pass failed")
            events.append(
                {
                    "type": "console",
                    "level": "ERROR",
                    "message": f"P2 refine pass failed: {e}",
                }
            )
            return events

        if row.get("skipped"):
            return events

        self.p2_breaker.mark_pass(int(row.get("window_end_raw_id") or 0))
        # Home topic drifts only on successful on-topic refine passes
        self.p2_breaker.update_home(
            str(row.get("text") or ""), settings["p2_project_card"]
        )
        events.append(
            {
                "type": "p2_refine",
                "row": {
                    "id": row.get("id"),
                    "pass_index": row.get("pass_index"),
                    "mode": row.get("mode"),
                    "text": row.get("text"),
                    "topic_score": row.get("topic_score"),
                    "window_start_raw_id": row.get("window_start_raw_id"),
                    "window_end_raw_id": row.get("window_end_raw_id"),
                },
            }
        )
        events.append(
            {
                "type": "console",
                "level": "P2",
                "message": (
                    f"P2 refine pass #{row.get('pass_index')} mode={row.get('mode')} "
                    f"topic={br.get('topic_score')}"
                ),
            }
        )
        return events

    def _emit_refine_results(self, created: List[Dict[str, Any]]) -> None:
        if not created:
            return
        with self._db_write_lock:
            usage = snapshot(self.db)["segment_usage"]
        created_ids = {c["id"] for c in created}
        for c in created:
            self.llm_mode = c.get("mode", self.llm_mode)
            self._emit({"type": "refined", "row": c})
            self._emit(
                {
                    "type": "console",
                    "level": "INFO",
                    "message": f"refine mode={c.get('mode')} id={c.get('id')}",
                }
            )
        for u in usage:
            if u["refined_segment_id"] in created_ids:
                self._emit({"type": "provenance", "row": u})

    def _run_refine(self, run_id: int) -> None:
        """P1 layer thread — light ASR cleanup only. P2 has its own worker."""
        assert self.db is not None

        def should_stop() -> bool:
            return not self._still_this_run(run_id)

        try:
            while self._still_this_run(run_id):
                if should_stop():
                    break
                created = refine_unrefined(
                    self.db,
                    force_stub=self.force_stub,
                    should_stop=should_stop,
                    max_groups=1,
                    lock=self._db_write_lock,
                )
                if should_stop():
                    break
                self._emit_refine_results(created)
                if created:
                    try:
                        with self._db_write_lock:
                            pending = int(self.db.count_unrefined_segments())
                        self._emit({"type": "p1_pending", "pending": pending})
                    except Exception:
                        logger.exception("p1 pending emit failed")
                    continue  # drain backlog without sleeping
                if self._ingest_done.is_set():
                    if should_stop():
                        break
                    created = refine_unrefined(
                        self.db,
                        force_stub=self.force_stub,
                        should_stop=should_stop,
                        max_groups=1,
                        lock=self._db_write_lock,
                    )
                    if should_stop():
                        break
                    self._emit_refine_results(created)
                    if not created:
                        break
                    continue
                self._stop.wait(0.05)
            if not self._still_this_run(run_id):
                if self.state != "error" and run_id == self._run_id:
                    self.state = "stopped"
                return
            if self.state != "error" and run_id == self._run_id:
                self.state = "done"
                self._emit(
                    {"type": "console", "level": "INFO", "message": "Play complete"}
                )
                with self._db_write_lock:
                    snap = snapshot(self.db)
                self._emit({"type": "snapshot", **snap})
        except Exception as e:
            if run_id == self._run_id:
                self.state = "error"
                logger.exception("refine failed")
                self._emit({"type": "console", "level": "ERROR", "message": str(e)})

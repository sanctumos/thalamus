# Web Omi streaming replay (Path A)

Browser-visible **streaming** Thalamus layers driven by selectable Cochlea NDJSON feeds and the original **time simulator** (`log_timestamp` deltas).

PRD: Tasks [Doc #1045](https://tasks.decisionsciencecorp.com/admin/doc.php?id=1045) · list **Web Omi replay (streaming)**.

## Conversations

Header **Conversation** dropdown picks which NDJSON feed Play streams. Catalog: `conversations/catalog.json`.

| Id | Source |
|----|--------|
| `cochlea-10min-committee` | `examples/raw_data_log.json` (default) |
| `vertex-security-pilot-2026-08-03` | Omi `13041a6c-…` Aug 3 2026 ~16:24 CDT → Cochlea NDJSON |
| `omi-live-webhook-mortgage-2026-08-11` | **P0 raw** realtime webhook (mortgage → Jim handoff) |

Play POST may include `conversation_id`. `GET /api/conversations` lists options.

## P2 filter + internal evaluator + Thalamus doctor

Non-LLM evidence accumulates while Play ingests. When score crosses `trip_threshold`, factoids are enumerated on a **review** packet and SSE emits `p2_hit` / `p2_trip` / `p2_review`. An **internal Thalamus evaluation agent** (not Sanctum/Letta) then auto-decides escalate vs decline — **not** a human-in-the-loop click. That gate still does **not** run the future P2 conversational refine LLM.

| Layer | Role |
|-------|------|
| P0 | Raw Cochlea / webhook |
| P1 | Light ASR cleanup (today’s Venice same-speaker refine) |
| P2 filter | Cheap accumulating rules (no LLM) |
| Evaluator | Internal agent: window + factoids + project card → escalate Y/N |
| P2 refine | Future: conversation-aware (see `p2_filters/gold_mortgage_jim_2026-08-11.md`) |

**Doctor API** (open in demos; later a scoped job bot like Q/Wren):

| Method | Path |
|--------|------|
| GET/PATCH | `/api/doctor/settings` |
| GET | `/api/doctor/filter-packs` |
| GET/PATCH | `/api/doctor/filter-packs/<id>` |
| PATCH | `/api/doctor/filter-rules/<id>` |
| POST | `/api/doctor/seed` |
| GET | `/api/doctor/reviews?status=pending` |
| POST | `/api/doctor/reviews/<id>/evaluate` | re-run internal evaluator |
| POST | `/api/doctor/reviews/<id>/decide` | doctor override only |

Settings of note: `p2_evaluator_mode` (`auto`\|`venice`\|`heuristic`), `p2_evaluator_model`, `p2_project_card`, `p2_auto_evaluate` (default true).

Config (`filter_packs` / `filter_rules` / `thalamus_settings`) survives Play/Reset like `app_secrets`. Runtime `p2_score_events` / `p2_review_prompts` wipe on Play/Reset.

Default pack: `video_to_dialog_handoff` (greeting, speaker_entry, segment_length_flip, tasking, proper nouns, backchannel). Setting `enrichment_gate_enabled` defaults **false** until the P2 LLM path ships.

## Run (local / NewDev)

```bash
cd examples/web_replay
pip install -r requirements.txt
./run.sh
# open http://HOST:8787/
```

Env:

| Var | Default | Meaning |
|-----|---------|---------|
| `THALAMUS_WEB_PORT` | `8787` | Bind port |
| `THALAMUS_WEB_SPEED` | `1.0` | Initial speed only — Play uses the UI control |
| `THALAMUS_WEB_FORCE_STUB` | `1` | Initial refine mode only — Play uses the UI Refine select |
| `THALAMUS_WEB_CONVERSATION` | catalog default | Boot `conversation_id` |
| `THALAMUS_WEB_DATA_LOG` | catalog path | Override NDJSON path (skips catalog resolve) |
| `VENICE_API_KEY` | — | Optional bootstrap only; prefer Settings → save into `app_secrets` |

**Web controls (source of truth for a Play run):** Conversation, Speed (`1.0` = real-time), Refine (Stub / Venice), Play / Reset / Stop.

**Settings:** Venice API key is stored in the demo SQLite table `app_secrets` (password field in the UI). Play/Reset wipe replay tables only — the key survives. No `~/.ssh/*.pass` for this app.

Access is **open during dev**.

## Tests (≥90% gate)

```bash
./run_slice_tests.sh all
./run_slice_tests.sh 1   # time sim + streamer
```

## Model lab (reusable)

```bash
# Full paid ladder → refreshes lab_out/refine_model_whitelist.json (≥85% pass)
cd examples && PYTHONPATH=. python3 -m web_replay.lab_model_ladder

# Offline whitelist schema + Settings API; network catalog check if key present
pytest web_replay/tests/test_model_whitelist.py -v

# Opt-in paid re-run via pytest
VENICE_LAB=1 pytest web_replay/tests/test_model_whitelist.py -v -m slow
```

Settings → **Refine model** dropdown is built from the whitelist (lab score + `$`/`$$`/`$$$` relative cost).

Play **resets** the demo DB, then releases NDJSON events only after each `log_timestamp` wait — not a batch dump. Raw pane ticks as events release; refined pane fills via Venice or stub.

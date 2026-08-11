# Web Omi streaming replay (Path A)

Browser-visible **streaming** Thalamus layers driven by `raw_data_log.json` and the original **time simulator** (`log_timestamp` deltas).

PRD: Tasks [Doc #1045](https://tasks.decisionsciencecorp.com/admin/doc.php?id=1045) · list **Web Omi replay (streaming)**.

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
| `VENICE_API_KEY` | — | Optional bootstrap only; prefer Settings → save into `app_secrets` |

**Web controls (source of truth for a Play run):** Speed (`1.0` = real-time), Refine (Stub / Venice), Play / Reset / Stop.

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

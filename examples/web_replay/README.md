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
| `THALAMUS_WEB_SPEED` | `1.0` | Time-sim speed (UI Play can override) |
| `THALAMUS_WEB_FORCE_STUB` | `1` | Stub refine (set `0` + Venice key for live LLM) |
| `VENICE_API_KEY` | from `~/.ssh/venice.pass` | Venice inference |

Access is **open during dev**.

## Tests (≥90% gate)

```bash
./run_slice_tests.sh all
./run_slice_tests.sh 1   # time sim + streamer
```

## Play semantics

Play **resets** the demo DB, then releases NDJSON events only after each `log_timestamp` wait — not a batch dump. Raw pane ticks as events release; refined pane fills via Venice or stub.

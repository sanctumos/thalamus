#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EXAMPLES="$(cd "$ROOT/.." && pwd)"
cd "$EXAMPLES"

# Secrets (Venice key) live in the demo SQLite app_secrets table — set via web Settings.
# Do not load ~/.ssh/*.pass here.

export THALAMUS_WEB_DATA="${THALAMUS_WEB_DATA:-$ROOT/data}"
# Server-side defaults only — Play speed / refine mode come from the web UI.
export THALAMUS_WEB_SPEED="${THALAMUS_WEB_SPEED:-1.0}"
export THALAMUS_WEB_HOST="${THALAMUS_WEB_HOST:-0.0.0.0}"
export THALAMUS_WEB_PORT="${THALAMUS_WEB_PORT:-8787}"
export THALAMUS_WEB_FORCE_STUB="${THALAMUS_WEB_FORCE_STUB:-1}"
export PYTHONPATH="$EXAMPLES${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$THALAMUS_WEB_DATA"

REPO_ROOT="$(cd "$EXAMPLES/.." && pwd)"
PY=python3
if [[ -x "$REPO_ROOT/.venv/bin/python3" ]]; then
  PY="$REPO_ROOT/.venv/bin/python3"
elif [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PY="$ROOT/.venv/bin/python3"
fi
exec "$PY" -m web_replay.server

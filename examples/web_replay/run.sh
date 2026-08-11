#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EXAMPLES="$(cd "$ROOT/.." && pwd)"
cd "$EXAMPLES"

if [[ -f "${HOME}/.ssh/venice.pass" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${HOME}/.ssh/venice.pass"
  set +a
fi

export THALAMUS_WEB_DATA="${THALAMUS_WEB_DATA:-$ROOT/data}"
export THALAMUS_WEB_SPEED="${THALAMUS_WEB_SPEED:-1.0}"
export THALAMUS_WEB_HOST="${THALAMUS_WEB_HOST:-0.0.0.0}"
export THALAMUS_WEB_PORT="${THALAMUS_WEB_PORT:-8787}"
export THALAMUS_WEB_FORCE_STUB="${THALAMUS_WEB_FORCE_STUB:-1}"
export PYTHONPATH="$EXAMPLES${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$THALAMUS_WEB_DATA"
exec python3 -m web_replay.server

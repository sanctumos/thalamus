#!/usr/bin/env bash
# Coverage gate per slice — fail under 90% on that slice's package paths.
# Usage: ./run_slice_tests.sh 1|2|3|4|all
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EXAMPLES="$(cd "$ROOT/.." && pwd)"
cd "$EXAMPLES"
export PYTHONPATH="$EXAMPLES${PYTHONPATH:+:$PYTHONPATH}"

SLICE="${1:-all}"
COV_FAIL=90

run_cov() {
  local name="$1"
  shift
  python3 -m pytest "$@" \
    --cov-config="$ROOT/.coveragerc" \
    --cov-report=term-missing \
    --cov-fail-under="$COV_FAIL"
  echo "OK slice $name coverage ≥${COV_FAIL}%"
}

case "$SLICE" in
  1)
    # Time simulator + streamer only
    run_cov 1 \
      --cov=web_replay.time_simulator --cov=web_replay.streamer \
      web_replay/tests/test_time_sim_streamer.py
    ;;
  2)
    # DB + Play/Reset + SSE bus
    run_cov 2 \
      --cov=web_replay.db_util --cov=web_replay.orchestrator --cov=web_replay.server \
      web_replay/tests/test_api_orchestrator.py \
      -k "not venice and not call_text and not load_venice and not refine_empty"
    ;;
  3)
    # Venice refine + stub
    run_cov 3 \
      --cov=web_replay.llm --cov=web_replay.refine \
      web_replay/tests/test_api_orchestrator.py \
      -k "refine or stub or call_text or venice or load_venice or orchestrator_play"
    ;;
  4)
    run_cov 4 \
      --cov=web_replay \
      web_replay/tests/test_e2e_ui.py web_replay/tests/test_api_orchestrator.py
    ;;
  all)
    run_cov all --cov=web_replay web_replay/tests
    ;;
  *)
    echo "usage: $0 1|2|3|4|all" >&2
    exit 2
    ;;
esac

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# examples/ on path so `import web_replay` and `import database` work
EXAMPLES = Path(__file__).resolve().parents[2]
if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))


@pytest.fixture
def mini_log(tmp_path):
    p = tmp_path / "mini.json"
    lines = []
    for i, (ts, text) in enumerate(
        [
            ("2025-03-26T22:48:00.000000Z", "Hello there"),
            ("2025-03-26T22:48:00.500000Z", "Testing connection"),
        ]
    ):
        lines.append(
            json.dumps(
                {
                    "session_id": "test-session",
                    "log_timestamp": ts,
                    "segments": [
                        {
                            "text": text,
                            "speaker": "SPEAKER_0",
                            "speaker_id": 0,
                            "start": float(i),
                            "end": float(i) + 0.5,
                        }
                    ],
                }
            )
        )
    p.write_text("\n".join(lines), encoding="utf-8")
    return p

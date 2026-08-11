import sys
from pathlib import Path

# examples/ on path so `import web_replay` and `import database` work
EXAMPLES = Path(__file__).resolve().parents[2]
if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))

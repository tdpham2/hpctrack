"""Tiny deterministic demo, not an HPC or scientific validation."""

import json
import sys
from pathlib import Path

values = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps({"sum_of_squares": sum(value * value for value in values), "device": "demo-cpu"}))

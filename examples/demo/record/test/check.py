import json
import sys
from pathlib import Path

result = json.loads((Path(sys.argv[1]) / "result.json").read_text())
passed = result.get("device") == "demo-cpu"
if len(sys.argv) > 2:
    reference = json.loads(Path(sys.argv[2]).read_text())
    for key, entry in reference["metrics"].items():
        passed = passed and abs(result[key] - entry["value"]) <= entry["absolute_tolerance"]
print(
    json.dumps(
        {
            "passed": passed,
            "metrics": {"sum_of_squares": result["sum_of_squares"]},
            "messages": ["Simulated local workflow; no HPC accelerator verified"],
        }
    )
)
raise SystemExit(0 if passed else 1)

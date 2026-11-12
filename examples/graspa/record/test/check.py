"""gRASPA completion check; numerical results are diagnostics, not thresholds.

Uses only the standard library, including on the site's older system Python.
"""

import json
import math
import re
import sys
from pathlib import Path


def check(directory):
    def read(name):
        path = directory / name
        return path.read_text(errors="replace") if path.is_file() else ""

    output = read("graspa.stdout.log") + "\n" + read("graspa.stderr.log")
    required = (
        "INITIALIZATION PHASE ENDS",
        "PRODUCTION PHASE ENDS",
        "END OF PROGRAM!",
        "Total GPU Energy:",
    )
    messages = ["Missing completion evidence: " + text for text in required if text not in output]
    if re.search(r"CUDA Error:", output, re.IGNORECASE):
        messages.append("Application reported a CUDA error")
    passed = not messages
    metrics = {}

    def metric(name, pattern):
        matches = re.findall(pattern, output, re.DOTALL)
        try:
            value = float(matches[-1])
            if not math.isfinite(value):
                raise ValueError
            metrics[name] = value
        except (IndexError, ValueError):
            messages.append("Diagnostic unavailable or nonfinite: " + name)

    for name, section in (
        ("final_energy_internal", "FINAL STAGE"),
        ("energy_drift_internal", "ENERGY DRIFT (CPU FINAL - RUNNING FINAL)"),
        ("gpu_drift_internal", "GPU DRIFT (GPU FINAL - CPU FINAL)"),
    ):
        metric(name, r"\*\*\* " + re.escape(section) + r" \*\*\*[^*]*?Total Energy:\s+(\S+)")
    metric("runtime_seconds", r"Work took\s+(\S+)\s+seconds")
    metric(
        "co2_loading_molecules",
        r"LOADING: # MOLECULES\).*?COMPONENT \[\d+\] \(CO2\)\s+"
        r".*?Overall: Average:\s+([^,\s]+)",
    )
    messages.append("Completion check only; energy, loading and drift are informational.")
    return {"passed": passed, "metrics": metrics, "messages": messages}


if __name__ == "__main__":
    result = check(Path(sys.argv[1]))
    print(json.dumps(result, allow_nan=False))
    raise SystemExit(0 if result["passed"] else 1)

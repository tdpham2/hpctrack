"""MACE-Polar completion check; energy and dipole are diagnostics, not thresholds.

Uses only the standard library, including on the site's older system Python.
"""

import json
import math
import sys
from pathlib import Path


def check(directory):
    def read(name):
        path = directory / name
        return path.read_text(errors="replace") if path.is_file() else ""

    messages = []
    output = read("polar.stdout.log") + "\n" + read("polar.stderr.log")
    for text in ("Traceback", "CUDA error"):
        if text in output:
            messages.append("Application log contains: " + text)
    try:
        summary = json.loads(read("polar.json"))
    except ValueError:
        summary = None
        messages.append("Missing or unreadable polar.json")
    metrics = {}
    if isinstance(summary, dict):

        def number(value):
            return isinstance(value, (int, float)) and math.isfinite(value)

        if not number(summary.get("energy")):
            messages.append("Energy is missing or nonfinite")
        if summary.get("forces_finite") is not True or not number(summary.get("max_abs_force")):
            messages.append("Forces are missing or nonfinite")
        device = str(summary.get("device") or "")
        if not device or device.lower() == "cpu":
            messages.append("Calculation did not report a GPU device")
        charges = summary.get("charges")
        if not charges or not all(number(value) for value in charges):
            messages.append("Charges are missing or nonfinite")
        elif abs(sum(charges)) > 1e-3:
            messages.append(f"Charges sum to {sum(charges):.6f}, expected 0")
        dipole = summary.get("dipole") or []
        diagnostics = {
            "energy_ev": summary.get("energy"),
            "max_abs_force_ev_per_a": summary.get("max_abs_force"),
            "dipole_norm": math.sqrt(sum(value * value for value in dipole))
            if all(number(value) for value in dipole) and dipole
            else None,
            "runtime_seconds": summary.get("runtime_seconds"),
        }
        metrics = {name: float(value) for name, value in diagnostics.items() if number(value)}
    passed = not messages
    messages.append("Completion check only; energy, forces and dipole are informational.")
    return {"passed": passed, "metrics": metrics, "messages": messages}


if __name__ == "__main__":
    result = check(Path(sys.argv[1]))
    print(json.dumps(result, allow_nan=False))
    raise SystemExit(0 if result["passed"] else 1)

"""MACE-Polar single point on a gas-phase water dimer; writes polar.json for check.py."""

import json
import time
from importlib.metadata import version

import numpy as np
import torch
from ase import Atoms
from mace.calculators import mace_polar

# S22 water dimer geometry (Angstrom), no periodic cell, so the dipole is defined.
atoms = Atoms(
    "OH2OH2",
    positions=[
        (-1.551007, -0.114520, 0.000000),
        (-1.934259, 0.762503, 0.000000),
        (-0.599677, 0.040712, 0.000000),
        (1.350625, 0.111469, 0.000000),
        (1.680398, -0.373741, -0.758561),
        (1.680398, -0.373741, 0.758561),
    ],
)
atoms.info.update(charge=0, spin=1, external_field=[0.0, 0.0, 0.0])

start = time.perf_counter()
atoms.calc = mace_polar(model="polar-1-m", device="cuda", default_dtype="float64")
energy = atoms.get_potential_energy()
forces = atoms.get_forces()
runtime = time.perf_counter() - start
results = atoms.calc.results

summary = {
    "energy": float(energy),
    "max_abs_force": float(np.abs(forces).max()),
    "forces_finite": bool(np.isfinite(forces).all()),
    "charges": np.asarray(results["density_coefficients"])[:, 0].tolist(),
    "dipole": np.asarray(results["dipole"]).reshape(-1).tolist(),
    "device": torch.cuda.get_device_name(0),
    "runtime_seconds": runtime,
    "mace_version": version("mace-torch"),
    "torch_version": torch.__version__,
}
with open("polar.json", "w") as stream:
    json.dump(summary, stream, indent=2)
print(json.dumps(summary))

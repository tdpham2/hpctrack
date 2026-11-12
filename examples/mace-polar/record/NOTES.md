# MACE-Polar notes

## Environment

- Requires `uv` on the build host's `PATH` and network access during the build.
- `uv venv --python 3.12` uses a system or uv-managed Python; no site modules.
- PyTorch comes from PyPI as a CUDA wheel; the node's NVIDIA driver must support it.

## Build decisions

- `git` source pinned to tag `v0.3.17`; hpctrack resolves it to a commit and
  `build.sh` installs `mace-torch @ git+URL@COMMIT` directly, without a clone.
- MACE-Polar's long-range terms need `graph_electrostatics` `v0.4.4` from git.
- The `polar-1-m` checkpoint is downloaded at build time into `$PREFIX/cache`, so
  jobs set `XDG_CACHE_HOME=$PREFIX/cache` and need no internet.
- To use the install: `export XDG_CACHE_HOME=$PREFIX/cache; source $PREFIX/venv/bin/activate`.

## Failures and fixes

None recorded yet.

## Known issues

- `torch` is unpinned; in Nov 2026 uv resolved torch 2.15.0 with the CUDA 13 runtime,
  which needs NVIDIA driver >= 580. On older drivers, pin `torch` in `build.sh`.
- The upstream `mace-reforge` (v1.0) rewrite is expected to change checkpoint
  compatibility; revisit the pin then.
- Dipoles are only meaningful without periodic boundaries; the test uses a gas-phase dimer.

## Validation

Completion only: a GPU single point on a water dimer must produce finite energy
and forces and charges summing to the total charge (0). Energy, forces and dipole
are recorded as diagnostics; they are not compared against a reference.

## Change log

- Initial recipe: mace-torch `v0.3.17`, graph_electrostatics `v0.4.4`, `polar-1-m`.

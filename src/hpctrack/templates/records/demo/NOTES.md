# Deterministic local demonstration

## Environment

Python standard library and Bash on the local development machine. All evidence
is simulated. This record does not validate LAMMPS or an HPC accelerator.

## Build decisions

Copy an immutable snapshot of a small Python program into a fresh prefix.

## Failures and fixes

No known failures in the demonstration input.

## Known issues

No performance, MPI, GPU, or site compatibility claims are made.

## Validation

For input `[1, 2, 3, 4]`, the expected sum of squares is 30. The reference is
accepted separately, and a subsequent calculation must compare against it.

## Change log

- 2026-11-11 — local-development implementation — agent: created the isolated
  demonstration recipe, calculation, and checker.

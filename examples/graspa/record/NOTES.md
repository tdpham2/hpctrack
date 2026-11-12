# gRASPA on Polaris: installation record

## Environment

Fill in the login node, programming environment, compiler and module versions
observed when this record is prepared. Observations on a login node do not
establish compute-node compatibility or site acceptance.

## Build decisions

Capture the configured working tree, including dirty and untracked files and
install.sh; *.o and *.x are excluded. install.sh runs unchanged in a fresh
working copy, so its removal of old artifacts is confined to that copy. The
wrapper checks the executable before installing it as PREFIX/bin/nvc_main.x.
Build metadata records each captured source file's SHA-256.

## Failures and fixes

None recorded yet. Use `hpctrack sw note` to append build attempts and fixes.

## Known issues

install.sh does not fail immediately on every command error; the wrapper checks
the final executable instead.

## Validation

The packaged input is a reduced CALF-20 CO2 isotherm case: initialization and
production cycles are 5,000 each, equilibration is zero and RandomSeed is 0.
Completion validation passes when the scheduler exit status is zero, both
phase-end markers and final program completion appear, GPU energy output is
present, and no CUDA error is reported. Energy, loading, drift and runtime are
recorded as diagnostics only. A passing build is validated, not scientifically
reference-verified.

## Change log

- Created from the packaged hpctrack gRASPA template.

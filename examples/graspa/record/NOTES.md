# gRASPA personal installation template

## Environment

This public template targets native PBS with PrgEnv-nvidia. It contains no
captured site results. Record actual environment observations in the private copy.

## Build decisions

Set the absolute path to the user's source directory containing install.sh.
Capture modified and untracked source files, excluding *.o and *.x. Run install.sh
unchanged in a writable build copy and install nvc_main.x under PREFIX/bin.
Retain the snapshot, file paths and content hashes in private state.

## Failures and fixes

No live build or GPU validation is represented by this template. The wrapper
checks script exit status and the newly built executable. Preserve original
source files and record any interventions here in the private record.

## Known issues

Replace configuration placeholders and supply a small user-owned input before
running this template. Completion validation does not establish scientific
agreement or numerical accuracy. There is no site-verification approval gate.

## Validation

Use one node, one GPU process and a 900-second walltime within the user's approved
allocation. Copy a small complete calculation into test/input; do not include
historical outputs or restart files. The checker requires successful scheduler
completion, both phase-end markers, final program completion, GPU energy output
and no reported CUDA Error. Numerical values are informational diagnostics.

## Change log

- Added a public template with placeholder configuration and no scientific input
  dataset. Tests use explicitly synthetic output. Actual build/validation evidence
  belongs in the user's private record repository.

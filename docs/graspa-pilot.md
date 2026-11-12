# Track a personal gRASPA installation

Use hpctrack to capture your modified code, build it and validate a small
calculation. The public example uses native PBS from an existing Polaris session.
It contains placeholders and no scientific input dataset. Keep actual machine
configuration, source paths and results in a separate private records repository.

## Set up private records

Install hpctrack with Python 3.10+ as described in the README. Choose a private
Git repository for `project_root`; it must be separate from the public tool
checkout. For example, replace `/path/to/private-records` below with your path:

```sh
mkdir -p /path/to/private-records
git -C /path/to/private-records init
cp config/polaris-local.example.yaml /path/to/private-records/machines.yaml
```

In that private configuration, set `project_root` to the repository's absolute
path and replace the username, allocation, work and install path placeholders.
Keep `records_dir: software` and `state_dir: state`. Review the node, walltime and
queue limits for your intended job. Configuration values are explicit; there is
no site-verification approval step. Legacy `site_verified` values are ignored.

Ignore `machines.yaml`, `state/`, `work/` and `install/` in the private repository.
Keep `software/` tracked there: promotion commits only the selected record, and
never pushes it. Do not add a public remote to the private records repository.
Site/storage notes are advisory and can be recorded privately as needed.

## Initialize and customize the record

From the public tool checkout, run:

```sh
hpctrack --config /path/to/private-records/machines.yaml doctor
hpctrack --config /path/to/private-records/machines.yaml sw init graspa --machine polaris --template examples/graspa/record
```

Edit the private `software/graspa/polaris/record.yaml`: replace the source path
with the directory containing your install.sh and set the validation account.
The build wrapper loads PrgEnv-nvidia, runs the captured install.sh unchanged and
installs the resulting nvc_main.x. Adjust the private wrapper for other environments.

Copy your own small calculation into the private record's `test/input/` directory.
Include simulation.input and all required structure and force-field files, without
historical output or restart files. A short example is 5,000 initialization cycles,
zero equilibration and 5,000 production cycles. Choose and record a random seed.
The example job uses one node, one GPU process and at most 900 seconds; configure
limits and cycle counts to suit your calculation. Record decisions in NOTES.md.

## Build, validate and promote

```sh
hpctrack --config /path/to/private-records/machines.yaml sw build graspa --machine polaris
hpctrack --config /path/to/private-records/machines.yaml sw validate graspa --machine polaris --build BUILD_ID
hpctrack --config /path/to/private-records/machines.yaml sw promote graspa --machine polaris --build BUILD_ID
hpctrack --config /path/to/private-records/machines.yaml sw show graspa --machine polaris
```

Replace BUILD_ID with the completed build's ID. A wait timeout returns exit 40;
resume that operation rather than starting another build or job:

```sh
hpctrack --config /path/to/private-records/machines.yaml resume --operation OPERATION_ID
```

Configure Git identity in the private records repository before promotion.
Commit failures are resumable. On exit 20, return the authentication remedy to
the human. Never retry an uncertain submission or change backends implicitly.

The completion checker requires successful scheduler completion, both phase-end
markers, final program completion, `Total GPU Energy:` output and no reported
`CUDA Error:`. It does not invoke nvidia-smi. Energy, loading, drift and runtime
are informational diagnostics. There is one validation job and no numerical
reference-acceptance step. A passing promoted installation reports `validated`.
Reference-mode records retain their accepted-reference comparison and `verified`
status. A failed revalidation cannot be overridden by an older pass.

## File provenance and agent use

Each build captures modified and untracked files under the declared source path.
`.git`, `*.o` and `*.x` are excluded by this example. Originals are untouched.
The build uses a writable copy, and resume uses the existing frozen snapshot.
Run a new build to capture later edits.

`sw show` includes `builds[].source_files`. Each entry, including install.sh,
records the full original, snapshot and build-copy paths plus a SHA-256 hash of
the captured bytes. Each build and validation also exposes `record_snapshot`,
which contains its saved wrapper, job, checker and input files. Keep snapshots
and logs with private state. Paths and raw command output can disclose personal
information and should not be attached to public issues or PRs.

An agent uses the same CLI with `HPCTRACK_ACTOR=agent` and an explicit private
`--config`. It respects the user's source edits and resource limits, records
interventions in NOTES.md, and resumes pending operations. A future skill can
orchestrate this sequence without a new record format or storage service.

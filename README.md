# hpctrack

A JSON command-line tool for reproducible HPC software records and resumable job
tracking. Local development currently covers the foundation, jobs, and software
record lifecycle (Phases 1–3). Staleness checks, scaling studies, dashboard, and
operational skills follow the planned Phase 3 review.

IRI is the intended default for Polaris and Aurora. PBS over SSH is an explicitly
configured alternative. Neither adapter has been verified on the actual sites
yet. All committed test fixtures are synthetic.

## Install

Use Python 3.10 or newer:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

For live IRI access, install the optional integration with `pip install '.[iri]'`.
Authentication is always performed by a human. The demo requires no HPC access,
credentials, PBS installation, or network calls after dependencies are installed.

## Local demonstration

The explicit configuration below confines demo records, logs, prefixes, scheduler
state, and the database to `state/demo`. Its detached workers run tiny local
scripts; every result is labeled `simulated`. This does not validate LAMMPS,
MPI, GPUs, Polaris, or Aurora.

```sh
hpctrack --config examples/demo/machines.yaml doctor
hpctrack --config examples/demo/machines.yaml sw init demo --machine demo --template examples/demo/record
hpctrack --config examples/demo/machines.yaml sw build demo --machine demo
hpctrack --config examples/demo/machines.yaml sw validate demo --machine demo
```

The first validation returns `state: reference_pending`. Review the candidate
`sum_of_squares` value (30 for the included input), then use the returned validation
ID in the acceptance command. After accepting, run a new comparison:

```sh
hpctrack --config examples/demo/machines.yaml sw reference accept demo --machine demo --validation VALIDATION_ID --yes
hpctrack --config examples/demo/machines.yaml sw validate demo --machine demo
hpctrack --config examples/demo/machines.yaml sw promote demo --machine demo --build BUILD_ID --no-commit
hpctrack --config examples/demo/machines.yaml sw show demo --machine demo
```

`--no-commit` explicitly skips Git for this disposable demo. Normal promotion
commits only the selected record and preserves unrelated staged files. For a
tracked record, configure `records_dir: software` inside a Git worktree and omit
`--no-commit`. Configure your Git identity before promotion.

The database is authoritative. Do not edit generated manifests, histories, or
accepted references. Recipes, notes, test inputs/checkers, and `record.yaml` are
editable. Replacing an accepted reference requires a separate reviewed migration;
automatic replacement is deliberately unsupported in this milestone.

## Jobs and recovery

```sh
hpctrack --config examples/demo/machines.yaml jobs submit examples/demo/job.sh --machine demo --nodes 1 --walltime 00:00:30 --queue debug --account demo
hpctrack --config examples/demo/machines.yaml jobs sync
hpctrack --config examples/demo/machines.yaml jobs list --all
hpctrack --config examples/demo/machines.yaml jobs show JOB_ID --machine demo
hpctrack --config examples/demo/machines.yaml jobs tag JOB_ID --machine demo --project example
hpctrack --config examples/demo/machines.yaml jobs cancel JOB_ID --machine demo
hpctrack --config examples/demo/machines.yaml resume --operation OPERATION_ID
```

External jobs require `--yes` to cancel. Job names alone never establish ownership.
Commands that wait accept `--wait-timeout SECONDS`; a timeout does not cancel work.
`resume` uses existing operation evidence and never blindly resubmits an uncertain
job. A preparation interrupted before launch is marked failed and can be started
again as a new command. An unresolved submission remains pending for inspection.

## CLI contract

Global options precede commands: `--config PATH`, `--state-dir PATH`, and `--json`.
Every command accepts `--json`; JSON is already the default. Successful commands
print one `{"ok": true, "data": ...}` object. Expected errors print one object
with `ok: false`, `error`, `message`, and relevant remedy/operation fields. Help
and version output remain plain text. Remote stdout is captured in artifacts.

| Exit | Meaning |
| --- | --- |
| 0 | Successful command, including a candidate awaiting acceptance |
| 1 | Unexpected, transport, or service failure |
| 2 | Invalid command/configuration/input |
| 10 | Build or validation failed |
| 20 | Human authentication required |
| 30 | Resource, provenance, ownership, or confirmation refusal |
| 40 | Operation pending, interrupted, or awaiting reconciliation |

Set `HPCTRACK_ACTOR=agent` for agent invocations. This attribution field is not an
identity security boundary. Agent invocations cannot call interactive connect or
accept scientific reference candidates.

## Develop and deploy

```sh
python -m pytest
ruff check .
python -m build
```

Tests use isolated temporary directories, mocked HTTP/SSH, and tiny local scripts.
No real scheduler or token store is contacted. See [the implementation plan](plan.md),
[deployment instructions](docs/deployment.md), and [site verification](docs/site-notes.md).

Shell recipes/checkers are trusted code. Validating configured paths is not an
operating-system sandbox. The demo and real transports share workflow code but
live paths, allocations, storage durability, and scientific checks still require
site acceptance before production use.

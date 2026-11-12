# hpctrack

A JSON command-line tool for reproducible HPC software records and resumable job
tracking. Local development currently covers the foundation, jobs, and software
record lifecycle (Phases 1–3). Staleness checks, scaling studies, dashboard, and
operational skills follow the planned Phase 3 review.

For your own modified source checkout, see the [gRASPA Polaris pilot](docs/graspa-pilot.md)
(`--template graspa`).
It uses explicit local PBS execution, working-tree snapshots, and completion-only
validation through the existing CLI. Live actions use the explicit machine
configuration and resource limits without a site-verification approval gate.

IRI is the intended default for remote Polaris and Aurora controllers. PBS over
SSH and the personal local PBS pilot are explicit alternatives. Neither adapter
has been verified on the actual sites yet. All committed test fixtures are synthetic.

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

## Workspace

hpctrack is infrastructure; your records and ledger live in a per-user workspace,
`~/.hpctrack` by default. Override it with `HPCTRACK_HOME=DIR` or the global
`--workspace DIR` (for example, a project-filesystem ledger shared by a team).

```sh
hpctrack templates list
hpctrack init --machines demo        # or pbs-local, pbs-ssh, iri; then fill REPLACE_*
```

`init` refuses to overwrite and creates:

```text
~/.hpctrack/
  hpctrack.yaml                    # machines, queues, accounts, limits
  AGENTS.md                        # operating rules for agents
  skills/build-software/SKILL.md   # the agent build loop
  records/<name>/<machine>/        # recipes, tests, NOTES.md, manifest.json, history.jsonl
  state/                           # gitignored: authoritative SQLite ledger, snapshots, logs
```

The workspace is its own Git repository; `sw promote` commits records there, never
into the hpctrack checkout. Other commands fail with `workspace_missing` until a
workspace exists; there is no fallback to the demo.

## Local demonstration

The demo machine runs tiny local scripts in detached workers; every result is labeled
`simulated`. It does not validate LAMMPS, MPI, GPUs, Polaris, or Aurora.

```sh
export HPCTRACK_HOME=$(mktemp -d)/ws
hpctrack init --machines demo
hpctrack doctor
hpctrack sw init demo --machine demo --template demo
hpctrack sw check demo --machine demo
hpctrack sw build demo --machine demo
hpctrack sw validate demo --machine demo
```

The first validation returns `state: reference_pending`. Review the candidate
`sum_of_squares` value (30 for the included input), then use the returned validation
ID in the acceptance command. After accepting, run a new comparison:

```sh
hpctrack sw reference accept demo --machine demo --validation VALIDATION_ID --yes
hpctrack sw validate demo --machine demo
hpctrack sw promote demo --machine demo --build BUILD_ID
hpctrack sw history demo --machine demo
hpctrack ledger export --output ledger.jsonl
```

Promotion commits only the selected record into the workspace repository and
preserves unrelated staged files; configure your Git identity first, or pass
`--no-commit` for a workspace created with `init --no-git`.

The database is authoritative. Do not edit generated manifests, histories, or
accepted references. Recipes, notes, test inputs/checkers, and `record.yaml` are
editable. Replacing an accepted reference requires a separate reviewed migration;
automatic replacement is deliberately unsupported in this milestone.

## Agent loop and ledger

An agent (or a person) writes `build.sh` and the test, and hpctrack runs each attempt
from immutable snapshots and records it. The workspace skill describes the loop:

- `sw check` (offline) reports unfilled `REPLACE_*` placeholders, `rebuild_needed`
  (`recipe_changed`, `build_failed`, ...), `revalidate_needed`, and `next_action`.
- A failed `sw build` (exit 10) returns `log_tail.stdout`/`log_tail.stderr`.
- `sw note --section "Failures and fixes" --message ...` appends a dated, attributed
  entry to NOTES.md and a `note` ledger event.
- `sw history` and `ledger export [--record N/M] [--machine M] [--since SEQ] [--output FILE]`
  return events with `sequence`; pass the last sequence to `--since` for incremental export.

Every event carries `actor` and `actor_detail`: `{kind, user, agent, session}` from
`HPCTRACK_ACTOR`, the login name, `HPCTRACK_AGENT`, and `HPCTRACK_SESSION`. Agent and
session must be short identifiers. Attribution is not an identity security boundary.

## Jobs and recovery

```sh
hpctrack jobs submit "$HPCTRACK_HOME/jobs/example.sh" --machine demo --nodes 1 --walltime 00:00:30 --queue debug --account demo
hpctrack jobs sync
hpctrack jobs list --all
hpctrack jobs show JOB_ID --machine demo
hpctrack jobs tag JOB_ID --machine demo --project example
hpctrack jobs cancel JOB_ID --machine demo
hpctrack resume --operation OPERATION_ID
```

External jobs require `--yes` to cancel. Job names alone never establish ownership.
Commands that wait accept `--wait-timeout SECONDS`; a timeout does not cancel work.
`resume` uses existing operation evidence and never blindly resubmits an uncertain
job. A preparation interrupted before launch is marked failed and can be started
again as a new command. An unresolved submission remains pending for inspection.

## CLI contract

Global options precede commands: `--workspace DIR`, `--config PATH` (advanced: an
explicit configuration file whose directory becomes the root), `--state-dir PATH`, and `--json`.
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

Set `HPCTRACK_ACTOR=agent` for agent invocations. Agent invocations cannot call interactive connect or
accept scientific reference candidates.

## Develop and deploy

```sh
python -m pytest
ruff check .
python -m build
```

Tests use isolated temporary directories, mocked HTTP/SSH, and tiny local scripts.
No real scheduler or token store is contacted. See [the implementation plan](plan.md),
[deployment instructions](docs/deployment.md), and [advisory site notes](docs/site-notes.md).

Shell recipes/checkers are trusted code. Validating configured paths is not an
operating-system sandbox. The demo and real transports share workflow code but
live paths, allocations, storage durability, and scientific checks depend on the
chosen environment. Site notes document observations without blocking execution.

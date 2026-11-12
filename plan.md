# HPC software and job tracker: implementation plan

Nov 11, 2026 · @Thang · revised after implementation review

## Nov 12 amendment: portable agent skill

Package one user-wide `hpctrack` skill for Claude Code, Codex, OpenCode, and Pi.
The explicit offline `skills install` command manages the two distinct host paths,
records version/file hashes, and refuses edited or unmanaged collisions; `skills status`
and dry runs need no initialized workspace. Keep the existing workspace skill and
operating rules as the maintained sources for the portable references.

`workspace show` resolves configuration and absolute data paths without opening the
ledger. The agent workflow inspects existing records, reads the selected workspace's
rules, and resumes matching pending operations reported by `sw check` before launching
another attempt. Preserve agent/session attribution and human-only authentication and
reference acceptance. Verify the wheel outside the checkout. Filesystem tests are not
manual host compatibility evidence. Public publishing, plugins, MCP, cross-agent
orchestration, and the deferred post-Phase-3 work remain outside this change.

## Nov 12 amendment: per-user workspace and agent ledger

hpctrack is infrastructure; users and agents create the data. These decisions
supersede the single-repository layout, the `examples/` demo paths, and the
`config/machines.yaml` default described below.

- Data lives in a per-user workspace: `--workspace DIR` > `$HPCTRACK_HOME` >
  `~/.hpctrack`. `hpctrack init --machines demo|pbs-local|pbs-ssh|iri` creates
  `hpctrack.yaml`, `AGENTS.md`, `skills/build-software/SKILL.md`, `records/`, a
  gitignored `state/`, and a Git repository that `sw promote` commits into. A
  missing workspace is an error (`workspace_missing`), never a demo fallback.
  `--config FILE` remains an advanced override.
- Record and machine templates ship as package data (`hpctrack templates list`,
  `sw init --template NAME|DIR`). Only the generic `demo` record is packaged;
  real-code test cases such as gRASPA live in `examples/` and are used by path. Templates carry `REPLACE_*` placeholders that
  `sw check` reports and build/validation refuse.
- SQLite stays authoritative (schema version 2). Events carry `actor_detail`
  (`kind`, `user`, `agent`, `session`); `ledger export` and `sw history` give a
  portable, incremental (`--since SEQ`) JSONL view. Committed `builds[].source_files`
  keep only `{path: sha256}`; full paths stay in the operation data.
- Agent loop: `sw check` (offline staleness and `next_action`), `log_tail` on
  `build_failed`, and `sw note` for attributed NOTES.md entries. One packaged
  skill (`build-software`) covers the loop; the seven operational skills and the
  dashboard remain deferred.

## Nov 12 amendment: personal gRASPA pilot

The user selected a lean, single-user pilot from the current Polaris session:
track installation status, rebuild modified code, and validate with a small job.
For this pilot, the following decisions supersede Crux/LAMMPS-first and mandatory
reference-comparison requirements below; the Phase 3 review checkpoint remains.

- Reuse the PBS adapter with explicit `pbs_local`/local transport; no SSH or IRI fallback.
- Snapshot the declared working tree, respecting dirty/untracked source and leaving
  originals untouched. Replay the user's install.sh in a fresh build copy.
- Use optional completion validation for gRASPA; existing records default to reference
  mode. Completion promotion reports `validated`, without claiming scientific agreement.
- Use the supplied CALF-20 input copy, 5,000 initialization and production cycles each,
  zero equilibration, ChemGraph/debug, one node/GPU process and 900 seconds.
- Add four focused tests, retain existing offline coverage, and stop for review before
  the live pilot. The user subsequently completed that review and removed the
  site-verification gate. Site/storage notes are advisory; configured limits remain enforced.

Later phases remain deferred.

## Implementation status and confirmed decisions

**Develop and test locally first; site notes are advisory, with no deployment approval gate.** The user removed the site-verification gate. Local acceptance uses an isolated demo transport/backend and synthetic fixtures. Keep live observations in local site notes (not tracked in this repository) and distinguish unverified facts from observed results. Initialize Git where repository metadata is writable.

- Use IRI for both Polaris and Aurora. Keep PBS over SSH as an explicitly configured alternative, never an automatic submission fallback.
- Make `sw check` inspect-only by default; remote execution requires the explicit flags described below.
- Complete a deterministic local build/validation/promotion milestone first. At deployment, validate real LAMMPS on Polaris and then Aurora.
- Require a dedicated human reference-acceptance step and a subsequent passing comparison before promotion.
- Retain the review checkpoint after Phase 3. Do not start later phases before that review.

## Summary and scope

hpctrack (working name) is a human-triggered command-line tool plus a static dashboard. It records how each scientific code was built on Polaris and Aurora, re-validates it with a small real calculation, runs scaling studies, and tracks PBS jobs. Every command returns JSON, so an agent can drive the same tool later through skill files.
The tool is developed locally and later deployed to a Crux compute node. Live operation uses human-authenticated SSH and IRI. The explicit demo requires no HPC connection or credentials.
In scope for v1:

- Job listing, submission and cancellation on Polaris and Aurora behind one interface
- Software records: build script, validation job, agent-written notes, manifest, history
- Staleness detection against machine changes and upstream releases, run on demand
- Scaling studies for codes marked as scalable
- A static HTML dashboard and a set of skill files for agents

Out of scope for v1:

- Background daemons, cron, or any automatic trigger
- Automatic rebuilds without a human starting them
- Multi-user support or a hosted web server
- Parsing live job output into science-level progress (planned follow-up)

## Advisory site observations

Use the human-run collection procedure and S01–S12 checklist in the local site notes as needed for troubleshooting. Record execution location, timestamp, commands or site guidance, sanitized results, and the observer. Public documentation and workstation settings are not substitutes for actual site observations; completing this checklist is not required to run configured operations.

- Confirm SSH routes, master lifetime, idle policies, and detached-process survival on both targets.
- Confirm Crux job lifetime/preemption, durable repository/state storage, one-controller ownership, and site-supported SQLite locking and durability. A passing smoke test alone does not establish reliable network filesystem behavior.
- Record target build/source/job roots, login/compute visibility, and transfers when mounts differ; identical mount paths are not required.
- Verify PBS JSON, historical queries, IRI resource IDs, account access, pagination, token refresh, and failure responses. [ALCF now lists Aurora as IRI-supported](https://docs.alcf.anl.gov/services/iri-api/).
- Confirm proxy/source access, approved allocations and queues, node/walltime/submission limits, per-command budgets, and build parallelism.
- Capture sanitized adapter evidence without tokens or authorization headers. Actual submission/cancellation smoke tests remain Phase 2 acceptance work.

Use site evidence to diagnose conflicts with implementation assumptions. No accounts, paths, or resource IDs are inferred from examples. Unknown site storage and execution details remain documented uncertainties and do not trigger an approval gate.

## Local development and acceptance

- Global `--config` and `--state-dir` options select configuration and state. The demo is explicitly selected with `examples/demo/machines.yaml`; missing live configuration never falls back to simulation.
- Demo records, prefixes, scheduler evidence, and state are isolated under `state/demo`. Results are labeled simulated and make no scientific or HPC validity claim.
- Local Phases 1–3 cover the foundation, jobs, resumable builds, reference acceptance, validation, promotion, and record-only Git integration. A deterministic calculation replaces the live LAMMPS test for this milestone.
- Keep the Phase 3 review checkpoint. Staleness, scaling, dashboard, and seven operational skills follow review; machine acceptance follows deployment.
- Test real adapters through injected HTTP/process boundaries, using explicitly synthetic fixtures. Test offline on Python 3.10 and the development interpreter; build and smoke-test a wheel.
- `sw promote --no-commit` explicitly supports disposable non-Git demos. Default promotion still requires a record-only commit and remains resumable if Git is unavailable.
- Deployment instructions are in `docs/deployment.md`. Live operations use explicit machine configuration and resource limits. The legacy `site_verified` field is accepted but ignored for execution.

## Architecture

The CLI is the only component that talks to ALCF. The human, the agent and the dashboard all work through it or through the state it writes.
Builds run detached on the target login node over SSH with site-approved parallelism. Validation and scaling run on compute nodes through the configured job backend. The Phase 3 pilot must compile without executing on a login-node GPU; compute-node builds require an explicit extension to this execution model.

IRI job queries do not require SSH. Builds, staging, log retrieval, and fingerprint collection require an authenticated SSH master. No target process opens the controller's database.

## Repository layout

One Git repository holds the tool, software records, and skills. Use Python 3.10 or later, Click, Pydantic 2, Jinja2, requests, PyYAML, and the supported `alcf-tokens` integration. Use standard-library SQLite. Use pytest and Ruff for development. Add `packaging` for Python version comparisons and `markdown-it-py` for rendering notes, with raw HTML disabled. Use inline SVG for dashboard plots; no hosted service or chart CDN is required.

```text
hpctrack/
  pyproject.toml
  AGENTS.md                  # entry point for agents: rules + pointer to skills/
  config/machines.yaml       # per machine: ssh alias, job backend, queues, account, proxy
  src/hpctrack/
    cli.py                   # all commands, --json on every one
    config.py
    connect.py               # SSH master connection: open, check, close
    remote.py                # run(machine, cmd), put/get files over the master socket
    backends/
      base.py                # JobBackend protocol + normalized Job model
      iri.py                 # ALCF IRI API
      pbs_ssh.py             # qsub / qstat / qdel over SSH
      fake.py                # replays recorded JSON, for unit tests
    records.py               # load and validate software records
    build.py                 # replay build.sh, capture logs
    validate.py              # submit test job, run check.py
    scaling.py
    fingerprint.py
    upstream.py              # PyPI and GitHub release checks
    store.py                 # transactional state, operation checkpoints, append-only events
    dashboard.py             # static HTML generator
  software/<name>/<machine>/ # one software record each
  skills/<skill>/SKILL.md
  state/                     # gitignored: hpctrack.db, logs, dashboard output
  tests/
```

## Software record format

A software record is a directory, software/<name>/<machine>/, that contains everything needed to rebuild and re-validate one code on one machine without the original agent session.

| File | Written by | Purpose |
| --- | --- | --- |
| `record.yaml` | Human or agent | Editable source/upstream declarations, Python tracking, explicit environment/version probes, and validation resources. Generated state is not edited here. |
| `build.sh` | Agent, then replayed unchanged | Exact recipe, including module setup and credential-free proxy settings. Receives tool-selected `PREFIX` and an immutable `SRC_REF`. |
| `NOTES.md` | Agent or human | Reasoning, failed approaches, workarounds, and change history under the fixed headings below. |
| `test/job.sh.j2` | Agent, reviewed by human | Shell body for validation. Resource directives are generated by the tool from `JobSpec`, not embedded in this template. |
| `test/input/` | Agent, reviewed by human | Small real calculation taking a few minutes. |
| `test/reference.json` | Tool, after explicit acceptance | Accepted scientific values, units, tolerances, and validation provenance. Never silently regenerated. |
| `test/check.py` | Agent, reviewed by human | Reads the output directory and an explicitly supplied reference path, emits the result contract below, and exits 0 or 1. Runs in the target job environment. |
| `scaling.yaml` | Human or agent | Optional study definition; its presence determines whether the record is scalable. |
| `manifest.json` | Tool | Current generated state and provenance. Never edited by hand. |
| `history.jsonl` | Tool | Generated projection of immutable record events with stable IDs; not an independent event store. |

NOTES.md headings, in this order: Environment, Build decisions, Failures and fixes, Known issues, Validation, Change log. Each change-log entry carries a date, the trigger, and who acted (human or agent).
Manifest example, with placeholder values (editable declarations originate in `record.yaml`; resolved values are copied into each build). Include a schema version and retain every validation separately in the database.

```json
{
  "schema_version": 1,
  "name": "lammps",
  "machine": "polaris",
  "source": {"type": "git", "url": "<repo url>", "ref": "<tag>", "commit": "<sha>"},
  "upstream": {"type": "github_release", "repo": "<owner>/<repo>"},
  "python_env": {"path": "<venv path>", "track": ["<pypi package>"]},
  "builds": [
    {"id": "<build id>", "prefix": "<install path>", "built_at": "<iso time>",
     "source_commit": "<sha>", "recipe_hash": "<hash>",
     "build_fingerprint": "<immutable fingerprint hash>",
     "last_validation_id": "<validation id>", "validated_fingerprint": "<fingerprint hash>",
     "validated_at": "<iso time>", "job_id": "<full pbs id>"}
  ],
  "current_build": "<build id>",
  "status": "verified",
  "status_reasons": [],
  "stale_machine": false,
  "stale_upstream": false,
  "accepted_reference_hash": "<hash>",
  "scalable": true
}
```

Builds also retain resolved source identity, recipe/input/checker hashes, remote locations, and their operation IDs. A mutable tag or branch is resolved before execution; later builds cannot retroactively change an earlier build's source or environment. Source tarballs need a recorded digest in place of a Git commit.

The normal checker contract is `{"passed": bool, "metrics": {...}, "messages": [...]}` with exit 0 for a pass and 1 for a failure. In candidate-reference mode, the same checker extracts metrics and verifies execution/accelerator checks without claiming a reference comparison. The operation reports `reference_pending`, and cannot supply promotion evidence. Candidate values and proposed tolerances are recorded with the validation for human review.

Rules for check.py, using LAMMPS as the first case:

- Compare a physical result against the reference within a tolerance, for example final potential energy.
- Confirm from the log that the intended accelerator package and device were actually used.
- Report a performance metric so slowdowns after a machine update are visible, without failing on it.

## Connections and authentication

A human establishes SSH masters and IRI authorization. All operational commands are non-interactive, including credential refresh. Treat expired/unavailable credentials as a reportable state.

- Transport is hidden in SSH config. machines.yaml names an SSH host alias per machine. Whether that alias is direct, a jump host or a reverse tunnel is set in ~/.ssh/config, so the tool does not change when the route does.
- `hpctrack connect <machine>` is the only interactive hpctrack command. It opens an SSH master with explicit ControlMaster, ControlPersist, keepalive, and connection-timeout settings. MFA uses the human's terminal, not JSON stdout. The human runs it on the Crux node where the agent lives.
- Socket location. Keep the control socket on node-local storage such as /tmp/$USER/hpctrack/, since Unix sockets often fail on shared filesystems.
- Other SSH actions use the socket with `BatchMode=yes`, closed stdin unless passing explicit payloads, and bounded timeouts. Check the master before acting and disable new-connection fallback, including the race where the socket vanishes after the check. IRI-only actions do not check SSH.
- Dead connection. The command exits with code 20 and prints `{"ok": false, "error": "auth_required", "message": "SSH master unavailable", "machine": "aurora", "fix": "hpctrack connect aurora"}`. It never waits for input.
- Agents stop on exit 20. They report the fix command to the human and wait. They never attempt to authenticate.
- Long operations survive disconnects. Builds run detached on the remote side with a log file and an exit-status file, and jobs live in PBS. After reconnecting, hpctrack resume picks up from the recorded remote state.
- Crux job expiry. Repository, database, and operation evidence live on confirmed durable storage. A replacement controller checks ownership, loads checkpoints, re-establishes required credentials as a human, and runs `resume`. Sockets remain node-local and are never copied to a replacement node.

`doctor` reports SSH state, socket age, IRI/authentication state, configured backend reachability, proxy reachability, and whether the state root is usable. Report these independently; a dead SSH master does not make a successful IRI query fail. Bound each probe and retain per-machine failures in the aggregate JSON result.

## Job backends

One JobBackend interface hides how each machine is reached, so the rest of the tool never branches on machine name. The backend per machine is a setting in machines.yaml.

| Machine | Default backend | Alternative |
| --- | --- | --- |
| Polaris | `iri` | Explicitly configured `pbs_ssh` |
| Aurora | `iri` | Explicitly configured `pbs_ssh` |

Interface methods: `submit(spec: JobSpec)`, `list(user, include_finished)`, `get(job_id)`, and `cancel(job_id)`. A backend instance is bound to one configured machine. The fake backend implements the same contract and supports recorded responses and injected failures.

`JobSpec` contains operation ID, machine, name, shell body, node/CPU resources, walltime in seconds, queue, account, required filesystems, absolute working directory, environment, and stdout/stderr paths. CLI flags and record settings construct this object before any submission. Reject embedded scheduler directives in user shell bodies so resource requests cannot silently disagree with the validated spec. The PBS adapter generates directives; IRI translates the same spec into its resource/attribute fields and runs the shell body with an explicit working directory.

Both adapters return `Job` with full scheduler ID, machine, name, normalized state, raw state, queue, account, nodes, requested walltime, submit/start/end times, exit status, workdir, stdout/stderr paths, and tool operation ID when known. Normalized states are `queued`, `held`, `running`, `suspended`, `finished`, `failed`, `cancelled`, and `unknown`. Unavailable metadata remains null. Job identity is `(machine, full scheduler ID)`; never strip server suffixes for storage or cancellation.

Follow all IRI list pages and preserve backend evidence. Do not infer success when a job disappears. Query history where supported, then retain `unknown`/last-known evidence if no authoritative completion is available. Read failures are not job failures. Never automatically switch adapters or retry a submission whose acceptance is uncertain.
Job labelling:

- Tool-submitted names include `ht-<kind>-<subject>` and an operation-ID suffix within the verified scheduler name limit. Kinds include `manual`, `validate`, and `scaling`. Store the full operation ID in job metadata/environment and the database, along with software/build IDs and an optional project label. Truncating a display name must not truncate the durable identity.
- hpctrack jobs sync pulls every job owned by the user, so production jobs submitted outside the tool appear too. hpctrack jobs tag <job_id> --machine <m> --project <label> attaches a project to those.
- Each sync writes state changes to the event log, which gives job history without relying on how long PBS keeps finished jobs.

IRI token handling uses the supported `alcf-tokens` integration at call time, including non-interactive refresh in its external credential store. Never copy tokens into records, the database, command arguments, or logs. If authorization is unavailable after permitted refresh, return exit 20 with `alcf-tokens login iri` as the human fix. Agents never invoke login or handle MFA. Transport/service failures and account-policy refusals must not all be mislabeled as authentication failures.

## CLI commands

JSON is the default. Every command accepts `--json` as an explicit compatibility flag and emits one result object on stdout, including expected failures. Logs/progress use stderr. Success uses `{"ok": true, "data": ...}`; errors retain a stable string `error` code plus `ok: false`, a message, and relevant machine/operation/fix fields. Keep CLI usage errors machine-readable too. Do not interleave raw subprocess output with the result object. `--help` and version output remain normal informational CLI output.

All network actions and process waits are bounded. Long operations accept a wait timeout and return exit 40 with an operation ID and remote state when still in progress; timeout does not cancel remote work. Repeated read-only observations may be retried within the bound; uncertain submissions may not.

| Command | Behavior |
| --- | --- |
| `jobs submit <script> --machine <m> --nodes <n> --walltime <HH:MM:SS> --queue <q> --account <a> --workdir <path> [--project <label>]` | Stage a shell body and submit a validated `JobSpec`; filesystem/output defaults come from confirmed machine configuration. |
| `sw reference accept <name> --machine <m> --validation <id> --yes` | Human acceptance of reviewed candidate values and tolerances; records provenance and writes the accepted reference. A new validation must pass before promotion. |

Other commands:

| Command | Behavior |
| --- | --- |
| `connect <machine>` | Human-only interactive SSH master setup. |
| `doctor` | Independent connection, backend, proxy, and state health per machine. |
| `status` | Software matrix and active-job summary from stored state, with observation timestamps. |
| `jobs list [--machine <m>] [--project <label>] [--all]` | Stored nonterminal jobs; optionally finished jobs. Run sync for fresh remote observations. |
| `jobs show <job_id> --machine <m>` | Job details and a bounded output tail; report unavailable logs explicitly. |
| `jobs sync [--machine <m>]` | Pull owned current/historical job states and append change events. |
| `jobs tag <job_id> --machine <m> --project <label>` | Attach a project label. |
| `jobs cancel <job_id> --machine <m> [--yes]` | Cancel; require `--yes` unless durable state proves tool ownership. A matching name is insufficient. |
| `sw list` | All records with status and independent stale flags. |
| `sw show <name> --machine <m>` | Manifest, notes, recent history, and operation evidence. |
| `sw init <name> --machine <m>` | Scaffold editable declarations, recipe, notes, and test templates. |
| `sw build <name> --machine <m> [--ref <tag>]` | Resolve the source and replay the recipe into a fresh prefix. |
| `sw validate <name> --machine <m> [--build <id>]` | Submit validation, wait within the requested bound, and collect checker evidence. |
| `sw promote <name> --machine <m> --build <id>` | Promote only after an accepted-reference comparison passes under the current known environment. |
| `sw check [<name>] [--machine <m>] [--revalidate OR --repair]` | Inspect by default; the two mutually exclusive flags authorize the workflows below. |
| `scaling run <name> --machine <m> [--yes]` | Estimate a study; submit only with explicit confirmation and within budget. |
| `scaling report <name> --machine <m>` | Speedup/efficiency, individual results, and study history. |
| `fingerprint <machine>` | Collect available login/environment facts without submitting a job. |
| `upstream check [<name>] [--machine <m>]` | Compare tracked versions against upstream; no build or validation submission. |
| `dashboard build` | Render static HTML from stored state. |
| `resume [--operation <id>]` | Reconcile interrupted work and continue only previously authorized steps. |

| Exit code | Meaning |
| --- | --- |
| 0 | Success, including an inspection reporting stale records or an unaccepted candidate reference |
| 1 | Unexpected, transport, or service error; include a specific machine-readable error code |
| 2 | Invalid command usage or malformed configuration/input |
| 10 | Build or validation failed |
| 20 | Human authentication required for SSH or IRI |
| 30 | Guardrail refusal, including budget/queue/account restrictions or a missing confirmation |
| 40 | Waiting timed out; remote work may continue and must be reconciled with `resume` |

## Durable state and recovery

SQLite is authoritative for jobs, builds, validations, studies, reference acceptance, operation checkpoints, and an append-only event table. The audit fields are stable event ID, UTC time, machine, kind, subject, actor, operation ID, and JSON payload. Add a database schema version; do not rely on filesystem projections to decide which actions have already run.

Use rollback journaling, short transactions, and a durable state root. Only one Crux host owns the controller at a time. Concurrent local invocations serialize mutations and atomically claim operation steps; do not hold a database transaction across an SSH/API call. A replacement host cannot steal ownership while the original controller might still be active. Document storage behavior in advisory site notes; merely disabling WAL does not prove network-filesystem suitability.

For every side effect, persist intent and a unique operation ID first. Store rendered inputs, hashes, budget authorization, remote paths, receipts, and completion evidence. Detached builds use unique operation directories, a launch lock, logs, and an atomically written exit-status file. Missing completion evidence does not justify launching another build.

After a lost submission response, query recorded IDs or reconcile by the operation marker before continuing. If acceptance remains uncertain, retain an explicit `submission_unknown` checkpoint and refuse automatic resubmission. A wait timeout is not a remote failure, and a missing scheduler job is not a pass. `resume` cannot expand a study budget, accept a reference, or start a repair that the original command did not authorize.

Manifest and history files are atomic, rebuildable projections of committed state. Record events are append-only in the database; regeneration preserves their IDs and ordering without duplicate history rows. If projection writing or a promotion commit fails after the database transaction, report that pending step and let `resume` finish it without repeating the remote action. Git commits include only the selected record; unrelated staged or modified files are preserved.

## Build and validation loop

A record is accepted only when a clean replay of build.sh produces a binary that passes its validation job. That rule turns the agent's notes into something a later run can trust.
First installation, started by a human and carried out by an agent:

1. Run `sw init`, then fill in `record.yaml`, `build.sh`, and `NOTES.md`.
2. Iterate by editing the recipe locally and invoking `sw build` for each clean attempt. Record important choices as work proceeds. Agents do not execute an unrecorded interactive build outside the CLI.
3. Write the validation shell body, input, checker, and proposed metrics/tolerances. A human reviews the scientific test and intended accelerator checks.
4. Complete a clean replay into a fresh prefix, using the recorded recipe and immutable source revision.
5. Run `sw validate`. With no accepted reference, extract candidate values and verify execution/device checks. A successful extraction is not a validated build; report `reference_pending` and retain the evidence.
6. A human reviews values, units, and tolerances and runs `sw reference accept ... --validation <id> --yes`. Require the referenced candidate and reviewed input/checker hashes to match. Existing accepted references are not silently replaced; a requested replacement requires a separately reviewed record change and invalidates prior validation evidence.
7. Run `sw validate` again against the accepted reference. Store the reference/input/checker hashes, metric results, job ID, and observed environment with this comparison.
8. Run `sw promote`. Verify the passing comparison still matches the accepted reference, tested inputs/checker, build, and current known environment; then update current state and commit only the record. A failed candidate build or validation never replaces a working current build.

Re-check after machine or upstream changes:

1. Plain `sw check` collects observations, records field-by-field differences and stale flags, and returns. It does not submit a job, rebuild, or promote.
2. `sw check --revalidate` additionally validates each selected stale current build against its accepted reference. A pass updates validation provenance, not the immutable build fingerprint. A failure marks that current build unhealthy and returns exit 10; there is no rebuild.
3. `sw check --repair` authorizes revalidation and, on a scientific/execution failure, one clean replay of the current build's pinned source followed by validation. Promote the replacement only after a pass. Do not rebuild on authentication, transport, or scheduler-observation errors. Enforce the aggregate configured budget before each submission; no unbounded repair loops.
4. Failed repair leaves the current selection intact, reports it as broken, and identifies failing steps and logs. An upstream update remains a separate notice even after a successful repair; repair does not select a new release.
5. The human may start a repair agent with notes, fingerprint differences, build logs, and check output. The agent edits the recipe, records the intervention, and uses `sw build`, `sw validate`, and `sw promote` explicitly.

New upstream version: sw build --ref <new tag> builds into a new prefix alongside the current one. The current build stays in use until the new one validates and is promoted. Old prefixes are kept until a human removes them.

## Scaling studies

A scaling study reuses the validation machinery: the same job template, run at several node counts, with a performance metric extracted instead of a pass or fail. Only records with a scaling.yaml take part.

```yaml
kind: strong              # fixed work; weak scaling grows work with node count
nodes: [1, 2, 4]           # Polaris pilot; confirm queue limits in Phase 0
queue: debug-scaling
walltime: "00:20:00"
input: scaling/in.scale
size_variable: null       # weak scaling requires an explicit workload-size rule
work_units: 1             # amount of scientific work represented by the metric
repeats: 2
metric:
  name: timesteps_per_s
  source: checker         # structured metrics emitted by the record's checker
  direction: higher       # higher = total throughput; lower = elapsed seconds
max_node_hours: 20
```

The example budget is illustrative, not an approved allocation or cap. The effective cap is the lower of the study cap and the configured machine cap. Resource settings are validated using the same `JobSpec` as validation. Metrics must be positive and finite; missing/invalid values produce failed run rows rather than fabricated zeros.

Flow of scaling run:

1. Estimate total node-hours from nodes, walltime and repeats. Refuse with exit 30 if it exceeds max_node_hours.
2. Print the estimate and require --yes. An agent must get this confirmation from the human.
3. Submit one job per node count and repeat, respecting the configured per-user/project queue occupancy including jobs submitted outside hpctrack. The Polaris pilot runs sequentially on `debug-scaling`; do not enqueue the whole study at once. Persist pending runs so a wait timeout can be resumed without duplication.
4. As jobs finish, extract the metric and store one row per run with the build id and machine fingerprint.
5. Report the table and mark any run that failed or hit walltime.

For `direction: higher`, the metric must represent total scientific work per second, not per-node throughput. For `direction: lower`, convert elapsed seconds to throughput as `work_units / elapsed_seconds`. Strong scaling holds work fixed; weak scaling supplies an explicit input-size rule and total work at each node count. Do not infer how a code's input grows from the word "weak" alone.

Aggregate successful repeats using arithmetic mean throughput, and report individual values, successful/failed counts, and spread. With `P_N` the mean throughput at N nodes and `N1` the smallest configured node count, strong-scaling speedup is `P_N / P_1` and efficiency is `(P_N / P_1) * (N1 / N)`. Weak-scaling efficiency is `(P_N / N) / (P_1 / N1)`. If the baseline has no successful runs, derived values remain unavailable; do not silently choose a different baseline. Mark partial groups and walltime failures explicitly.

The current [Polaris queue documentation](https://docs.alcf.anl.gov/polaris/running-jobs/) supports the 1/2/4-node pilot on `debug-scaling` with only one queued/accruing/running job per user. The example must be checked against site notes before execution. [Aurora's scaling queue](https://docs.alcf.anl.gov/aurora/running-jobs-aurora/) currently starts at two nodes; its later study must use an approved machine-specific node list.
Because each run is stored with its fingerprint and build id, scaling report can compare the same study before and after a machine update or a rebuild.

## Staleness checks

A record goes stale for two reasons: the machine changed underneath it, or upstream released something newer. Both are checked on demand and both only change the status; neither rebuilds anything.
Machine/environment fingerprints are structured JSON with stable canonical hashes. Explicit probes in `record.yaml` describe how to reproduce the recipe's environment; do not attempt to infer arbitrary module loads by parsing shell scripts. Capture:

- OS release and kernel version
- Default loaded modules and the full module avail listing
- Versions of the compilers, MPI and GPU runtime that the record's build.sh loads
- GPU driver version as reported on a compute node, captured by the validation job itself

Store immutable build-time fingerprints and separate last-validation fingerprints. `fingerprint` collects available login/environment fields without submitting work. GPU/compute-node facts are captured in validation jobs, labeled with their observation time and origin, and are not represented as newly observed by a login-only check. Normalize ordering/noise before hashing; preserve raw evidence for diagnostics. `sw check` compares against the last successful validation while retaining the build-time diff for repairs.
Upstream checks use declarations from `record.yaml` and resolved current-build provenance:

| Tracking type | Current version | Latest version |
| --- | --- | --- |
| `pypi` | `pip list --format=json` in the configured environment | PyPI JSON API; compare parsed package versions |
| `github_release` | Current build's recorded source release | GitHub releases API; stable releases by default, never lexical tag ordering |
| `git_branch` | Current build's immutable commit | `git ls-remote` for the configured branch |

These calls need outbound internet, so they run where the proxy is configured, as set per machine in machines.yaml.
Failed upstream requests produce an observation error and leave last-known versions/stale flags intact. They never imply that software is current. Revalidating an unchanged version cannot clear `stale_upstream`.

Track current-build validation health, `stale_machine`, and `stale_upstream` independently. Display all reasons, with primary status precedence `unvalidated` (no promoted build), `broken` (current build failed validation), `stale-machine`, `stale-upstream`, then `verified`. An unsuccessful candidate leaves the current build's health unchanged. A verified record means an accepted-reference comparison passed under the most recently observed relevant environment; observation timestamps remain visible.

## Dashboard

The dashboard is a set of static HTML files generated by dashboard build from the SQLite event log and the software records. Nothing runs in the background, and the files can be opened through an SSH port forward or copied elsewhere.

| View | Shows |
| --- | --- |
| Software matrix | Software by machine, independent status reasons, validation date, and current/upstream versions |
| Jobs | Nonterminal jobs and recent completions, filterable by project, with observation age |
| Timeline | Immutable build, validation, fingerprint, upstream, and intervention events |
| Record detail | Rendered notes, build/validation history, reference provenance, and fingerprint differences |
| Scaling | Speedup/efficiency, individual results, incomplete groups, and previous compatible studies |

Read the transactional state and event log through the same query layer as the CLI. Build from a consistent database snapshot without making remote requests. Escape untrusted text and disable raw HTML in rendered notes. Bundle assets and data so every view works when opened from local files without a server or network. A dashboard is a dated snapshot, not live monitoring.

## Agent skills

Agent support is a set of SKILL.md files that teach an agent to use the CLI. No agent-specific code path exists, so anything an agent can do, a human can do with the same commands.

| Skill | When used | Core commands |
| --- | --- | --- |
| check-connection | Session start and after an authentication failure | `doctor`; report the human remedy on exit 20 |
| job-status | Inspect running or completed jobs | `jobs sync`, `jobs list`, `jobs show` |
| install-software | Add a code to a machine | `sw init`, `sw build`, `sw validate`, human reference acceptance, `sw promote` |
| check-software | Inspect status or maintenance impact | `fingerprint`, `upstream check`, inspect-only `sw check` |
| repair-software | Human authorizes repair | `sw show`, explicitly authorized repair or `sw build`/`sw validate`/`sw promote` |
| update-software | Human authorizes a new release | `sw build --ref`, `sw validate`, `sw promote` |
| run-scaling | Human authorizes a study and its estimate | `scaling run`, `scaling report` |

Each SKILL.md has the same sections: when to use, preconditions, steps with exact commands, how to react to each exit code, what must be confirmed with the human, and what to write to NOTES.md before finishing.
Create the root `AGENTS.md` standing rules during Phase 1, then complete the seven skills in Phase 7: use only hpctrack commands for operational remote actions, stop on exit 20, never authenticate, and record interventions in the record's change log. The documented Phase 0 bootstrap checks run before the CLI exists and are an explicit exception to CLI-only access, not an exception to human-only authentication.

## Guardrails

The guardrails are enforced in the tool, not only written in the skills, so they hold whoever is at the keyboard.

- No silent prompts. Non-interactive commands never wait for input. They exit with a code and a fix.
- Budget caps. `machines.yaml` sets node, walltime, and aggregate node-hours caps for every submitted command, including manual jobs, validation, repair, and scaling. Estimate `sum(nodes * walltime_seconds * repeats) / 3600` before a study submits anything. Reserve authorized steps durably so resume cannot reset the budget. Refuse over-budget work with exit 30.
- Allowed queues and accounts. Submit only to configured queues and allocations. Validate minimums as well as maximums, required filesystem resources, and queue occupancy before submission. `--yes` cannot override limits.
- Scoped tool writes. Validate canonical tool-generated prefixes and work paths under configured roots, including traversal/symlink escapes. Supply `PREFIX` to the build recipe. Arbitrary shell recipes/checkers remain trusted reviewed code; this path validation is not a filesystem sandbox and does not guarantee that a script cannot write elsewhere.
- No deletion. The tool has no command that removes a build prefix or a record. Cleanup is manual.
- Promotion needs a pass. Refuse promotion without a passing accepted-reference comparison for that exact build/input/checker/reference and current known relevant environment. Candidate metric extraction is never a pass for promotion.
- Cancel is scoped. jobs cancel acts without --yes only on jobs the tool submitted.
- Secrets stay out. Tokens and passcodes are never written to the repository, the database or logs.
- Everything is attributed. Each event records whether a human or an agent acted. The actor is set by an HPCTRACK_ACTOR environment variable that the skills require agents to set.

## Implementation phases

Build the local phases in order and meet their offline acceptance criteria. Site evidence is advisory. Initialize and commit Git where metadata permissions allow; test Git behavior in temporary repositories. Stop after local Phase 3 for review. No daemon or schedule is introduced.

| Phase | Deliverables | Acceptance |
| --- | --- | --- |
| Advisory site notes | Available S01–S12 observations and configuration decisions | Document observed behavior without requiring site-verification approval |
| 1. Skeleton and connections | Package, root agent rules, validated machine config, JSON/errors, connect/remote, durable store, doctor | Bounded independent SSH/IRI health; missing master yields exit 20 without authentication fallback; state transactions and ownership behave as specified |
| 2. Jobs | JobSpec/Job/JobBackend, IRI/PBS/fake, job commands, recovery | Local submission/sync/cancellation and synthetic adapter tests pass. Live qstat/IRI agreement is checked at deployment |
| 3. Software records | Templates, builds, reference acceptance, validation, promotion, projections, Git integration | Deterministic demo clean-replays and promotes only after an accepted-reference comparison; wrong references and tampering fail. Temporary-repository commits preserve unrelated staging. Live LAMMPS acceptance follows deployment |
| Review checkpoint | Record, reference, and recovery design review | Stop after Phase 3 for human review before continuing |
| 4. Staleness | Fingerprints, upstream checks, independent status flags, explicit revalidate/repair | A simulated observed environment change marks stale without submitting; `--revalidate` restores machine validity while preserving an upstream notice; transport failures do not trigger rebuilds |
| 5. Scaling | Study budget/occupancy enforcement, resumable run/report | Synthetic local 1/2/4-node study produces correct tables; over-budget studies submit nothing. The live study follows deployment |
| 6. Dashboard | Five static views | Views render offline from representative stored jobs/builds/validations/studies without a remote request |
| 7. Skills | Seven consistent SKILL.md files and finalized root rules | A fresh agent runs inspect-only check-software end to end and stops correctly on exit 20 without attempting authentication |
| 8. Second target | LAMMPS on Aurora, then a second scientific code | Both are added through the installation workflow and machine/record configuration without changing tool code |

## Verification strategy

- Run `pytest` and `ruff check` for the affected implementation phase; exercise Python 3.10 compatibility rather than assuming the workstation interpreter matches Crux.
- Test the JSON contract on success, usage errors, expected failures, subprocess diagnostics, and timeouts. Verify token/MFA material is not logged.
- Use recorded sanitized IRI/PBS responses plus injected failures for pagination, no jobs, malformed responses, held/suspended states, missing jobs, and colliding IDs across machines. A fake success path alone does not validate adapter parsing.
- Verify budget/account/queue/filesystem refusals occur before a submission, and unconfirmed cancellation of external jobs performs no cancellation.
- Inject failures before remote launch, after acceptance but before receipt storage, after result storage, and during projection/commit writing. Resume must not duplicate a job, build, audit event, or budget reservation.
- Verify candidate-reference extraction cannot authorize promotion, wrong accepted references fail scientifically, provenance changes invalidate evidence, and failed candidates preserve the current build.
- Verify machine and upstream stale flags are independent, no job is submitted by plain checks, and unavailable observations never claim freshness or trigger repair.
- Use synthetic strong/weak-scaling data to check throughput conversion, means, efficiency, missing/zero metrics, failed repeats, and missing baselines. Verify queue occupancy and total-study caps.
- Inspect all dashboard views from a populated fixture database, including escaped notes/job names, offline assets, stale observation timestamps, and partial studies.
- Live checks use the exact queues, accounts, paths, and limits confirmed in site notes. Sanitized live evidence is recorded separately from unit-test results.

Notes for the implementing agent:

- Phases 1 to 3 give a usable tool. Stop and ask for review after Phase 3, since the record format is the hardest part to change later.
- Label local adapter fixtures as synthetic; add sanitized real qstat/IRI responses during deployment acceptance.
- Anything in this plan that conflicts with the local site notes yields to the site notes; flag the conflict instead of working around it.

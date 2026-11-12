# Site verification: Phase 0

Prepared: 2026-11-11. Status: **pending human verification before live deployment; local development is authorized**.

This document accompanies [the implementation plan](../plan.md). The user changed
the approach to local development first and Crux deployment later. No existing
site results are available. This checklist gates live operation, not coding or
offline tests. Workstation observations do not establish Crux compute behavior. Do not check an item off without recording evidence and a human confirmer.

## Observations from this workstation

These read-only checks ran on 2026-11-11. They did not establish a connection,
authenticate, change SSH configuration, or submit jobs.

| Check | Observed result | What it establishes |
| --- | --- | --- |
| Workspace inventory | Only `plan.md` existed before this preparation | No package, tests, machine configuration, or site notes were present |
| `git status --short --branch` during review | Not a Git repository | Local initialization was attempted later; this workspace blocks `.git` writes. Git integration is tested in temporary repositories |
| Effective SSH configuration | Aliases `crux`, `polaris`, and `aurora` exist | Local alias availability only |
| `ssh -G crux` | Hostname `crux.alcf.anl.gov` | Local destination, not the route from a Crux compute node |
| `ssh -G polaris` | Hostname `polaris.alcf.anl.gov` | Local destination only |
| `ssh -G aurora` | Hostname `login.aurora.alcf.anl.gov` | Local destination only |
| Selected settings from all three aliases | `ControlMaster auto`, `ControlPersist no`, home-directory control paths; keepalive interval 30 seconds, count 100; no connection timeout | The future tool must explicitly configure its own bounded connections and node-local sockets |
| `ssh -O check -o BatchMode=yes -o ConnectTimeout=5 <alias>` for each alias | Exit 255: control socket does not exist | No reusable master at any of the three configured local paths |

The missing local sockets do not establish whether another workstation or a Crux
session has a connection. No remote observations have been made.

## Documentary starting points

Reviewed on 2026-11-11. Recheck these against actual access and scheduler settings.

| Topic | Documented expectation | Source |
| --- | --- | --- |
| IRI coverage | Aurora, Polaris, and Crux are listed as supported compute resources | [ALCF IRI guide](https://docs.alcf.anl.gov/services/iri-api/) |
| IRI authentication | Use `alcf-tokens login iri`, `test-token iri`, and the supported token retrieval integration; retrieval can refresh tokens | [ALCF IRI guide](https://docs.alcf.anl.gov/services/iri-api/) |
| IRI contract | API v2 has a published OpenAPI schema; verify resource identities and actual responses | [Deployed OpenAPI schema](https://api.alcf.anl.gov/api/v2/openapi.json) |
| Polaris pilot | `debug`: 1–2 nodes; `debug-scaling`: 1–10 nodes. Both list 5-minute minimum and 1-hour maximum walltimes. `debug-scaling` permits only one queued/accruing/running job per user | [Polaris queues](https://docs.alcf.anl.gov/polaris/running-jobs/) |
| Aurora pilot | `debug`: 1–2 nodes; `debug-scaling`: 2–256 nodes. Both list 5-minute minimum and 1-hour maximum walltimes and one queued/accruing/running job per user | [Aurora queues](https://docs.alcf.anl.gov/aurora/running-jobs-aurora/) |
| Aurora work directory | Submit from the allocated project directory | [Aurora jobs](https://docs.alcf.anl.gov/aurora/running-jobs-aurora/) |
| Crux controller lifetime | Limits depend on queue; `preemptable` can be terminated without warning | [Crux queues](https://docs.alcf.anl.gov/crux/queueing-and-running-jobs/running-jobs/) |
| PBS resources and output | Explicit walltime and filesystem resources are required; JSON and historical job queries are documented | [ALCF PBS guide](https://docs.alcf.anl.gov/running-jobs/) |
| Builds | Builds requiring GPU execution need compute nodes; login-node compilation must limit parallelism | [Polaris compilation](https://docs.alcf.anl.gov/polaris/compiling-and-linking/), [Aurora compilation](https://docs.alcf.anl.gov/aurora/compiling-and-linking/), [login-node limits](https://docs.alcf.anl.gov/dev-environment/) |
| SQLite storage | Network filesystem locking and sync semantics can compromise database durability; a passing smoke test alone is insufficient evidence | [SQLite network-filesystem guidance](https://www.sqlite.org/useovernet.html) |

IRI is the chosen default on both target machines. Do not use the obsolete
assumption that Aurora is unsupported to select a backend. PBS over SSH remains
an explicitly configured alternative, never an automatic retry path.

## Verification record

For every item, record the originating hostname and whether it was a login or
compute node, UTC time, command or site guidance, sanitized result, conclusion,
and human confirmer. Preserve failure evidence as well as successes. Do not
record tokens, MFA responses, authorization headers, or complete environments.

| ID | Required observation | Status | Evidence / human confirmer |
| --- | --- | --- | --- |
| S01 | Crux compute hostname, Python availability, actual hosting queue, requested/maximum walltime, and preemption behavior | Pending | — |
| S02 | Crux-compute-to-Polaris and Crux-compute-to-Aurora routes and working host aliases, including required jump hosts/tunnels | Pending | — |
| S03 | Human-established master connection on each target, working node-local socket, measured lifetime, and documented idle policy | Pending | — |
| S04 | Detached process/log/status survival across connection loss on each target | Pending | — |
| S05 | Durable repository and controller state paths, ownership, retention/backup policy, and availability in a replacement Crux job | Pending | — |
| S06 | Site-supported SQLite locking/sync behavior for the selected state filesystem and one-controller ownership procedure | Pending | — |
| S07 | Target software/source/job roots, filesystem names, login/compute visibility, and file-transfer method when mounts differ | Pending | — |
| S08 | Valid PBS JSON, empty-job behavior, full job IDs, historical queries, retention, and queue/account visibility on both targets | Pending | — |
| S09 | IRI resource IDs, authenticated list/status access on both targets, pagination, refresh, and unauthenticated/expired-token behavior from Crux | Pending | — |
| S10 | Outbound HTTPS/proxy behavior from Crux and target login/compute nodes; upstream/source access without exposing credentials | Pending | — |
| S11 | Actual allocations, allowed validation/scaling queues, node/walltime limits, user/project submission limits, and command budgets | Pending | — |
| S12 | Permitted build parallelism, available compiler/MPI/GPU modules, and whether the Polaris LAMMPS recipe can compile without executing on GPUs | Pending | — |

### Values to carry into machine configuration

These are deliberately unset. A local hostname or a documentation example is not
an approved account, filesystem, or remote root.

| Setting | Crux controller | Polaris | Aurora |
| --- | --- | --- | --- |
| Execution host / approved SSH route | Pending | Pending | Pending |
| Durable repository root | Pending | Not required to match Crux | Not required to match Crux |
| Durable state root and filesystem | Pending | Controller-only DB | Controller-only DB |
| SSH socket directory | Pending node-local path | Socket lives on Crux | Socket lives on Crux |
| IRI resource ID | Not a v1 job target | Pending | Pending |
| IRI/API connectivity from controller | Pending | Pending access verification | Pending access verification |
| Software / source / job roots | Not a v1 build target | Pending | Pending |
| Required filesystem resources | Hosting job: pending | Pending | Pending |
| Allocation / account | Pending | Pending | Pending |
| Validation queue and resources | Not applicable | Pending | Pending |
| Scaling queue and resources | Not applicable | Pending | Pending |
| Node-hours cap per command | Hosting allocation: pending | Pending | Pending |
| Proxy and no-proxy configuration | Pending | Pending by node role | Pending by node role |
| Build process/thread cap | Not applicable | Pending | Pending |

## Human-run collection procedure

The following is a runbook, not a report of commands already run remotely. A
human establishes authentication and obtains an authorized Crux compute
allocation using their normal site workflow. Direct site commands in this
bootstrap procedure are an exception to the operational CLI-only agent workflow;
agents still never authenticate. Local demo acceptance does not complete these checks.

### 1. Identify the controller context

Run inside the Crux compute allocation. If `PBS_JOBID` is absent, record that
fact and obtain the intended compute allocation before testing the route.

```sh
date -u
hostname -f
python3 --version
if [ -n "${PBS_JOBID:-}" ]; then
    qstat -f -F JSON "$PBS_JOBID"
fi
```

Record the hosting queue and inspect it with `qstat -Qf <actual-queue>`. Record
both the requested walltime and the queue limit. Do not equate a maximum walltime
with a guarantee against preemption or early termination.

### 2. Establish and observe the target connections

On Crux, first inspect `ssh -G polaris` and `ssh -G aurora`. Confirm that these
aliases exist there; the workstation configuration is not automatically shared.
Record only routing and connection settings, not private credentials.

After confirming `/tmp` is node-local, a human can create a dedicated master for
each target. Run this block once per machine, changing `task_machine` to
`aurora` for the second run. It can ask for MFA and is **human-only**.

```sh
task_machine=polaris
task_socket_dir="/tmp/hpctrack-$(id -u)"
install -d -m 700 "$task_socket_dir"
ssh -MNf -S "$task_socket_dir/$task_machine.sock" \
    -o ControlMaster=yes -o ControlPersist=3600 \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ConnectTimeout=10 "$task_machine"
```

Check reuse without initiating a new connection:

```sh
ssh -S "$task_socket_dir/$task_machine.sock" -O check "$task_machine"
ssh -T -S "$task_socket_dir/$task_machine.sock" \
    -o BatchMode=yes -o ControlMaster=no -o ProxyCommand=false \
    -o ConnectTimeout=10 "$task_machine" hostname -f
```

The disabled proxy command prevents direct-connection fallback if the master is
lost between the check and execution. Stop if a reuse check fails. Record the
elapsed lifetime and the site's idle/maximum-session policy separately: an
observation that a connection survived some interval does not prove its maximum
lifetime. Record any route that requires a tunnel and how a replacement Crux
job re-establishes it.

For S04, use a human-authorized, short detached probe in a dedicated target
scratch directory. Capture a log and an exit-status file, close only the dedicated
probe master, reconnect as a human, and inspect the result. Record all commands,
paths, and evidence. This tests disconnect survival; it does not establish
survival of a login-node reboot. Do not disturb existing production connections.

### 3. Record filesystem and build facts

On Crux and each target, inspect the candidate paths using `realpath`, `df -T`,
and `findmnt -T` where available. Record the mount identity, permissions, quota,
retention, and whether both login and compute nodes see the intended paths.
Record transfer requirements instead of assuming shared mounts.

For the controller state filesystem, obtain site guidance on locking, sync, and
SQLite support. Test rollback-journal transactions and process termination only
in a disposable directory authorized for that purpose. A smoke test supplements
site guidance; it does not establish reliable network filesystem semantics on
its own. Do not approve an unsuitable filesystem simply because one test passes.

Verify that a replacement Crux allocation can read the durable evidence. Confirm
the process for releasing ownership of the old controller before the new one
writes state. State must not depend on graceful shutdown of the old job.

For builds, record relevant modules, compiler/MPI/runtime versions, supported
Python, and a site-approved compilation parallelism cap. Confirm the proposed
LAMMPS build does not need GPU execution on a login node. A recipe requiring
compute-node compilation needs an explicit plan amendment before Phase 3.

### 4. Inspect scheduler configuration and existing jobs

Run on each target through an established connection or a human's existing
session. These commands inspect state; they do not submit or cancel jobs.

```sh
qstat -f -F JSON -u "$USER"
qstat -x -f -F JSON -u "$USER"
qstat -Qf debug
qstat -Qf debug-scaling
qstat -Bf
```

Record exit codes and stderr as well as stdout, especially if there are no jobs.
Validate captured JSON, retain full scheduler IDs, and sanitize other users' or
projects' details before committing fixtures. Confirm available accounts using
the site's account tools or IRI account endpoint. Record limits at both the user
and project level, required filesystem resources, and approved per-command caps.
Do not submit to queues merely because they appear in documentation.

### 5. Verify IRI and source-download access

From Crux, inspect the public resource listing with bounded HTTPS:

```sh
curl --fail --silent --show-error --connect-timeout 5 --max-time 30 \
    https://api.alcf.anl.gov/api/v2/status/resources
```

Match resource names and types to actual compute resources; record confirmed IDs
for Polaris and Aurora. A public listing alone does not prove account access.

In an existing environment containing the supported `alcf-tokens` tool, the human
authenticates when needed and tests access:

```sh
alcf-tokens login iri
alcf-tokens test-token iri
```

The login command is human-only. Never capture or paste token retrieval output.
Use the [IRI guide](https://docs.alcf.anl.gov/services/iri-api/) and deployed
OpenAPI schema to perform authenticated read-only list/status/account requests
with bounded timeouts; keep authorization headers out of captured evidence.
Record pagination and zero-job results for each target. Observe token refresh
and record the human reauthentication remedy when refresh is unavailable.
Credential refresh may update the external token store; credentials never belong
in this repository or the future hpctrack database.

Check access to GitHub/PyPI/source hosts from the actual execution locations and
record credential-free proxy/no-proxy settings. Do not dump the environment or
enable shell tracing around authenticated requests. Save sanitized response
fixtures in Phase 2; empty or failed access checks must be reported honestly.

Submission/cancellation smoke tests belong to Phase 2 after its resource limits
and allocations are configured. Phase 0 must not claim them as completed.

## Gate decision

- [ ] S01–S12 have evidence, dates, and human confirmation for every applicable node role and machine.
- [ ] Configuration values above are concrete, approved, and consistent with that evidence.
- [ ] The state filesystem and controller ownership procedure are suitable; unresolved durability concerns block live use.
- [ ] Any conflict with the plan is resolved explicitly, not hidden in an implementation workaround.
- [ ] A human confirms the completed record before enabling live machine configuration.

Human confirmer: **pending**  
Confirmation date: **pending**  
Decision: **Site verification incomplete; local development proceeds, live deployment remains gated.**

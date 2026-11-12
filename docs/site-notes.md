# Advisory site notes

Site observations help troubleshoot a personal installation. They are not an
approval gate: hpctrack uses explicit machine configuration and resource limits,
and accepts the legacy site_verified field without blocking execution.

Keep completed observations in the private records repository, alongside the
software record's NOTES.md. This public document contains guidance only, with
no captured site responses, personal paths, allocations or login configuration.

## What to record when useful

| Topic | Useful evidence |
| --- | --- |
| Execution context | Machine and node role, execution time, selected backend |
| Build environment | Compiler/module versions, applicable compilation limits |
| Filesystem behavior | Work/install visibility, state storage and controller ownership |
| Job behavior | Requested resources, scheduler status and exit code, log locations |
| Recovery | Existing operation ID, observed outcome, explicit intervention |

Label simulated fixtures as synthetic and distinguish observations from assumptions.
Do not claim that a passing demo establishes GPU execution, scientific accuracy,
or storage durability. Keep source snapshots and state available for resume.
SQLite storage and detached-worker behavior depend on the selected environment.

Agents use hpctrack for operational actions and never authenticate, handle MFA,
or invoke alcf-tokens login. Return the human remedy on exit 20. Never retry an
uncertain submission or silently switch backends. Keep tokens, credentials and
complete environments outside records and logs.

## Public reporting

Share only the minimum redacted outcome needed to reproduce a tool issue.
Raw doctor, sw show and job output can include identifying paths or job details.
Use synthetic fixtures for public tests. Keep scientific input data private unless
its owner has explicitly selected it for publication.

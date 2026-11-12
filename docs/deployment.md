# Deploying the local implementation to Crux

For the user-selected first installation from an existing Polaris session, follow
the [personal gRASPA pilot](graspa-pilot.md). Its local PBS and completion-validation
choices supersede the Crux/LAMMPS pilot sequence below for that installation only.

The current deliverable is the local Phase 3 milestone. Local tests do not establish
site compatibility or scientific validity. The [site notes](site-notes.md) are
advisory; there is no site-verification approval gate. Explicit machine configuration
and resource limits still apply. No site information is needed to develop or test the demo.

1. Copy the source checkout or a built wheel to persistent storage available from
   Crux. Create a Python 3.10+ environment. Install the package with the `iri` extra
   if using IRI, then run `hpctrack init --machines iri` (or `pbs-ssh`). Configuration,
   records, and state live in the workspace (`~/.hpctrack`, `HPCTRACK_HOME`, or
   `--workspace`), never inside the installed package.
2. Fill every `REPLACE_*` value in the workspace `hpctrack.yaml` with real usernames, IRI resource IDs, paths, allocations, required filesystems,
   queue limits, command budgets, and any credential-free HTTPS proxy URL.
   Example limits are illustrative, not an authorization to spend an allocation.
3. Choose a persistent state root with site-supported locking and durability.
   hpctrack uses SQLite rollback journaling, full sync, short transactions, and a
   controller file lock to serialize mutating commands. Confirm the shared
   filesystem supports those semantics. Read commands can inspect existing data
   while another command waits. Never copy a live database or share a state root
   between independent controllers without verifying ownership and storage.
4. Record useful site observations as needed. The legacy `site_verified` field is
   accepted but does not gate execution. Missing configuration produces an error, not a demo fallback.
   Do not copy demo state into live state. Use fresh live state and distinct roots.
5. A human runs `alcf-tokens login iri` in the intended environment and establishes
   SSH masters with `hpctrack connect MACHINE`.
   Control sockets are node-local. Credentials remain in the external token store.
6. Run `doctor`, then compare `jobs sync`/`jobs list --all` with site qstat output.
   Exercise a permitted trivial submission and cancellation. Capture sanitized
   real responses to extend the currently synthetic adapter fixtures.
7. Install a real record with a reviewed build recipe, validation input, and checker.
   The generic scaffold intentionally fails until completed. The first scientific
   acceptance target is LAMMPS on Polaris, followed by Aurora. Verify physical
   metrics and accelerator use, accept the reference as a human, run a new
   comparison, then promote and commit the record.

Build recipes receive `PREFIX`, immutable `SRC_REF`, `SRC_URL`, and `SRC_DIR`.
For Git sources, the recipe must fetch/check out `SRC_REF` into `SRC_DIR`; the tool
resolves and records the revision before launch. In-record `local` sources remain
demo-only. `working_tree` sources capture an absolute directory on the controller,
including local modifications, and supply a staged copy through `SRC_DIR`.
Validation templates receive `prefix`, `workdir`,
`input_dir`, `nodes`, and `source_ref`, with a `quote` shell-quoting filter. They
contain a shell body without PBS directives. The checker is called with the
output directory and, for comparisons, the accepted reference path. It must
print one JSON object and exit 0 or 1.

After losing a connection or reaching a wait timeout, a human restores credentials
as needed and runs `resume`. Do not issue another submission to compensate for
an uncertain receipt. Confirm detached worker behavior and recovery from Crux job
expiry during site acceptance. A live job absent from scheduler history remains
unknown; its absence is not evidence of successful completion.

Staleness commands, scaling, dashboard generation, and the seven operational skills
are deferred until the local Phase 3 review. They are not advertised as implemented.

## Personal records and public contributions

Keep the public tool checkout separate from a private records Git repository.
The existing `project_root` configuration selects the records repository;
`records_dir` and `state_dir` are relative to it. `sw promote` commits the selected
record in that repository. It does not push, but those commits can contain full
source paths and machine details. Keep the machine configuration private as well.

Public PRs should contain generic code, placeholder examples, and synthetic test
fixtures. Exclude personal configurations, records, source snapshots, scientific
inputs, logs, and raw `doctor`/`sw show` output. Review the staged diff and package
contents; `.gitignore` alone does not control which files go into a source package.
CI runs pytest and Ruff without HPC access. Live pilot validation stays local;
share only a redacted pass/fail summary if desired, without machine or account IDs.

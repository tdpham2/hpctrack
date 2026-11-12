# Deploying the local implementation to Crux

The current deliverable is the local Phase 3 milestone. Local tests do not establish
site compatibility or scientific validity. Complete the [site checklist](site-notes.md)
before enabling any live machine configuration. No site information is needed to
develop or test the demo.

1. Copy the source checkout or a built wheel to persistent storage available from
   Crux. Create a Python 3.10+ environment. Install the package with the `iri` extra
   if using IRI, and copy the example configuration separately when installing a
   wheel. Keep the configuration and records outside the installed package.
2. Copy `config/machines.example.yaml` to a private `config/machines.yaml` and fill
   in real usernames, IRI resource IDs, paths, allocations, required filesystems,
   queue limits, command budgets, and any credential-free HTTPS proxy URL.
   Example limits are illustrative, not an authorization to spend an allocation.
3. Choose a persistent state root with site-supported locking and durability.
   hpctrack uses SQLite rollback journaling, full sync, short transactions, and a
   controller file lock to serialize mutating commands. Confirm the shared
   filesystem supports those semantics. Read commands can inspect existing data
   while another command waits. Never copy a live database or share a state root
   between independent controllers without verifying ownership and storage.
4. Complete and human-confirm site facts, then set `site_verified: true` for each
   confirmed machine. Missing configuration produces an error, not a demo fallback.
   Do not copy demo state into live state. Use fresh live state and distinct roots.
5. A human runs `alcf-tokens login iri` in the intended environment and establishes
   SSH masters with `hpctrack --config config/machines.yaml connect MACHINE`.
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
resolves and records the revision before launch. Local source snapshots are only
supported by the demo. Validation templates receive `prefix`, `workdir`,
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

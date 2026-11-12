# Operating this hpctrack workspace

This directory is a per-user hpctrack workspace. `hpctrack.yaml` configures machines,
`records/<name>/<machine>/` holds software records, and `state/` (gitignored) holds the
authoritative SQLite ledger and immutable operation snapshots. The procedure for building
software is in `skills/build-software/SKILL.md`.

- Every remote action goes through `hpctrack`. Do not call `qsub`, `ssh`, or site APIs
  directly for work you want recorded.
- Never authenticate, handle MFA, or invoke `alcf-tokens login`. On exit 20 stop and return
  the `fix` field to the human.
- On exit 40 the work may still be running. Use `hpctrack resume --operation ID`; never
  resubmit an uncertain build, validation, or job.
- Use only the machine configuration and resource limits in `hpctrack.yaml` that the user
  approved. Never silently switch backends or machines.
- Keep credentials out of records, logs, command arguments, notes, and state.
- Record every intervention in the record's NOTES.md with `hpctrack sw note`.
- Only a human runs `hpctrack sw reference accept --yes`. Agents propose; humans accept.
- Evidence from the `demo` machine is simulated and validates nothing on a real system.

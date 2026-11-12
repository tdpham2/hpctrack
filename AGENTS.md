# Working on hpctrack

This repository is the tool. User data (configuration, records, ledger state) lives in
per-user workspaces created by `hpctrack init`; do not add personal records, machine
configuration, or state to this repository. Operating rules for agents that *use*
hpctrack ship in `src/hpctrack/templates/workspace/` (AGENTS.md and skills).

Local development is authorized without HPC access. Site notes are advisory;
there is no site-verification approval gate. Follow `plan.md`; stop for review
after the local Phase 3 record/validation/promotion milestone. Staleness, scaling,
dashboard, and the remaining operational skills follow that review.

- Exercise the tool locally in a disposable workspace
  (`HPCTRACK_HOME=$(mktemp -d)/ws hpctrack init --machines demo`). Demo evidence is
  simulated and does not validate LAMMPS, Polaris, or Aurora.
- Never authenticate, handle MFA, or invoke `alcf-tokens login`. Return the human
  remedy on exit 20. Isolated tests inject transports and HTTP clients.
- Use explicit machine configuration and user-approved resource limits for live
  jobs. Never retry an uncertain submission or silently switch backends.
- Keep credentials outside records, logs, command arguments, and state.
- Keep templates placeholder-only (`REPLACE_*`): no personal paths or allocations.
- Run relevant pytest checks and Ruff. Tests must not require network or HPC
  credentials. Never label synthetic fixtures as captured site responses.

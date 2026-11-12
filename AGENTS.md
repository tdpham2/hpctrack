# Working on hpctrack

Local development is authorized without HPC access. Site notes are advisory;
there is no site-verification approval gate. Follow `plan.md`; stop for review
after the local Phase 3 record/validation/promotion milestone. Staleness, scaling,
dashboard, and the seven operational skills follow that review.

- Use the explicit demo configuration for local exercises. Demo evidence is
  simulated and does not validate LAMMPS, Polaris, or Aurora.
- Never authenticate, handle MFA, or invoke `alcf-tokens login`. Return the human
  remedy on exit 20. Operational remote actions go through hpctrack; isolated
  tests inject transports and HTTP clients.
- Use explicit machine configuration and user-approved resource limits for live
  jobs. Never retry an uncertain submission or silently switch backends.
- Keep credentials outside records, logs, command arguments, and state.
- Keep personal machine configuration, records, inputs, snapshots and logs in a
  separate private project_root. Public examples and fixtures use placeholders
  or synthetic data. Never publish raw site output or automatically push records.
- Record interventions in a software record's `NOTES.md` when changing it.
- Run relevant pytest checks and Ruff. Tests must not require network or HPC
  credentials. Never label synthetic fixtures as captured site responses.

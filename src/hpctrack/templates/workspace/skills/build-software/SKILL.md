---
name: build-software
description: Build, repair, validate, and record an HPC software installation with hpctrack, recovering pending work before promoting a validated build.
---

# Build software with hpctrack

hpctrack runs immutable snapshots and records every attempt. Every command must
receive `HPCTRACK_ACTOR=agent`, `HPCTRACK_AGENT` (your agent name), and
`HPCTRACK_SESSION` (a short session identifier). These are identifiers, never credentials.
Set them in each command environment if your shell does not preserve exports.

Preserve the user's workspace selection and global options on every command. Run
`hpctrack workspace show` and read its absolute `operating_rules` path before operating.
Use `config`, `project`, `records`, and `state` from that response; the current
working directory is not necessarily the workspace. With legacy configuration and
no workspace rules, use the packaged operating rules supplied with this workflow.
Quote paths, including `--workspace "REPLACE_WORKSPACE"` or `--config "REPLACE_CONFIG"`.

Every command prints one JSON object. Read `ok`, `error`, `fix`, and `data`.

| Exit | Meaning | What to do |
|------|---------|------------|
| 0 | command succeeded | inspect evidence/state; this alone does not establish scientific validation |
| 1 | unexpected, transport, or service failure | inspect recorded state with `sw check`; resume pending IDs before any retry; report unresolved uncertainty |
| 2 | invalid command, configuration, or record | repair the reported input; do not assume earlier operations stopped |
| 10 | build or validation failed | inspect `log_tail` / `validation`, note the cause, repair, then check again |
| 20 | authentication needed | **stop**; return `fix` to the human; never authenticate |
| 30 | refused by policy | report the refusal; do not work around it or change attribution |
| 40 | pending, interrupted, or uncertain | resume the reported ID; if absent, use `sw check` to find matching pending IDs; **never resubmit** |

## Loop

1. **Inspect before initialization.** Use `hpctrack sw list` and
   `hpctrack sw show NAME --machine M`. For an existing record, inspect its notes,
   builds, validations, and `record_path`; continue with checking and repair.
   Only for a new record, inspect the absolute `records` directory from `workspace show`
   to ensure `NAME/M` does not already exist, then use `hpctrack templates list` and
   `hpctrack sw init NAME --machine M --template TEMPLATE`. If files already exist but
   the ledger lacks the record, report the inconsistency and preserve them; do not reinitialize.
2. **Check and recover first.** `hpctrack sw check NAME --machine M` reports
   `record_path`, `pending_operations`, `placeholders`, `rebuild_needed`,
   `revalidate_needed`, and `next_action`. If `next_action` is `resume`, run
   `hpctrack resume --operation ID` for each matching pending operation, then check
   again. A pending operation takes priority even if the recipe has since changed.
   Resume uses the saved snapshot; do not launch replacement work while it is unresolved.
3. **Fill or repair.** Edit the absolute `record_path` returned by `sw show`/`sw check`:
   `record.yaml`, `build.sh`, and `test/job.sh.j2`/`test/check.py`. If a malformed record
   prevents these commands, locate it beneath the returned `records` directory.
   Replace every `REPLACE_*` value using the user's configuration. Use only approved
   machines, queues, accounts, and resource limits. Note the intervention, then check again.
4. **Build when indicated.** `hpctrack sw build NAME --machine M`.
   On exit 10 (`build_failed`), read `log_tail.stdout` / `log_tail.stderr`, fix the recipe,
   and record the reason with `hpctrack sw note NAME --machine M --section
   "Failures and fixes" --message "..."`. Return to checking. On exit 40 resume;
   a timeout does not cancel work or authorize another launch.
5. **Validate when indicated.** `hpctrack sw validate NAME --machine M --build BUILD_ID`.
   In `reference` mode, `reference_pending` is a candidate, not passing evidence.
   Return the candidate metrics and `hpctrack sw reference accept NAME --machine M
   --validation ID --yes` to the human for review and execution. Never run acceptance
   or unset agent attribution yourself. After human acceptance, validate again for
   a passing comparison. In `completion` mode, a passing checker establishes completion
   only; it does not demonstrate agreement with a scientific reference. On exit 10,
   inspect evidence, note whether the build or test needs repair, and return to checking.
6. **Promote when indicated.** `hpctrack sw promote NAME --machine M --build BUILD_ID`
   commits the record to the workspace Git repository. Resume any pending promotion
   instead of rebuilding/revalidating. Use `--no-commit` only for an explicitly disposable
   non-Git demo. When `next_action` is `none`, report the existing evidence without rebuilding.
7. **Report.** `hpctrack sw history NAME --machine M` returns the attributed ledger.
   Explain the resulting state, validation mode, and whether evidence is simulated.

Record every intervention using `sw note` under the matching NOTES.md section:
`Environment`, `Build decisions`, `Failures and fixes`, `Known issues`, `Validation`,
`Change log`. Do not edit `manifest.json`, `history.jsonl`, or `test/reference.json`
by hand. Never authenticate, silently switch backends, or resubmit uncertain work.
Keep credentials outside records, notes, command arguments, logs, and state.

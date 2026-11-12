---
name: build-software
description: Build, validate, and record a software installation on an HPC machine with hpctrack, iterating on the build recipe until a validated build can be promoted.
---

# Build software with hpctrack

hpctrack is the ledger. You write the recipe and the test; hpctrack runs them from immutable
snapshots and records every attempt with your identity. Set `HPCTRACK_ACTOR=agent`, and set
`HPCTRACK_AGENT` (your name) and `HPCTRACK_SESSION` (a short session id), so ledger entries
are attributed. These are identifiers, never credentials.

Every command prints one JSON object. Read `ok`, `error`, `fix`, and `data`.

| Exit | Meaning | What to do |
|------|---------|------------|
| 0 | success | continue |
| 2 | invalid input or record | fix the input; nothing ran |
| 10 | the build or validation failed | read `log_tail` / `validation`, fix, note, retry |
| 20 | authentication needed | **stop**; return `fix` to the human |
| 30 | refused by policy | do not work around it; report it |
| 40 | still pending or uncertain | `hpctrack resume --operation ID`; **never resubmit** |

## Loop

1. **Start from a template.** `hpctrack templates list`, then
   `hpctrack sw init NAME --machine M --template TEMPLATE`.
2. **Fill the record.** Edit `records/NAME/M/record.yaml`, `build.sh`, and
   `test/job.sh.j2`/`test/check.py`. Replace every `REPLACE_*` value. Use only queues,
   accounts, and limits that the user approved in `hpctrack.yaml`.
3. **Check offline.** `hpctrack sw check NAME --machine M` reports `placeholders`,
   `rebuild_needed`, `revalidate_needed`, and `next_action`. Do this before spending allocation.
4. **Build.** `hpctrack sw build NAME --machine M`.
   - On exit 10 (`build_failed`), read `log_tail.stdout` / `log_tail.stderr`, fix `build.sh`,
     then record what you learned:
     `hpctrack sw note NAME --machine M --section "Failures and fixes" --message "..."`.
     Go back to step 3.
   - On exit 40, resume the reported operation. Do not start a new build.
5. **Validate.** `hpctrack sw validate NAME --machine M --build BUILD_ID`.
   - In `reference` mode, the first run produces a `reference_pending` candidate. Stop and ask
     a human to review its metrics and run
     `hpctrack sw reference accept NAME --machine M --validation ID --yes`. Then validate again.
   - In `completion` mode, a passing checker is enough.
   - On exit 10, decide whether the build or the test is wrong, note it, and fix it.
6. **Promote.** `hpctrack sw promote NAME --machine M --build BUILD_ID` commits the record
   (manifest, NOTES.md, history.jsonl) to the workspace Git repository.
7. **Report.** `hpctrack sw history NAME --machine M` returns the attributed ledger.

Record build decisions and environment findings with `sw note` under the matching section
(`Environment`, `Build decisions`, `Failures and fixes`, `Known issues`, `Validation`,
`Change log`). Do not edit `manifest.json`, `history.jsonl`, or `test/reference.json` by
hand; hpctrack projects them from the ledger and refuses tampered evidence.

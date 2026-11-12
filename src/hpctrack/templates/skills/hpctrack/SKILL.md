---
name: hpctrack
description: Inspect, build, repair, validate, and promote HPC software records through the hpctrack JSON CLI. Use for hpctrack workspace and recorded installation tasks.
---

# hpctrack

Use the installed `hpctrack` CLI for the user's selected workspace. This skill does
not install the CLI, initialize a workspace, or authorize live resource use by itself.

Before every command, ensure its environment includes `HPCTRACK_ACTOR=agent`,
`HPCTRACK_AGENT` (claude, codex, opencode, or pi), and `HPCTRACK_SESSION` (a short,
non-secret session identifier). Keep these values across commands, including recovery.
Do not switch to human attribution to bypass a refusal.

1. Run `hpctrack workspace show`, preserving the user's global `--workspace`,
   `--config`, and `--state-dir` options on every command. Global options precede
   subcommands. Workspace selection is `--workspace` > `HPCTRACK_HOME` > `~/.hpctrack`;
   `--config` overrides the configuration file. Quote paths containing spaces.
2. Read the selected workspace's `operating_rules` path from that JSON output;
   do not assume the current directory or this installed skill is the workspace.
   If rules are absent (for example with a legacy `--config`), report that and read
   [the packaged operating rules](references/AGENTS.md). For a missing workspace,
   report the remedy; initialize only when requested, with the selected machine
   template. `demo` is simulated and cannot validate real software or an HPC site.
3. Read [the build and recovery workflow](references/build-software.md). Inspect
   existing records before `sw init`. Use returned absolute paths when editing.
   Resume matching pending operations before considering another build or validation.

All commands return a JSON envelope. Command success does not mean scientific
validation; inspect the evidence and validation mode. Return authentication remedies
to the human on exit 20; never authenticate or accept references as an agent.

# Portable hpctrack agent skill

Install the wheel to make `hpctrack` available on the agent's PATH:

```sh
uv tool install ./dist/hpctrack-0.1.0-py3-none-any.whl
hpctrack skills install --agent all --dry-run
hpctrack skills install --agent all
hpctrack skills status
```

For an activated Python environment, `uv pip install ./dist/hpctrack-0.1.0-py3-none-any.whl`
is also supported. Use that environment when launching the agent. Bare-name package
installation requires a later package-index release. Installing the package does not
install a skill automatically. No agent executable, network, workspace, or ledger is
needed for `skills install` or `skills status`.

## Locations and invocation

| `--agent` | User-wide destination | Invocation in the host |
| --- | --- | --- |
| `claude` | `~/.claude/skills/hpctrack/` | `/hpctrack` |
| `codex` | `~/.agents/skills/hpctrack/` | `$hpctrack` |
| `opencode` | `~/.agents/skills/hpctrack/` | Ask to use the hpctrack skill |
| `pi` | `~/.agents/skills/hpctrack/` | `/skill:hpctrack` |

`--agent all` writes the two distinct directories once, with identical contents.
The installer leaves global instructions and permission settings untouched. The
entrypoint uses common skill frontmatter (`name`, `description`) and relative
references; there are no host-specific tool permissions, hooks, or orchestration.

These mappings follow the documented discovery locations for
[Claude Code](https://code.claude.com/docs/en/skills),
[Codex](https://learn.chatgpt.com/docs/build-skills),
[OpenCode](https://opencode.ai/docs/skills/), and
[Pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md).
Discovery and configuration can vary by host version.

## Managed updates and conflicts

The installed `.hpctrack-skill.json` records the hpctrack version and SHA-256 hash
of each managed file. `skills status` returns both destinations and their agent aliases:

| Status | Meaning |
| --- | --- |
| `missing` | No installation (or an empty destination) |
| `outdated` | Managed files are intact but differ from this package's version or resources |
| `modified` | A managed file is edited/deleted, metadata is invalid, or an unmanaged collision exists |
| `current` | Version and managed contents match the installed Python package |

After upgrading the wheel, rerun `hpctrack skills install --agent all`. Repeated
installation is a no-op for current files. Upgrades replace unchanged managed files,
add new files, and remove retired managed files. Unrelated extra files in a managed
directory remain untouched; a new package file colliding with one is refused.
Existing nonempty directories without the hpctrack manifest are also refused, even
when their content happens to match. Symlinks beneath the home directory are refused.

`--dry-run` reports the same proposed create/update/remove actions without writing.
Reported status describes the installation before these actions; rerun `skills status`
to inspect the result. Conflicts return JSON `skill_conflict` with exit 30, including
in dry runs. All selected destinations are checked before any changes. Back up and
review conflicts, then move the entire conflicting skill directory aside to reinstall
cleanly. Restore only intentional local additions afterward. There is no force overwrite.
If an I/O failure interrupts installation, inspect status and preserve conflicts before
reinstalling; the installer does not silently discard partially written files.

The supporting references are copied directly from the packaged workspace templates.
The existing `skills/build-software/SKILL.md` workspace path remains available. Package
upgrades and user-wide installation do not overwrite existing workspace rules or skills;
review any local workspace differences explicitly.

## Workspace selection and operation

```sh
hpctrack init --machines demo
hpctrack --workspace "/path/with spaces/workspace" workspace show
```

Use `--workspace DIR`, otherwise `HPCTRACK_HOME`, otherwise `~/.hpctrack`.
The advanced `--config FILE` takes precedence over workspace configuration;
`project_root` and record/state paths retain their configuration semantics.
`--state-dir DIR` overrides the state location. Global options precede subcommands.
`workspace show` reads configuration only, returns absolute paths including
`operating_rules`, and never creates a ledger or contacts a backend. Missing or
invalid configuration remains an error, without fallback to demo.

The agent reads the selected workspace's rules even when launched elsewhere. It
inspects existing records and uses `sw init` only for new records. It edits the
absolute `record_path` from `sw show` or `sw check`, records interventions through
`sw note`, and resumes the IDs in `pending_operations` before starting another attempt.
Every command includes `HPCTRACK_ACTOR=agent`, `HPCTRACK_AGENT`, and `HPCTRACK_SESSION`.
The CLI enforces human-only authentication and reference acceptance. On exit 20 the
agent returns the human remedy. Exit 1 may follow a launch; inspect state before retrying.

A zero exit code means the command succeeded. A reference candidate still needs human
acceptance and another passing comparison; completion mode establishes completion,
not scientific reference agreement. Demo evidence is simulated and does not validate
LAMMPS, Polaris, Aurora, or any real scientific installation. Live resource limits and
machine configuration must come from the user. Never resubmit uncertain work or silently
switch backends.

## Host discovery checks

Filesystem and wheel tests verify packaging and installation, not actual host behavior.
No interactive host compatibility was manually verified for this change; no host versions
are claimed. To verify a host locally:

1. Record its version using `claude --version`, `codex --version`, `opencode --version`,
   or `pi --version`, along with OS and date. Verify `hpctrack --version` on that host's PATH.
2. Start a fresh host session outside the repository. Confirm it lists or loads `hpctrack`
   using the invocation above (Codex also exposes `/skills`). Check the loaded file path,
   especially if another skill with the same name exists.
3. Ask it to inspect a disposable demo workspace from an unrelated directory. Confirm it
   reads that workspace's operating rules and follows the bundled workflow references.
4. Check its command environment includes agent and session attribution. Test pending
   operation recovery with demo evidence only. Confirm that it returns authentication
   remedies and reference candidates to the human.
5. Record the actual version, loaded path, and observed results. A discovered skill alone
   does not prove that the host follows every workflow rule. Do not relax global permissions
   merely to make this test pass.

The CI smoke test installs a freshly built wheel into an isolated environment and runs
`scripts/wheel_smoke.py` outside the checkout. It verifies packaged references, both skill
destinations, dry runs, status, workspace inspection, and demo record initialization.
Public publishing, marketplace plugins, MCP, cross-agent orchestration, and the deferred
post-Phase-3 operational features remain separate work.

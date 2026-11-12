"""Explicit, offline installation of the portable skill from package resources."""

import json
import re
from pathlib import Path, PurePosixPath

from hpctrack import __version__
from hpctrack.config import templates
from hpctrack.errors import TrackError
from hpctrack.util import atomic_write, digest, write_json

MANIFEST = ".hpctrack-skill.json"
DESTINATIONS = {
    "claude": ".claude/skills/hpctrack",
    "codex": ".agents/skills/hpctrack",
    "opencode": ".agents/skills/hpctrack",
    "pi": ".agents/skills/hpctrack",
}


def packaged_files():
    """Workspace procedures remain the maintained source for both installations."""
    source = templates()
    return {
        "SKILL.md": (source / "skills/hpctrack/SKILL.md").read_bytes(),
        "references/AGENTS.md": (source / "workspace/AGENTS.md").read_bytes(),
        "references/build-software.md": (
            source / "workspace/skills/build-software/SKILL.md"
        ).read_bytes(),
    }


def _manifest(files):
    return {
        "schema_version": 1,
        "package": "hpctrack",
        "version": __version__,
        "files": {name: digest(content) for name, content in sorted(files.items())},
    }


def _load_manifest(path):
    try:
        manifest = json.loads(path.read_text())
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("package") != "hpctrack"
            or not isinstance(manifest.get("version"), str)
            or not isinstance(manifest.get("files"), dict)
            or "SKILL.md" not in manifest["files"]
        ):
            return None
        for name, sha in manifest["files"].items():
            relative = PurePosixPath(name)
            if (
                not relative.parts
                or "\x00" in name
                or relative.is_absolute()
                or relative.as_posix() != name
                or ".." in relative.parts
                or "\\" in name
                or MANIFEST in relative.parts
                or not isinstance(sha, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
            ):
                return None
        return manifest
    except (OSError, ValueError, TypeError):
        return None


def _blocked_path(path, home):
    """Do not follow skill-directory links or replace a non-directory ancestor."""
    for parent in (path, *path.parents):
        if parent == home:
            break
        if parent.is_symlink() or (parent != path and parent.exists() and not parent.is_dir()):
            return True
    return False


def _inspect(path, home, expected):
    report = {
        "path": str(path),
        "agents": [agent for agent, relative in DESTINATIONS.items() if home / relative == path],
        "status": "missing",
        "installed_version": None,
        "changes": [],
        "conflicts": [],
    }
    if _blocked_path(path, home) or (path.exists() and not path.is_dir()):
        report.update(status="modified", conflicts=[str(path)])
        return report
    previous = None
    manifest_path = path / MANIFEST
    if manifest_path.exists() or manifest_path.is_symlink():
        if not manifest_path.is_symlink() and manifest_path.is_file():
            previous = _load_manifest(manifest_path)
        if previous is None:
            report.update(status="modified", conflicts=[MANIFEST])
            return report
    elif path.exists() and any(path.iterdir()):
        report.update(status="modified", conflicts=["unmanaged_directory"])
        return report

    old_files = previous["files"] if previous else {}
    report["installed_version"] = previous["version"] if previous else None
    for name, sha in old_files.items():
        installed = path / name
        if (
            _blocked_path(installed, home)
            or not installed.is_file()
            or digest(installed.read_bytes()) != sha
        ):
            report["conflicts"].append(name)
    for name in expected["files"]:
        installed = path / name
        if name not in old_files and (_blocked_path(installed, home) or installed.exists()):
            report["conflicts"].append(name)
    if report["conflicts"]:
        report["status"] = "modified"
        return report
    if previous:
        report["status"] = "current" if previous == expected else "outdated"
    for name, sha in expected["files"].items():
        if old_files.get(name) != sha:
            report["changes"].append(
                {"path": name, "action": "update" if name in old_files else "create"}
            )
    for name in sorted(old_files.keys() - expected["files"].keys()):
        report["changes"].append({"path": name, "action": "remove"})
    if previous != expected:
        report["changes"].append({"path": MANIFEST, "action": "update" if previous else "create"})
    return report


def _reports(agent, expected):
    if agent != "all" and agent not in DESTINATIONS:
        raise TrackError("invalid_agent", "Unknown agent", 2)
    home = Path.home().resolve()
    destinations = dict.fromkeys(DESTINATIONS.values() if agent == "all" else [DESTINATIONS[agent]])
    return [_inspect(home / relative, home, expected) for relative in destinations]


def status():
    return {"version": __version__, "destinations": _reports("all", _manifest(packaged_files()))}


def install(agent, dry_run=False):
    files = packaged_files()
    manifest = _manifest(files)
    reports = _reports(agent, manifest)
    result = {"version": __version__, "dry_run": dry_run, "destinations": reports}
    # Check all destinations first so a conflict in one cannot partially install --agent all.
    if any(report["conflicts"] for report in reports):
        raise TrackError(
            "skill_conflict",
            "Refusing to overwrite edited or unmanaged skill files",
            30,
            **result,
            fix="Review and back up the conflicting files, then move them aside and rerun installation",
        )
    if not dry_run:
        for report in reports:
            destination = Path(report["path"])
            for change in report["changes"]:
                name = change["path"]
                if name == MANIFEST:
                    write_json(destination / name, manifest)
                elif change["action"] == "remove":
                    (destination / name).unlink()
                else:
                    atomic_write(destination / name, files[name])
    return result

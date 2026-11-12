import json
import math
import subprocess
from pathlib import Path

import yaml
from pydantic import ValidationError

from hpctrack.errors import TrackError
from hpctrack.models import Record
from hpctrack.util import atomic_write, digest, read_tree, tree_hash, write_json

HEADINGS = [
    "Environment",
    "Build decisions",
    "Failures and fixes",
    "Known issues",
    "Validation",
    "Change log",
]


def load_record(path):
    try:
        record = Record.model_validate(yaml.safe_load((path / "record.yaml").read_text()))
        for required in ("build.sh", "test/job.sh.j2", "test/check.py", "NOTES.md"):
            if not (path / required).is_file():
                raise ValueError(f"Missing {required}")
        notes = (path / "NOTES.md").read_text()
        positions = [notes.find("## " + heading) for heading in HEADINGS]
        if any(index < 0 for index in positions) or positions != sorted(positions):
            raise ValueError("NOTES.md headings are missing or out of order")
        read_tree(path)  # Refuse symlinked inputs before reading or staging them.
        return record
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise TrackError(
            "invalid_record",
            "Record is missing required files or has invalid declarations",
            2,
            path=str(path),
        ) from exc


def placeholders(path):
    """Return record inputs that still contain template REPLACE_* values."""
    return [
        name
        for name in ("record.yaml", "build.sh", "test/job.sh.j2")
        if "REPLACE_" in (path / name).read_text(errors="replace")
    ]


def require_filled(path):
    found = placeholders(path)
    if found:
        raise TrackError(
            "record_placeholders",
            "Fill every REPLACE_* value in the record before running it",
            2,
            files=found,
        )


def add_note(path, message, heading, stamp):
    """Insert a dated entry at the end of one NOTES.md section, preserving heading order."""
    if heading not in HEADINGS:
        raise TrackError("invalid_section", "Unknown NOTES.md section", 2, sections=HEADINGS)
    notes = (path / "NOTES.md").read_text()
    start = notes.find("## " + heading)
    following = [notes.find("\n## " + h, start) for h in HEADINGS[HEADINGS.index(heading) + 1 :]]
    end = min([index for index in following if index >= 0], default=len(notes))
    entry = f"- {stamp}: " + " ".join(message.split())
    section = notes[start:end].rstrip("\n")
    if "\n" not in section:
        section += "\n"  # Keep a blank line below a bare heading.
    atomic_write(path / "NOTES.md", notes[:start] + section + "\n" + entry + "\n" + notes[end:])
    return entry


def contract_hash(path, record):
    files = read_tree(path / "test")
    files.pop("reference.json", None)
    contract = {
        "test": tree_hash(files),
        "metrics": record.metrics,
        "resources": record.validation.model_dump(),
    }
    # Preserve hashes for existing reference records.
    if record.validation_mode != "reference":
        contract["validation_mode"] = record.validation_mode
    return digest(contract)


def capture_working_tree(source, destination):
    root = Path(source.url)
    if not root.is_dir():
        raise TrackError("invalid_source", "Working-tree source directory does not exist", 2)
    files = read_tree(root, exclude=(".git", *source.exclude))
    if not files:
        raise TrackError("invalid_source", "Working-tree snapshot contains no files", 2)
    executables = []
    source_files = {}
    for name, content in files.items():
        atomic_write(destination / name, content)
        source_files[name] = {
            "original_path": str(root / name),
            "snapshot_path": str(destination / name),
            "sha256": digest(content),
        }
        if (root / name).stat().st_mode & 0o111:
            executables.append(name)
    # Git is optional; content hashes, not repository cleanliness, identify the build.
    commit = None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "source_snapshot": str(destination),
        "source_ref": tree_hash(files),
        "source_commit": commit,
        "source_executables": executables,
        "source_files": source_files,
    }


def init_record(path, machine, template=None):
    if path.exists():
        raise TrackError("record_exists", "Refusing to overwrite an existing record", 30)
    if template:
        template = Path(template).resolve()
        load_record(template)
        files = read_tree(template)
        path.mkdir(parents=True)
        for name, content in files.items():
            if name not in ("manifest.json", "history.jsonl", "test/reference.json"):
                atomic_write(path / name, content)
    else:
        path.mkdir(parents=True)
        queue_name, queue = next(iter(machine.queues.items()))
        data = {
            "schema_version": 1,
            "source": {"type": "git", "url": "https://example.invalid/replace-me", "ref": "HEAD"},
            "validation": {
                "nodes": queue.min_nodes,
                "walltime": queue.min_walltime,
                "queue": queue_name,
                "account": machine.accounts[0],
            },
            "metrics": {"result": 0.000001},
            "environment_probes": {},
        }
        atomic_write(path / "record.yaml", yaml.safe_dump(data, sort_keys=False))
        atomic_write(
            path / "build.sh",
            '#!/bin/bash\nset -eu\necho "Write and review a build recipe" >&2\nexit 1\n',
        )
        atomic_write(
            path / "NOTES.md",
            "# Software record\n\n" + "\n\n".join("## " + h for h in HEADINGS) + "\n",
        )
        atomic_write(
            path / "test/job.sh.j2",
            'echo "Write and review a scientific calculation" >&2\nexit 1\n',
        )
        atomic_write(
            path / "test/check.py",
            'import json\nprint(json.dumps({"passed": False, "metrics": {}, "messages": ["Checker not implemented"]}))\nraise SystemExit(1)\n',
        )


def validate_metrics(metrics, tolerances):
    if not isinstance(metrics, dict):
        raise TrackError("invalid_metrics", "Checker metrics must be an object", 10)
    for key in tolerances:
        value = metrics.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise TrackError(
                "invalid_metrics", f"Required metric {key} is missing or nonfinite", 10
            )


def compare(metrics, reference):
    for key, entry in reference["metrics"].items():
        if abs(metrics[key] - entry["value"]) > entry["absolute_tolerance"]:
            return False
    return True


def snapshot(path, destination):
    files = read_tree(path)
    for name, content in files.items():
        if name not in ("manifest.json", "history.jsonl"):
            atomic_write(destination / name, content)
    return destination


def project_record(settings, store, name, machine):
    key = f"{name}/{machine}"
    record = store.get("record", key)
    if not record:
        raise TrackError("unknown_record", "Record has not been initialized", 2)
    path = settings.record_path(name, machine)
    manifest = {
        "schema_version": 1,
        **record,
        "builds": [b for b in store.all("build") if b["record_key"] == key],
        "validations": [v for v in store.all("validation") if v["record_key"] == key],
    }
    reference = store.get("reference", key)
    if reference:
        manifest["accepted_reference_hash"] = digest(reference)
        write_json(path / "test/reference.json", reference)
    write_json(path / "manifest.json", manifest)
    atomic_write(
        path / "history.jsonl",
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in store.history(key)),
    )
    return manifest


def check_reference_file(path, reference):
    if reference is None:
        if (path / "test/reference.json").exists():
            raise TrackError("reference_unaccepted", "Reference file has no acceptance record", 30)
        return
    try:
        content = json.loads((path / "test/reference.json").read_text())
    except (OSError, ValueError) as exc:
        raise TrackError(
            "reference_changed", "Accepted reference file is missing or malformed", 30
        ) from exc
    if content != reference:
        raise TrackError("reference_changed", "Reference file differs from accepted evidence", 30)


def commit_record(root, path, operation_id, name):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30
        )

    check = git("rev-parse", "--show-toplevel")
    if check.returncode:
        raise TrackError(
            "git_required",
            "Promotion is recorded but its Git commit is pending. "
            "Initialize Git and resume; use --no-commit explicitly for a non-Git demo.",
            30,
        )
    try:
        relative = path.resolve().relative_to(Path(check.stdout.strip()).resolve()).as_posix()
    except ValueError as exc:
        raise TrackError(
            "git_record_outside", "Record must be inside the Git worktree", 30
        ) from exc
    previous = git(
        "log", "-1", "--format=%H", "--fixed-strings", f"--grep=hpctrack-operation:{operation_id}"
    )
    if previous.returncode == 0 and previous.stdout.strip():
        return previous.stdout.strip()
    if git("add", "--", relative).returncode:
        raise TrackError("git_failed", "Could not stage the selected software record", 30)
    message = f"hpctrack: promote {name}\n\nhpctrack-operation:{operation_id}"
    # --only commits the selected record and preserves unrelated staged changes.
    result = git("commit", "--only", "-m", message, "--", relative)
    if result.returncode:
        raise TrackError(
            "git_failed", "Record commit failed; configure Git identity and resume", 30
        )
    return git("rev-parse", "HEAD").stdout.strip()

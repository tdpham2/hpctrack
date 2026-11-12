import os
import shlex
import subprocess
from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from hpctrack.errors import TrackError
from hpctrack.models import Config
from hpctrack.util import atomic_write, identifier, within

CONFIG_NAME = "hpctrack.yaml"


def resolve_workspace(workspace=None):
    """Return the data home: --workspace, then $HPCTRACK_HOME, then ~/.hpctrack."""
    value = workspace or os.environ.get("HPCTRACK_HOME") or Path.home() / ".hpctrack"
    return Path(value).expanduser().resolve()


def workspace_config(workspace=None):
    root = resolve_workspace(workspace)
    path = root / CONFIG_NAME
    if not path.is_file():
        raise TrackError(
            "workspace_missing",
            "No hpctrack workspace found",
            2,
            workspace=str(root),
            fix=f"hpctrack --workspace {shlex.quote(str(root))} init --machines demo",
        )
    return path


def templates():
    return resources.files("hpctrack") / "templates"


def template_names(kind):
    return sorted(
        item.name.removesuffix(".yaml")
        for item in (templates() / kind).iterdir()
        if not item.name.startswith((".", "_"))
    )


def record_template(value):
    """Resolve a packaged record template name, otherwise treat the value as a path."""
    if value is None:
        return None
    if value in template_names("records"):
        return Path(str(templates() / "records" / value))
    path = Path(value).expanduser()
    if not path.is_dir():
        raise TrackError(
            "unknown_template",
            "Template is neither a packaged name nor a directory",
            2,
            available=template_names("records"),
        )
    return path


def _copy_template(source, destination):
    if source.is_dir():
        for item in source.iterdir():
            if item.name != "__pycache__":
                _copy_template(item, destination / item.name)
    else:
        atomic_write(destination, source.read_bytes())


def init_workspace(workspace=None, machines="demo", git=True):
    """Create a self-contained data home from packaged templates; never overwrite one."""
    root = resolve_workspace(workspace)
    if machines not in template_names("machines"):
        raise TrackError(
            "unknown_template", "Unknown machine template", 2, available=template_names("machines")
        )
    if (root / CONFIG_NAME).exists() or (root.is_dir() and any(root.iterdir())):
        raise TrackError(
            "workspace_exists",
            "Refusing to initialize a non-empty directory",
            30,
            workspace=str(root),
        )
    source = templates()
    atomic_write(root / CONFIG_NAME, (source / "machines" / f"{machines}.yaml").read_bytes())
    for item in (source / "workspace").iterdir():
        name = ".gitignore" if item.name == "gitignore" else item.name
        _copy_template(item, root / name)
    (root / "records").mkdir(exist_ok=True)
    result = {"workspace": str(root), "config": str(root / CONFIG_NAME), "git": False}
    if git:
        completed = subprocess.run(
            ["git", "init", "-q", "-b", "main", str(root)], capture_output=True, timeout=30
        )
        result["git"] = completed.returncode == 0
    content = (root / CONFIG_NAME).read_text()
    result["placeholders"] = "REPLACE_" in content
    if result["placeholders"]:
        result["fix"] = f"Fill every REPLACE_* value in {root / CONFIG_NAME}, then run doctor"
    return result


class Settings:
    def __init__(self, path, state_dir=None):
        path = Path(path).resolve()
        self.path = path
        try:
            self.config = Config.model_validate(yaml.safe_load(path.read_text()))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise TrackError(
                "invalid_config",
                "Cannot load configuration; fill every REPLACE_* value in the "
                "workspace hpctrack.yaml",
                2,
                path=str(path),
                reason=type(exc).__name__,
            ) from exc
        self.root = (path.parent / self.config.project_root).resolve()
        self.records = (self.root / self.config.records_dir).resolve()
        self.state = (
            Path(state_dir).resolve()
            if state_dir
            else (self.root / self.config.state_dir).resolve()
        )
        configured_state = (self.root / self.config.state_dir).resolve()
        if state_dir and configured_state in self.records.parents:
            self.records = self.state / self.records.relative_to(configured_state)
        for name in self.config.machines:
            identifier(name)

    def machine(self, name, live=False):
        if name not in self.config.machines:
            raise TrackError("unknown_machine", f"Unknown machine: {name}", 2)
        machine = self.config.machines[name].model_copy(deep=True)
        if machine.backend == "fake":
            machine.software_root = str(within(self.state, self.state / machine.software_root))
            machine.work_root = str(within(self.state, self.state / machine.work_root))
        return machine

    def record_path(self, name, machine):
        self.machine(machine)
        return within(self.records, self.records / identifier(name) / identifier(machine))

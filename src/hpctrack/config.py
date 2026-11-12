from pathlib import Path

import yaml
from pydantic import ValidationError

from hpctrack.errors import TrackError
from hpctrack.models import Config
from hpctrack.util import identifier, within


class Settings:
    def __init__(self, path, state_dir=None):
        path = Path(path).resolve()
        try:
            self.config = Config.model_validate(yaml.safe_load(path.read_text()))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise TrackError(
                "invalid_config",
                "Cannot load configuration; use the explicit demo "
                "config or fill config/machines.example.yaml",
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

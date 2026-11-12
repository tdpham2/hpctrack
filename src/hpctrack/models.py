import os
import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Queue(Model):
    min_nodes: int = Field(default=1, ge=1)
    max_nodes: int = Field(ge=1)
    min_walltime: int = Field(default=1, ge=1)
    max_walltime: int = Field(ge=1)
    max_active: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def limits(self):
        if self.min_nodes > self.max_nodes or self.min_walltime > self.max_walltime:
            raise ValueError("queue minimum exceeds maximum")
        return self


class Machine(Model):
    backend: Literal["fake", "iri", "pbs_ssh", "pbs_local"]
    transport: Literal["local", "ssh"]
    ssh_alias: str | None = None
    resource_id: str | None = None
    api_url: str = "https://api.alcf.anl.gov/api/v2"
    software_root: str
    work_root: str
    queues: dict[str, Queue]
    accounts: list[str]
    filesystems: list[str] = Field(min_length=1)
    max_node_hours: float = Field(gt=0)
    max_nodes: int = Field(ge=1)
    max_walltime: int = Field(ge=1)
    user: str | None = None
    proxy: str | None = None
    site_verified: bool = False  # Legacy configuration field; does not gate execution.

    @field_validator("software_root", "work_root", "user", mode="before")
    @classmethod
    def expand(cls, value):
        if not isinstance(value, str):
            return value
        value = os.path.expandvars(os.path.expanduser(value))
        if "$" in value:
            raise ValueError("undefined environment variable in machine configuration")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if (self.backend in ("fake", "pbs_local")) != (self.transport == "local"):
            raise ValueError("fake/pbs_local require local transport; iri/pbs_ssh require SSH")
        if not self.queues or not self.accounts or any(not account for account in self.accounts):
            raise ValueError("queues and accounts must be configured")
        if self.backend != "fake":
            if not self.user:
                raise ValueError("live machines require user")
            if not all(path.startswith("/") for path in (self.software_root, self.work_root)):
                raise ValueError("live roots must be absolute paths")
        if self.transport == "ssh":
            if not self.ssh_alias or not self.user:
                raise ValueError("live machines require ssh_alias and user")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", self.ssh_alias):
                raise ValueError("invalid SSH alias")
        if self.backend == "iri" and not self.resource_id:
            raise ValueError("IRI requires a confirmed resource_id")
        if not self.api_url.startswith("https://"):
            raise ValueError("IRI requires HTTPS")
        if self.backend != "fake" and any(
            "REPLACE" in value
            for value in (
                self.user or "",
                self.resource_id or "",
                self.software_root,
                self.work_root,
                *self.accounts,
                *self.filesystems,
            )
        ):
            raise ValueError("replace example values with actual machine configuration")
        return self


class Config(Model):
    project_root: str = "."
    records_dir: str = "software"
    state_dir: str = "state"
    machines: dict[str, Machine]


class Resources(Model):
    nodes: int = Field(ge=1)
    walltime: int = Field(ge=1)
    queue: str
    account: str


class JobSpec(Resources):
    operation_id: str
    machine: str
    name: str
    script: str
    workdir: str
    stdout_path: str
    stderr_path: str
    filesystems: list[str]
    environment: dict[str, str] = Field(default_factory=dict)
    cpu_cores_per_process: int | None = Field(default=None, ge=1)


JobState = Literal[
    "queued", "held", "running", "suspended", "finished", "failed", "cancelled", "unknown"
]
TERMINAL = {"finished", "failed", "cancelled"}


class Job(Model):
    job_id: str
    machine: str
    name: str = ""
    state: JobState = "unknown"
    raw_state: str | None = None
    queue: str | None = None
    account: str | None = None
    nodes: int | None = None
    walltime_requested: int | None = None
    submit_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    exit_status: int | None = None
    workdir: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    operation_id: str | None = None
    simulated: bool = False


class Source(Model):
    type: Literal["git", "local", "working_tree"]
    url: str
    ref: str = "HEAD"
    exclude: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def local_path(self):
        path = PurePosixPath(self.url)
        if self.type == "local" and (path.is_absolute() or ".." in path.parts or str(path) == "."):
            raise ValueError("local source must be a relative directory inside the record")
        if self.type == "working_tree" and not path.is_absolute():
            raise ValueError("working_tree source must be an absolute directory on the controller")
        if self.exclude and self.type != "working_tree":
            raise ValueError("source exclusions apply only to working_tree snapshots")
        return self


class Record(Model):
    schema_version: Literal[1] = 1
    source: Source
    validation: Resources
    validation_mode: Literal["reference", "completion"] = "reference"
    metrics: dict[str, float] = Field(default_factory=dict)  # required absolute tolerances
    environment_probes: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def tolerances(self):
        if (self.validation_mode == "reference" and not self.metrics) or any(
            value < 0 for value in self.metrics.values()
        ):
            raise ValueError("at least one finite, nonnegative metric tolerance is required")
        return self

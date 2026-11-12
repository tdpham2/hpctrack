import re
from typing import Protocol

from hpctrack.errors import TrackError
from hpctrack.models import Job, JobSpec


class JobBackend(Protocol):
    def submit(self, spec: JobSpec) -> Job: ...
    def list(self, user: str | None, include_finished: bool) -> list[Job]: ...
    def get(self, job_id: str) -> Job: ...
    def cancel(self, job_id: str) -> None: ...


def check_budget(spec, machine):
    if re.search(r"^\s*#\s*(PBS|SBATCH)\b", spec.script, re.MULTILINE):
        raise TrackError(
            "embedded_directive", "Pass scheduler resources as options, not directives", 30
        )
    queue = machine.queues.get(spec.queue)
    if not queue or spec.account not in machine.accounts:
        raise TrackError("resource_refused", "Queue or account is not permitted", 30)
    if not queue.min_nodes <= spec.nodes <= min(queue.max_nodes, machine.max_nodes):
        raise TrackError("resource_refused", "Node request exceeds configured limits", 30)
    if not queue.min_walltime <= spec.walltime <= min(queue.max_walltime, machine.max_walltime):
        raise TrackError("resource_refused", "Walltime request exceeds configured limits", 30)
    if spec.nodes * spec.walltime / 3600 > machine.max_node_hours:
        raise TrackError("budget_exceeded", "Job exceeds the configured node-hours budget", 30)
    if set(spec.filesystems) != set(machine.filesystems):
        raise TrackError("resource_refused", "Job filesystems must match configured resources", 30)


def operation_marker(name, environment=None):
    marker = (environment or {}).get("HPCTRACK_OPERATION_ID")
    if marker:
        return marker
    match = re.search(r"-([a-f0-9]{32})$", name or "")
    return match.group(1) if match else None


def walltime_seconds(value):
    if value is None:
        return None
    if isinstance(value, (float, int)) or str(value).isdigit():
        return int(value)
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
        if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
            raise ValueError
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, AttributeError) as exc:
        raise TrackError("invalid_walltime", "Walltime must be seconds or HH:MM:SS", 2) from exc


def format_walltime(seconds):
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def validate_job_id(job_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\[\]:-]{0,255}", job_id):
        raise TrackError("invalid_job_id", "Invalid scheduler job identifier", 2)
    return job_id

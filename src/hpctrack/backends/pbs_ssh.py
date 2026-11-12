import json
import re
import shlex
from datetime import datetime, timezone

from hpctrack.backends.base import (
    format_walltime,
    operation_marker,
    validate_job_id,
    walltime_seconds,
)
from hpctrack.errors import TrackError
from hpctrack.models import Job


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value)


def normalize(machine, job_id, raw):
    state = raw.get("job_state", "")
    exit_status = raw.get("Exit_status")
    states = {
        "Q": "queued",
        "W": "queued",
        "T": "queued",
        "H": "held",
        "R": "running",
        "B": "running",
        "E": "running",
        "S": "suspended",
        "U": "suspended",
    }
    normalized = states.get(state, "unknown")
    if state in ("F", "C") and exit_status is not None:
        normalized = "finished" if int(exit_status) == 0 else "failed"
    resources = raw.get("Resource_List", {})
    variables = raw.get("Variable_List", {})
    if isinstance(variables, str):
        variables = dict(item.split("=", 1) for item in variables.split(",") if "=" in item)

    def output_path(value):
        if value and not value.startswith("/") and ":" in value:
            return value.split(":", 1)[1]
        return value

    return Job(
        job_id=job_id,
        machine=machine,
        name=raw.get("Job_Name", ""),
        state=normalized,
        raw_state=state,
        queue=raw.get("queue"),
        account=raw.get("Account_Name"),
        nodes=resources.get("nodect"),
        walltime_requested=walltime_seconds(resources.get("walltime")),
        submit_time=timestamp(raw.get("qtime")),
        start_time=timestamp(raw.get("stime")),
        end_time=timestamp(raw.get("obittime")),
        exit_status=exit_status,
        workdir=variables.get("PBS_O_WORKDIR"),
        stdout_path=output_path(raw.get("Output_Path")),
        stderr_path=output_path(raw.get("Error_Path")),
        operation_id=operation_marker(raw.get("Job_Name"), variables),
    )


class PBSBackend:
    def __init__(self, machine, config, transport):
        self.machine, self.config, self.transport = machine, config, transport

    def submit(self, spec):
        for value in (spec.name, spec.queue, spec.account, *spec.filesystems):
            if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
                raise TrackError(
                    "invalid_resource", "PBS resource identifiers contain invalid characters", 2
                )
        for value in (spec.stdout_path, spec.stderr_path):
            if "\n" in value or "\r" in value:
                raise TrackError("invalid_path", "Newlines are not allowed in scheduler paths", 2)
        select = f"{spec.nodes}"
        if spec.cpu_cores_per_process:
            select += f":ncpus={spec.cpu_cores_per_process}"
        lines = [
            "#!/bin/bash",
            f"#PBS -N {spec.name}",
            f"#PBS -q {spec.queue}",
            f"#PBS -A {spec.account}",
            f"#PBS -l select={select}",
            "#PBS -l place=scatter",
            f"#PBS -l walltime={format_walltime(spec.walltime)}",
            f"#PBS -l filesystems={':'.join(spec.filesystems)}",
            f"#PBS -o {shlex.quote(spec.stdout_path)}",
            f"#PBS -e {shlex.quote(spec.stderr_path)}",
            "set -e",
            f"cd -- {shlex.quote(spec.workdir)}",
        ]
        for name, value in spec.environment.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise TrackError("invalid_environment", "Invalid environment variable name", 2)
            lines.append(f"export {name}={shlex.quote(value)}")
        lines.append(spec.script)
        path = f"{spec.workdir}/submit-{spec.operation_id}.pbs"
        self.transport.write(path, "\n".join(lines) + "\n")
        result = self.transport.run(["qsub", path])
        if result.returncode:
            raise TrackError("submission_refused", "PBS refused submission", 30)
        job_id = result.stdout.decode().strip()
        if not re.fullmatch(r"[0-9]+(?:\[[0-9-]*\])?(?:\.[A-Za-z0-9_.-]+)?", job_id):
            raise TrackError("submission_unknown", "PBS returned an unrecognized receipt", 40)
        return Job(
            job_id=job_id,
            machine=self.machine,
            name=spec.name,
            state="queued",
            operation_id=spec.operation_id,
        )

    def _query(self, args, missing=False):
        result = self.transport.run(["qstat", "-f", "-F", "JSON", *args])
        if missing and result.returncode == 153:
            return {}
        if result.returncode:
            raise TrackError("scheduler_error", "PBS status query failed", machine=self.machine)
        try:
            jobs = json.loads(result.stdout).get("Jobs", {})
            if not isinstance(jobs, dict):
                raise ValueError
            return jobs
        except (ValueError, AttributeError) as exc:
            raise TrackError("invalid_response", "PBS did not return a valid jobs object") from exc

    def list(self, user=None, include_finished=False):
        args = ["-x"] if include_finished else []
        args += ["-u", user or self.config.user]
        return [normalize(self.machine, key, value) for key, value in self._query(args).items()]

    def get(self, job_id):
        validate_job_id(job_id)
        jobs = self._query(["-x", job_id], missing=True)
        return (
            normalize(self.machine, job_id, jobs[job_id])
            if job_id in jobs
            else Job(job_id=job_id, machine=self.machine)
        )

    def cancel(self, job_id):
        validate_job_id(job_id)
        if self.transport.run(["qdel", job_id]).returncode:
            raise TrackError("cancel_failed", "PBS cancellation failed", machine=self.machine)

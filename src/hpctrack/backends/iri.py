import subprocess
import sys
import time
from urllib.parse import quote

import requests

from hpctrack.backends.base import operation_marker, validate_job_id, walltime_seconds
from hpctrack.backends.pbs_ssh import normalize as normalize_pbs
from hpctrack.backends.pbs_ssh import timestamp
from hpctrack.errors import TrackError, auth_required
from hpctrack.models import Job


def access_token(machine):
    # Close stdin and bound the helper; it must never start an interactive login.
    script = "from alcf_tokens.auth import get_access_token; print(get_access_token('iri'))"
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise auth_required(machine, "iri") from exc
    token = result.stdout.decode().strip()
    if result.returncode or not token or any(char.isspace() for char in token):
        raise auth_required(machine, "iri")
    return token


def normalize(machine, raw, job_id=None):
    if not isinstance(raw, dict):
        raise TrackError("invalid_response", "IRI job must be an object")
    job_id = raw.get("job_id", raw.get("id", raw.get("jobId", job_id)))
    if job_id is None:
        raise TrackError("invalid_response", "IRI job has no identifier")
    if "job_state" in raw:
        return normalize_pbs(machine, str(job_id), raw)
    attributes = raw.get("attributes") or {}
    resources = raw.get("resources") or {}
    state = raw.get("state", "unknown")
    states = {
        "new": "queued",
        "queued": "queued",
        "held": "held",
        "active": "running",
        "running": "running",
        "suspended": "suspended",
        "completed": "finished",
        "finished": "finished",
        "failed": "failed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
    }
    exit_status = raw.get("exit_status", raw.get("exit_code"))
    normalized = states.get(state, "unknown")
    if normalized == "finished" and exit_status not in (None, 0, "0"):
        normalized = "failed"
    return Job(
        job_id=str(job_id),
        machine=machine,
        name=raw.get("name", ""),
        state=normalized,
        raw_state=state,
        queue=raw.get("queue", attributes.get("queue_name")),
        account=raw.get("account", attributes.get("account")),
        nodes=raw.get("nodes", resources.get("node_count")),
        walltime_requested=walltime_seconds(attributes.get("duration", raw.get("walltime"))),
        submit_time=timestamp(raw.get("submit_time")),
        start_time=timestamp(raw.get("start_time")),
        end_time=timestamp(raw.get("end_time")),
        exit_status=exit_status,
        workdir=raw.get("workdir", (raw.get("environment") or {}).get("HPCTRACK_WORKDIR")),
        stdout_path=raw.get("stdout_path"),
        stderr_path=raw.get("stderr_path"),
        operation_id=operation_marker(raw.get("name"), raw.get("environment")),
    )


class IRIBackend:
    def __init__(self, machine, config, session=None, token_provider=None):
        self.machine, self.config = machine, config
        self.session = session or requests.Session()
        self.token_provider = token_provider or (lambda: access_token(machine))
        self.resource = quote(config.resource_id, safe="")

    def request(self, method, path, **kwargs):
        token = self.token_provider()
        try:
            response = self.session.request(
                method,
                self.config.api_url.rstrip("/") + path,
                headers={"Authorization": f"Bearer {token}"},
                timeout=(5, 30),
                allow_redirects=False,
                proxies={"https": self.config.proxy} if self.config.proxy else None,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise TrackError(
                "api_unavailable",
                "IRI request failed; credentials omitted from diagnostics",
                machine=self.machine,
            ) from exc
        if response.status_code == 401:
            raise auth_required(self.machine, "iri")
        if response.status_code == 403:
            raise TrackError("api_forbidden", "IRI denied this operation for the account", 30)
        if response.status_code == 404:
            return None
        if response.status_code == 204:
            return None
        if not 200 <= response.status_code < 300:
            raise TrackError("api_error", "IRI returned an error", status=response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise TrackError("invalid_response", "IRI returned invalid JSON") from exc

    def submit(self, spec):
        import shlex

        payload = {
            "executable": "/bin/bash",
            "arguments": ["-lc", f"cd -- {shlex.quote(spec.workdir)}\n{spec.script}"],
            "name": spec.name,
            "stdout_path": spec.stdout_path,
            "stderr_path": spec.stderr_path,
            "environment": {**spec.environment, "HPCTRACK_WORKDIR": spec.workdir},
            "resources": {"node_count": spec.nodes},
            "attributes": {
                "duration": spec.walltime,
                "queue_name": spec.queue,
                "account": spec.account,
                "custom_attributes": {"filesystems": ":".join(spec.filesystems)},
            },
        }
        if spec.cpu_cores_per_process:
            payload["resources"]["cpu_cores_per_process"] = spec.cpu_cores_per_process
        response = self.request("POST", f"/compute/job/{self.resource}", json=payload)
        job_id = (
            response
            if isinstance(response, (str, int))
            else (
                response.get("job_id", response.get("id", response.get("jobId")))
                if isinstance(response, dict)
                else None
            )
        )
        if job_id is None:
            raise TrackError(
                "submission_unknown", "IRI submission has no recognized job receipt", 40
            )
        return Job(
            job_id=str(job_id),
            machine=self.machine,
            name=spec.name,
            state="queued",
            operation_id=spec.operation_id,
        )

    def list(self, user=None, include_finished=False):
        result, seen = [], set()
        deadline = time.monotonic() + 60
        for offset in range(0, 100000, 100):
            if time.monotonic() >= deadline:
                raise TrackError("api_timeout", "IRI listing exceeded its total time budget")
            response = self.request(
                "POST",
                f"/compute/status/{self.resource}",
                params={
                    "historical": str(include_finished).lower(),
                    "limit": 100,
                    "offset": offset,
                },
                json={"owner": user or self.config.user},
            )
            rows = (
                response.get("jobs", response.get("items"))
                if isinstance(response, dict)
                else response
            )
            if not isinstance(rows, list):
                raise TrackError("invalid_response", "IRI status response must contain a jobs list")
            for row in rows:
                job = normalize(self.machine, row)
                if job.job_id in seen:
                    raise TrackError("pagination_error", "IRI repeated a job across pages")
                seen.add(job.job_id)
                result.append(job)
            if len(rows) < 100:
                return result
        raise TrackError("pagination_error", "IRI exceeded the bounded pagination limit")

    def get(self, job_id):
        validate_job_id(job_id)
        response = self.request(
            "GET",
            f"/compute/status/{self.resource}/{quote(job_id, safe='')}",
            params={"historical": "true"},
        )
        if response is None:
            return Job(job_id=job_id, machine=self.machine)
        return normalize(self.machine, response, job_id)

    def cancel(self, job_id):
        validate_job_id(job_id)
        self.request("DELETE", f"/compute/cancel/{self.resource}/{quote(job_id, safe='')}")

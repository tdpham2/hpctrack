from pathlib import Path

from hpctrack.errors import TrackError
from hpctrack.models import Job, JobSpec
from hpctrack.remote import prepare_worker, worker_result
from hpctrack.util import now


class FakeBackend:
    """A persistent local demo scheduler, never an automatic production fallback."""

    def __init__(self, machine, config, transport):
        self.machine, self.config, self.transport = machine, config, transport
        self.root = Path(config.work_root) / "scheduler"

    def submit(self, spec):
        job_id = f"demo-{spec.operation_id}"
        directory = self.root / job_id
        self.transport.mkdir(spec.workdir)
        self.transport.write(f"{directory}/script.sh", spec.script)
        prepare_worker(
            self.transport,
            str(directory),
            ["bash", str(directory / "script.sh")],
            spec.workdir,
            spec.environment,
            timeout=spec.walltime,
        )
        self.transport.write(f"{directory}/spec.json", spec.model_dump_json())
        self.transport.write(f"{directory}/submitted", now())
        self.transport.start(str(directory))
        return Job(
            job_id=job_id,
            machine=self.machine,
            name=spec.name,
            state="queued",
            operation_id=spec.operation_id,
            simulated=True,
        )

    def get(self, job_id):
        if not job_id.startswith("demo-") or "/" in job_id or ".." in job_id:
            raise TrackError("invalid_job_id", "Invalid demo job ID", 2)
        directory = self.root / job_id
        raw = self.transport.read(f"{directory}/spec.json")
        if raw is None:
            return Job(job_id=job_id, machine=self.machine, simulated=True)
        spec = JobSpec.model_validate_json(raw)
        result = worker_result(self.transport, str(directory))
        state = "running" if (directory / "pid").exists() else "queued"
        if result:
            state = (
                "cancelled"
                if result.get("cancelled")
                else ("finished" if result["exit_status"] == 0 else "failed")
            )
            # Output paths match the real backend contract.
            for source, target in (
                ("stdout.log", spec.stdout_path),
                ("stderr.log", spec.stderr_path),
            ):
                data = self.transport.read(f"{directory}/{source}")
                if data is not None:
                    self.transport.write(target, data)
        return Job(
            job_id=job_id,
            machine=self.machine,
            name=spec.name,
            state=state,
            raw_state=state,
            queue=spec.queue,
            account=spec.account,
            nodes=spec.nodes,
            walltime_requested=spec.walltime,
            workdir=spec.workdir,
            stdout_path=spec.stdout_path,
            stderr_path=spec.stderr_path,
            operation_id=spec.operation_id,
            simulated=True,
            submit_time=(directory / "submitted").read_text(),
            exit_status=result["exit_status"] if result else None,
        )

    def list(self, user=None, include_finished=False):
        jobs = [self.get(path.parent.name) for path in sorted(self.root.glob("*/spec.json"))]
        return [
            job
            for job in jobs
            if include_finished or job.state not in ("finished", "failed", "cancelled")
        ]

    def cancel(self, job_id):
        job = self.get(job_id)
        if job.state == "unknown":
            raise TrackError("unknown_job", "Demo job not found", 2)
        self.transport.cancel(str(self.root / job_id))

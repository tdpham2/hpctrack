import time

import pytest

from hpctrack.errors import TrackError
from hpctrack.models import Job

RESOURCES = {"nodes": 1, "walltime": 10, "queue": "debug", "account": "demo"}


def test_submission_sync_and_cancellation(service):
    result = service.submit_job("demo", "sleep 2\n", RESOURCES, project="project-a")
    job_id = result["job"]["job_id"]
    backend = service.backend("demo")
    deadline = time.monotonic() + 5
    while backend.get(job_id).state == "queued" and time.monotonic() < deadline:
        time.sleep(0.02)
    service.sync()
    job = service.store.get("job", f"demo/{job_id}")
    assert job["tool_owned"] and job["project"] == "project-a"
    service.cancel("demo", job_id)
    while (
        backend.get(job_id).state not in ("cancelled", "finished") and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    assert backend.get(job_id).state == "cancelled"


@pytest.mark.parametrize(
    "change", [{"nodes": 5}, {"walltime": 301}, {"queue": "unauthorized"}, {"account": "other"}]
)
def test_limits_refuse_before_submission(service, change):
    with pytest.raises(TrackError) as error:
        service.submit_job("demo", "echo should-not-run", {**RESOURCES, **change})
    assert error.value.code == 30
    assert service.backend("demo").list(None, True) == []


def test_embedded_directives_cannot_bypass_budget(service):
    with pytest.raises(TrackError) as error:
        service.submit_job("demo", "#PBS -l select=1000\necho hi", RESOURCES)
    assert error.value.result["error"] == "embedded_directive"


def test_external_cancel_requires_confirmation(service):
    calls = []

    class Backend:
        def cancel(self, job_id):
            calls.append(job_id)

    service.backend_factory = lambda *_: Backend()
    with pytest.raises(TrackError) as error:
        service.cancel("demo", "123.server")
    assert error.value.code == 30 and not calls
    service.cancel("demo", "123.server", True)
    assert calls == ["123.server"]


def test_missing_job_does_not_become_success(service):
    assert service.backend("demo").get("demo-absent").state == "unknown"


def test_lost_submission_receipt_reconciles_without_duplicate(service):
    class Backend:
        def __init__(self):
            self.jobs = []
            self.submits = 0

        def list(self, *args):
            return self.jobs

        def submit(self, spec):
            self.submits += 1
            self.jobs.append(
                Job(
                    job_id="100.server",
                    machine="demo",
                    name=spec.name,
                    state="queued",
                    operation_id=spec.operation_id,
                )
            )
            raise TrackError("api_unavailable", "Connection lost after acceptance")

    backend = Backend()
    service.backend_factory = lambda *_: backend
    with pytest.raises(TrackError) as error:
        service.submit_job("demo", "echo ok", RESOURCES)
    operation_id = error.value.result["operation_id"]
    result = service.resume(operation_id)
    assert result["operations"][0]["job_id"] == "100.server"
    assert backend.submits == 1
    assert service.store.get("job", "demo/100.server")["tool_owned"]


def test_uncertain_submission_is_not_retried(service):
    class Backend:
        submits = 0

        def list(self, *args):
            return []

        def submit(self, spec):
            self.submits += 1
            raise TrackError("api_unavailable", "Unknown acceptance")

    backend = Backend()
    service.backend_factory = lambda *_: backend
    with pytest.raises(TrackError) as error:
        service.submit_job("demo", "echo ok", RESOURCES)
    with pytest.raises(TrackError) as resumed:
        service.resume(error.value.result["operation_id"])
    assert resumed.value.result["error"] == "submission_unknown"
    assert backend.submits == 1


def test_colliding_job_ids_are_machine_scoped(service):
    service._remember_job(Job(job_id="10.server", machine="first", state="queued"))
    service._remember_job(Job(job_id="10.server", machine="second", state="running"))
    assert service.store.get("job", "first/10.server")["state"] == "queued"
    assert service.store.get("job", "second/10.server")["state"] == "running"


def test_sync_does_not_turn_name_marker_into_ownership(service):
    service._remember_job(
        Job(
            job_id="1.server", machine="demo", operation_id="a" * 32, name="ht-validate-" + "a" * 32
        )
    )
    assert not service.store.get("job", "demo/1.server")["tool_owned"]


def test_disappeared_job_becomes_unknown_with_last_known_evidence(service):
    service._remember_job(Job(job_id="1.server", machine="demo", state="running", workdir="/known"))

    class Backend:
        def list(self, *args):
            return []

        def get(self, job_id):
            return Job(job_id=job_id, machine="demo")

    service.backend_factory = lambda *_: Backend()
    service.sync()
    job = service.store.get("job", "demo/1.server")
    assert job["state"] == "unknown" and job["last_known_state"] == "running"
    assert job["workdir"] == "/known"


def test_queue_occupancy_refuses_before_submission(service):
    class Backend:
        def list(self, *args):
            return [
                Job(job_id=str(i), machine="demo", queue="debug", state="running") for i in range(2)
            ]

        def submit(self, spec):
            pytest.fail("queue capacity must be checked before submission")

    service.backend_factory = lambda *_: Backend()
    with pytest.raises(TrackError) as error:
        service.submit_job("demo", "echo nope", RESOURCES)
    assert error.value.result["error"] == "queue_full"

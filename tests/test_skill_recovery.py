import json

import pytest

from hpctrack import cli
from hpctrack.backends.fake import FakeBackend
from hpctrack.errors import TrackError, auth_required
from hpctrack.remote import LocalTransport
from hpctrack.service import Service


def test_pending_build_is_resumed_once_from_new_controller(service, record, monkeypatch):
    starts = []
    start = LocalTransport.start

    def count_start(self, directory):
        starts.append(directory)
        return start(self, directory)

    monkeypatch.setattr(LocalTransport, "start", count_start)
    # Delay observation deterministically while the real local demo worker proceeds.
    import hpctrack.service as service_module

    with monkeypatch.context() as patch:
        patch.setattr(service_module, "worker_result", lambda *args: None)
        with pytest.raises(TrackError) as error:
            service.build("tiny", "demo", wait_timeout=0)
    assert error.value.code == 40
    operation_id = error.value.result["operation_id"]
    (record / "build.sh").write_text("# REPLACE_RECIPE\nexit 99\n")
    other = Service(service.settings)
    try:
        check = other.check("tiny", "demo")
        assert check["next_action"] == "resume" and check["placeholders"]
        assert check["pending_operations"] == [
            {
                "id": operation_id,
                "kind": "build",
                "status": "running",
                "build_id": None,
                "job_id": None,
            }
        ]
        resumed = other.resume(check["pending_operations"][0]["id"], wait_timeout=10)
        assert resumed["operations"][0]["state"] == "built"
        other.resume(operation_id)
        assert len(starts) == 1 and len(other.store.all("build")) == 1
        assert other.check("tiny", "demo")["pending_operations"] == []
    finally:
        other.store.close()


@pytest.mark.parametrize("uncertain", [False, True])
def test_pending_validation_recovers_without_duplicate_submission(
    service, record, monkeypatch, uncertain
):
    build = service.build("tiny", "demo", wait_timeout=10)
    submits = []
    submit, get = FakeBackend.submit, FakeBackend.get

    def count_submit(self, spec):
        submits.append(spec.operation_id)
        job = submit(self, spec)
        if uncertain:
            raise TrackError("synthetic_disconnect", "Synthetic failure after submission", 1)
        return job

    def running(self, job_id):
        return get(self, job_id).model_copy(update={"state": "running"})

    monkeypatch.setattr(FakeBackend, "submit", count_submit)
    with monkeypatch.context() as patch:
        patch.setattr(FakeBackend, "get", running)
        with pytest.raises(TrackError) as error:
            service.validate("tiny", "demo", build["id"], wait_timeout=0)
    assert error.value.code in (1, 40)
    check = service.check("tiny", "demo")
    assert check["next_action"] == "resume"
    pending = check["pending_operations"]
    assert len(pending) == 1 and pending[0]["kind"] == "validate"
    assert pending[0]["build_id"] == build["id"]
    other = Service(service.settings)
    try:
        result = other.resume(pending[0]["id"], wait_timeout=10)
        assert result["operations"][0]["state"] == "reference_pending"
        other.resume(pending[0]["id"])
        assert submits == [pending[0]["id"]]
        assert len(other.store.all("validation")) == 1
        assert other.check("tiny", "demo")["next_action"] == "human_reference_review"
    finally:
        other.store.close()


def test_check_matches_record_and_includes_promotion(service, record):
    other = service.store.new_operation("build", {"record_key": "different/demo"})
    finished = service.store.new_operation("validate", {"record_key": "tiny/demo"})
    finished["status"] = "finished"
    service.store.save_operation(finished)
    assert service.check("tiny", "demo")["pending_operations"] == []
    pending = service.store.new_operation(
        "promote", {"record_key": "tiny/demo", "build_id": "build-1"}
    )
    check = service.check("tiny", "demo")
    assert check["next_action"] == "resume"
    assert [op["id"] for op in check["pending_operations"]] == [pending["id"]]
    assert check["pending_operations"][0]["id"] != other["id"]


def test_cli_authentication_returns_human_remedy(service, record, monkeypatch, capsys):
    monkeypatch.setenv("HPCTRACK_ACTOR", "agent")
    monkeypatch.setenv("HPCTRACK_AGENT", "codex")
    monkeypatch.setenv("HPCTRACK_SESSION", "auth-test")

    def unavailable(*args, **kwargs):
        raise auth_required("demo")

    monkeypatch.setattr(Service, "transport", unavailable)
    with pytest.raises(SystemExit) as error:
        cli.main(
            ["--config", str(service.settings.path), "sw", "build", "tiny", "--machine", "demo"]
        )
    assert error.value.code == 20
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "auth_required" and payload["fix"] == "hpctrack connect demo"
    assert service.store.all("build") == [] and service.store.pending() == []


def test_agent_cannot_accept_reference_through_cli(service, record, monkeypatch, capsys):
    build = service.build("tiny", "demo", wait_timeout=10)
    candidate = service.validate("tiny", "demo", build["id"], wait_timeout=10)
    monkeypatch.setenv("HPCTRACK_ACTOR", "agent")
    monkeypatch.setenv("HPCTRACK_AGENT", "codex")
    monkeypatch.setenv("HPCTRACK_SESSION", "reference-test")
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "--config",
                str(service.settings.path),
                "sw",
                "reference",
                "accept",
                "tiny",
                "--machine",
                "demo",
                "--validation",
                candidate["id"],
                "--yes",
            ]
        )
    assert error.value.code == 30
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "human_confirmation_required"
    assert not (record / "test/reference.json").exists()
    assert service.check("tiny", "demo")["next_action"] == "human_reference_review"

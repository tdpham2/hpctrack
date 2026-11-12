import json
import subprocess

import pytest
import requests

from hpctrack.backends.iri import IRIBackend
from hpctrack.backends.pbs_ssh import PBSBackend, normalize
from hpctrack.errors import TrackError
from hpctrack.models import JobSpec, Machine
from hpctrack.remote import SSHTransport


@pytest.fixture
def machine():
    return Machine(
        backend="iri",
        transport="ssh",
        ssh_alias="test-host",
        resource_id="resource-id",
        user="test-user",
        software_root="/project/software",
        work_root="/project/work",
        queues={"debug": {"max_nodes": 4, "max_walltime": 600}},
        accounts=["allocation"],
        filesystems=["home", "eagle"],
        max_node_hours=1,
        max_nodes=4,
        max_walltime=600,
        site_verified=True,
    )


@pytest.fixture
def spec():
    return JobSpec(
        operation_id="a" * 32,
        machine="polaris",
        name="ht-test-" + "a" * 32,
        nodes=2,
        walltime=300,
        queue="debug",
        account="allocation",
        script="echo hello",
        workdir="/project/work/run",
        stdout_path="/project/work/run/out",
        stderr_path="/project/work/run/err",
        filesystems=["home", "eagle"],
        environment={"HPCTRACK_OPERATION_ID": "a" * 32},
    )


class Response:
    def __init__(self, data=None, status=200):
        self.status_code, self.data = status, data

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def iri(machine, *responses):
    session = Session(*responses)
    return IRIBackend(
        "polaris", machine, session=session, token_provider=lambda: "TEST_SECRET"
    ), session


def test_iri_submission_uses_one_canonical_resource_spec(machine, spec):
    backend, session = iri(machine, Response({"job_id": "123.polaris"}))
    assert backend.submit(spec).job_id == "123.polaris"
    method, url, options = session.calls[0]
    assert method == "POST" and url.endswith("/compute/job/resource-id")
    payload = options["json"]
    assert payload["resources"] == {"node_count": 2}
    assert payload["attributes"] == {
        "duration": 300,
        "queue_name": "debug",
        "account": "allocation",
        "custom_attributes": {"filesystems": "home:eagle"},
    }
    assert payload["arguments"][1].startswith("cd -- /project/work/run\n")
    assert options["timeout"] == (5, 30) and options["allow_redirects"] is False


def test_iri_pagination_and_states(machine):
    first = [{"job_id": str(i), "state": "active"} for i in range(100)]
    backend, session = iri(
        machine, Response({"jobs": first}), Response([{"id": "100", "state": "held"}])
    )
    jobs = backend.list(None, True)
    assert len(jobs) == 101 and jobs[-1].state == "held" and jobs[0].state == "running"
    assert session.calls[1][2]["params"]["offset"] == 100
    assert session.calls[0][2]["json"] == {"owner": "test-user"}


@pytest.mark.parametrize("status,code", [(401, 20), (403, 30), (503, 1)])
def test_iri_errors_do_not_expose_token(machine, status, code):
    backend, _ = iri(machine, Response(status=status))
    with pytest.raises(TrackError) as error:
        backend.list(None, False)
    assert error.value.code == code
    assert "TEST_SECRET" not in json.dumps(error.value.result)


def test_iri_invalid_json_and_transport_errors(machine):
    for response in (Response(ValueError("TEST_SECRET")), requests.Timeout("TEST_SECRET")):
        backend, _ = iri(machine, response)
        with pytest.raises(TrackError) as error:
            backend.list(None, False)
        assert "TEST_SECRET" not in str(error.value)


def test_iri_missing_job_is_unknown_and_cancel_204_is_valid(machine):
    backend, session = iri(machine, Response(status=404), Response(status=204))
    assert backend.get("100.server").state == "unknown"
    backend.cancel("100.server")
    assert session.calls[-1][0] == "DELETE"


def test_iri_unrecognized_receipt_stays_uncertain(machine, spec):
    backend, _ = iri(machine, Response({"task": "unrecognized"}))
    with pytest.raises(TrackError) as error:
        backend.submit(spec)
    assert error.value.code == 40


def test_pbs_normalization_preserves_full_id_and_absent_metadata():
    job = normalize(
        "aurora",
        "123.server",
        {"Job_Name": "external", "job_state": "H", "Resource_List": {"walltime": "01:02:03"}},
    )
    assert job.job_id == "123.server" and job.state == "held"
    assert job.walltime_requested == 3723 and job.exit_status is None
    assert normalize("aurora", "123.server", {"job_state": "F"}).state == "unknown"
    assert normalize("aurora", "123.server", {"job_state": "F", "Exit_status": 2}).state == "failed"
    assert normalize("aurora", "123.server", {"job_state": "S"}).state == "suspended"


def test_pbs_submission_and_empty_listing(machine, spec):
    class Transport:
        files = {}
        calls = []

        def write(self, path, content):
            self.files[path] = content

        def run(self, argv):
            self.calls.append(argv)
            return subprocess.CompletedProcess(
                argv, 0, b"123.polaris\n" if argv[0] == "qsub" else b'{"Jobs": {}}'
            )

    transport = Transport()
    backend = PBSBackend("polaris", machine, transport)
    assert backend.submit(spec).job_id == "123.polaris"
    content = next(iter(transport.files.values()))
    assert "#PBS -l select=2" in content and "#PBS -l walltime=00:05:00" in content
    assert "#PBS -l filesystems=home:eagle" in content
    assert backend.list("test-user", True) == []
    assert "-x" in transport.calls[-1] and "test-user" in transport.calls[-1]


def test_ssh_checks_before_action_and_disables_fallback(machine):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, b"ok", b"")

    transport = SSHTransport("polaris", machine, runner=run)
    transport.run(["echo", "a b; $(secret)"])
    assert "-O" in calls[0][0]
    command = calls[1][0]
    assert "BatchMode=yes" in command and "ProxyCommand=false" in command
    assert command[-1] == "echo 'a b; $(secret)'"
    assert calls[1][1]["timeout"] == 30


def test_dead_master_never_attempts_remote_action(machine):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 255, b"", b"missing")

    transport = SSHTransport("aurora", machine, runner=run)
    with pytest.raises(TrackError) as error:
        transport.run(["qstat"])
    assert error.value.code == 20 and len(calls) == 1
    assert error.value.result["fix"] == "hpctrack connect aurora"

from pathlib import Path

import pytest
import requests
import yaml

from hpctrack.config import Settings
from hpctrack.service import Service

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "examples/demo/record"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Tests must not contact the network")

    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setenv("HPCTRACK_ACTOR", "human")


@pytest.fixture
def config_path(tmp_path):
    content = yaml.safe_load((REPO / "examples/demo/machines.yaml").read_text())
    content.update(project_root=".", records_dir="software", state_dir="state")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(content))
    return path


@pytest.fixture
def service(config_path):
    value = Service(Settings(config_path))
    yield value
    value.store.close()


@pytest.fixture
def record(service):
    service.init("tiny", "demo", TEMPLATE)
    return service.settings.record_path("tiny", "demo")


@pytest.fixture
def accepted(service, record):
    build = service.build("tiny", "demo", wait_timeout=10)
    candidate = service.validate("tiny", "demo", build["id"], wait_timeout=10)
    service.accept_reference("tiny", "demo", candidate["id"], True)
    passed = service.validate("tiny", "demo", build["id"], wait_timeout=10)
    return build, candidate, passed

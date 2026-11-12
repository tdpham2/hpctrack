import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from hpctrack.config import Settings
from hpctrack.errors import TrackError
from hpctrack.store import Store
from hpctrack.util import within

ROOT = Path(__file__).resolve().parents[1]


def run_cli(config, *args, env=None):
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **(env or {})}
    result = subprocess.run(
        [sys.executable, "-m", "hpctrack", "--config", str(config), *args],
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )
    return result, json.loads(result.stdout)


def test_json_success_and_usage_error(config_path):
    result, payload = run_cli(config_path, "doctor", "--json")
    assert result.returncode == 0 and payload["ok"]
    assert payload["data"]["machines"]["demo"]["simulated"]
    result, payload = run_cli(config_path, "jobs", "cancel")
    assert result.returncode == 2 and payload["error"] == "usage_error"


def test_invalid_config_is_json(tmp_path):
    result, payload = run_cli(tmp_path / "missing.yaml", "status")
    assert result.returncode == 2 and payload["error"] == "invalid_config"


def test_agent_cannot_connect_even_in_demo(config_path):
    result, payload = run_cli(config_path, "connect", "demo", env={"HPCTRACK_ACTOR": "agent"})
    assert result.returncode == 30 and payload["error"] == "human_only"


def test_live_example_is_disabled(tmp_path):
    result, payload = run_cli(
        ROOT / "config/machines.example.yaml", "--state-dir", str(tmp_path / "live"), "doctor"
    )
    assert result.returncode == 30
    assert payload["data"] if "data" in payload else payload["machines"]
    assert all(
        item["backend"]["error"] == "site_unverified" for item in payload["machines"].values()
    )


def test_state_override_keeps_demo_records_isolated(tmp_path):
    settings = Settings(ROOT / "examples/demo/machines.yaml", tmp_path / "new-state")
    assert settings.records == tmp_path / "new-state/records"
    assert str(settings.machine("demo").software_root).startswith(str(settings.state))


def test_path_escape_and_symlink_are_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(TrackError):
        within(root, root / "../escape")
    with pytest.raises(TrackError):
        within(root, root / "link/file")


def test_store_mutation_lock_and_event_deduplication(tmp_path):
    one, two = Store(tmp_path), Store(tmp_path)
    try:
        with one.mutation():
            with pytest.raises(TrackError) as error:
                with two.mutation():
                    pass
            assert error.value.result["error"] == "controller_busy"
        one.put("record", "r", {"name": "r"})
        one.put("record", "r", {"name": "r"})
        assert len(one.history("r")) == 1
        assert two.get("record", "r") == {"name": "r"}
    finally:
        one.close()
        two.close()


def test_bad_config_never_silently_uses_fake(config_path):
    content = yaml.safe_load(config_path.read_text())
    content["machines"]["demo"]["backend"] = "iri"
    config_path.write_text(yaml.safe_dump(content))
    with pytest.raises(TrackError) as error:
        Settings(config_path)
    assert error.value.code == 2

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from hpctrack.config import init_workspace, record_template, resolve_workspace, workspace_config
from hpctrack.errors import TrackError
from hpctrack.records import HEADINGS, load_record
from hpctrack.store import Store

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env=None):
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **(env or {})}
    result = subprocess.run(
        [sys.executable, "-m", "hpctrack", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    return result, json.loads(result.stdout)


def test_workspace_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HPCTRACK_HOME", raising=False)
    assert resolve_workspace() == (tmp_path / "home/.hpctrack").resolve()
    monkeypatch.setenv("HPCTRACK_HOME", str(tmp_path / "env"))
    assert resolve_workspace() == (tmp_path / "env").resolve()
    assert resolve_workspace(tmp_path / "flag") == (tmp_path / "flag").resolve()
    with pytest.raises(TrackError) as error:
        workspace_config()
    assert error.value.result["error"] == "workspace_missing" and error.value.code == 2


def test_init_layout_and_refuses_overwrite(tmp_path):
    root = tmp_path / "ws"
    result = init_workspace(root, "demo")
    assert result["git"] and not result["placeholders"]
    for name in ("hpctrack.yaml", "AGENTS.md", "skills/build-software/SKILL.md", ".gitignore"):
        assert (root / name).is_file(), name
    assert (root / "records").is_dir() and (root / ".git").is_dir()
    assert "state/" in (root / ".gitignore").read_text()
    with pytest.raises(TrackError) as error:
        init_workspace(root, "demo")
    assert error.value.result["error"] == "workspace_exists" and error.value.code == 30


def test_init_without_git_and_placeholder_template(tmp_path):
    result = init_workspace(tmp_path / "ws", "pbs-local", git=False)
    assert not result["git"] and not (tmp_path / "ws/.git").exists()
    assert result["placeholders"] and "REPLACE_" in result["fix"]
    with pytest.raises(TrackError):
        init_workspace(tmp_path / "other", "no-such-machines")


def test_record_template_by_name_or_path(tmp_path):
    demo = record_template("demo")
    load_record(demo)
    assert record_template(str(demo)) == demo
    graspa = ROOT / "examples/graspa/record"
    assert record_template(str(graspa)) == graspa
    load_record(graspa)
    with pytest.raises(TrackError) as error:
        record_template("missing-template")
    assert "demo" in error.value.result["available"]


def test_v1_database_migrates_and_keeps_events(tmp_path):
    db = sqlite3.connect(tmp_path / "hpctrack.db")
    db.executescript("""
    CREATE TABLE events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
        time TEXT NOT NULL, machine TEXT, kind TEXT NOT NULL, subject TEXT NOT NULL,
        actor TEXT NOT NULL, operation_id TEXT, payload TEXT NOT NULL);
    INSERT INTO events(id,time,kind,subject,actor,payload)
        VALUES ('old','2026-01-01T00:00:00Z','record','r','human','{"record_key": "r"}');
    PRAGMA user_version=1;
    """)
    db.commit()
    db.close()
    store = Store(tmp_path)
    try:
        events = store.events("r")
        assert [e["id"] for e in events] == ["old"] and events[0]["actor_detail"] is None
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        store.close()


def test_actor_detail_rejects_free_text(tmp_path, monkeypatch):
    monkeypatch.setenv("HPCTRACK_AGENT", "token=abc def")
    with pytest.raises(TrackError) as error:
        Store(tmp_path)
    assert error.value.result["error"] == "invalid_actor"


def test_actor_detail_and_export_filters(service, record, tmp_path, monkeypatch):
    service.store.actor_detail = {**service.store.actor_detail, "agent": "builder", "session": "s1"}
    service.note("tiny", "demo", "first attempt")
    exported = service.ledger("tiny/demo")
    assert exported["count"] == len(exported["events"]) >= 2
    note = exported["events"][-1]
    assert note["kind"] == "note" and note["actor_detail"]["agent"] == "builder"
    assert service.ledger(since=exported["last_sequence"])["count"] == 0
    assert service.ledger(machine="no-such-machine")["count"] == 0
    written = service.ledger("tiny/demo", output=tmp_path / "out/ledger.jsonl")
    lines = (tmp_path / "out/ledger.jsonl").read_text().splitlines()
    assert written["count"] == len(lines) and json.loads(lines[-1])["kind"] == "note"
    history = (record / "history.jsonl").read_text().splitlines()
    assert json.loads(history[-1])["kind"] == "note"


def test_note_keeps_heading_order(service, record):
    for section in ("Failures and fixes", "Environment", "Change log", "Failures and fixes"):
        service.note("tiny", "demo", f"entry for {section}\nwith  newline", section)
    notes = (record / "NOTES.md").read_text()
    load_record(record)
    positions = [notes.find("## " + heading) for heading in HEADINGS]
    assert positions == sorted(positions)
    failures = notes[notes.find("## Failures and fixes") : notes.find("## Known issues")]
    assert failures.count("entry for Failures and fixes with newline") == 2
    with pytest.raises(TrackError):
        service.note("tiny", "demo", "x", "Not a heading")
    with pytest.raises(TrackError):
        service.note("tiny", "demo", "   ")


def test_check_reports_staleness_and_next_action(service, record, accepted):
    build = accepted[0]
    state = service.check("tiny", "demo")
    assert state["rebuild_needed"] == [] and state["revalidate_needed"] == []
    assert state["next_action"] == "promote"
    service.promote("tiny", "demo", build["id"], True)
    assert service.check("tiny", "demo")["next_action"] == "none"
    (record / "build.sh").write_text((record / "build.sh").read_text() + "\n# tweak\n")
    (record / "test/check.py").write_text((record / "test/check.py").read_text() + "\n# tweak\n")
    state = service.check("tiny", "demo")
    assert state["rebuild_needed"] == ["recipe_changed"]
    assert state["revalidate_needed"] == ["contract_changed"]
    assert state["next_action"] == "build"


def test_build_failure_carries_log_tail(service, record):
    (record / "build.sh").write_text("echo out-line\necho err-line >&2\nexit 3\n")
    with pytest.raises(TrackError) as error:
        service.build("tiny", "demo", wait_timeout=10)
    assert error.value.result["error"] == "build_failed"
    assert error.value.result["log_tail"] == {"stdout": "out-line", "stderr": "err-line"}
    assert service.check("tiny", "demo")["rebuild_needed"][0] == "build_failed"


def test_placeholders_block_build_before_submission(service, record):
    config = yaml.safe_load((record / "record.yaml").read_text())
    config["validation"]["account"] = "REPLACE_ACCOUNT"
    (record / "record.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(TrackError) as error:
        service.build("tiny", "demo")
    assert error.value.result["error"] == "record_placeholders"
    assert error.value.result["files"] == ["record.yaml"]
    assert service.store.all("build") == []
    assert service.check("tiny", "demo")["next_action"] == "fill_placeholders"


def test_cli_workspace_end_to_end(tmp_path):
    env = {"HPCTRACK_HOME": str(tmp_path / "ws"), "HPCTRACK_AGENT": "tester"}
    result, payload = run("status", env=env)
    assert result.returncode == 2 and payload["error"] == "workspace_missing"
    result, payload = run("templates", "list", env=env)
    assert payload["data"]["records"] == ["demo"]
    result, payload = run("init", "--machines", "demo", env=env)
    assert result.returncode == 0 and payload["data"]["workspace"] == str(tmp_path / "ws")
    result, payload = run("sw", "init", "tiny", "--machine", "demo", "--template", "demo", env=env)
    assert result.returncode == 0, payload
    assert (tmp_path / "ws/records/tiny/demo/record.yaml").is_file()
    result, payload = run("sw", "check", "tiny", "--machine", "demo", env=env)
    assert payload["data"]["next_action"] == "build"
    result, payload = run("sw", "note", "tiny", "--machine", "demo", "--message", "hello", env=env)
    assert "tester" in payload["data"]["entry"]
    result, payload = run("sw", "history", "tiny", "--machine", "demo", env=env)
    assert payload["data"]["events"][-1]["kind"] == "note"
    other = tmp_path / "other"
    result, payload = run("--workspace", str(other), "init", "--no-git", env=env)
    assert result.returncode == 0 and not (other / ".git").exists()
    result, payload = run("--workspace", str(other), "ledger", "export", env=env)
    assert payload["data"]["count"] == 0


def test_workspace_show_is_read_only_and_resolves_overrides(tmp_path, monkeypatch, capsys):
    from hpctrack import cli

    home = tmp_path / "user home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HPCTRACK_HOME", raising=False)
    elsewhere = tmp_path / "unrelated directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    default, env_root, flag_root = home / ".hpctrack", tmp_path / "env ws", tmp_path / "flag ws"
    for root in (default, env_root, flag_root):
        init_workspace(root, "demo", git=False)

    def refuse(*args):
        pytest.fail("workspace show must not open the ledger or contact a backend")

    monkeypatch.setattr(cli, "Service", refuse)

    def show(*args):
        assert cli.main([*args, "workspace", "show"]) == 0
        return json.loads(capsys.readouterr().out)["data"]

    assert show()["workspace"] == str(default)
    monkeypatch.setenv("HPCTRACK_HOME", str(env_root))
    assert show()["workspace"] == str(env_root)
    info = show("--workspace", str(flag_root))
    assert info == {
        "workspace": str(flag_root),
        "config": str(flag_root / "hpctrack.yaml"),
        "project": str(flag_root),
        "records": str(flag_root / "records"),
        "state": str(flag_root / "state"),
        "operating_rules": str(flag_root / "AGENTS.md"),
    }
    config = env_root / "hpctrack.yaml"
    content = yaml.safe_load(config.read_text())
    content.update(
        project_root="project root", records_dir="custom records", state_dir="custom state"
    )
    config.write_text(yaml.safe_dump(content))
    info = show("--workspace", str(flag_root), "--config", str(config), "--state-dir", "new state")
    assert info["config"] == str(config)
    assert info["project"] == str(env_root / "project root")
    assert info["records"] == str(env_root / "project root/custom records")
    assert info["state"] == str(elsewhere / "new state")
    assert not list(tmp_path.rglob("*.db"))
    assert not (elsewhere / "new state").exists()
    assert not (env_root / "project root").exists()


def test_workspace_show_errors_without_ledger(tmp_path):
    missing = tmp_path / "missing workspace"
    result, payload = run("--workspace", str(missing), "workspace", "show")
    assert result.returncode == 2 and payload["error"] == "workspace_missing"
    assert "'" + str(missing) + "'" in payload["fix"]
    result, payload = run("--config", str(missing / "invalid.yaml"), "workspace", "show")
    assert result.returncode == 2 and payload["error"] == "invalid_config"
    assert not missing.exists()


def test_agent_record_operations_from_unrelated_directory(tmp_path, monkeypatch):
    elsewhere = tmp_path / "unrelated directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    root = tmp_path / "workspace with spaces"
    env = {
        "HPCTRACK_HOME": str(root),
        "HPCTRACK_ACTOR": "agent",
        "HPCTRACK_AGENT": "codex",
        "HPCTRACK_SESSION": "portable-test",
    }

    def command(*args):
        result, payload = run(*args, env=env)
        assert result.returncode == 0, payload
        return payload["data"]

    command("init", "--machines", "demo", "--no-git")
    assert command("sw", "list")["software"] == []
    command("sw", "init", "tiny", "--machine", "demo", "--template", "demo")
    info = command("sw", "show", "tiny", "--machine", "demo")
    path = Path(info["record_path"])
    assert path == root / "records/tiny/demo"
    config = yaml.safe_load((path / "record.yaml").read_text())
    config["validation_mode"] = "completion"
    (path / "record.yaml").write_text(yaml.safe_dump(config))
    command("sw", "note", "tiny", "--machine", "demo", "--message", "Test completion mode")
    assert command("sw", "check", "tiny", "--machine", "demo")["record_path"] == str(path)
    build = command("sw", "build", "tiny", "--machine", "demo")
    validation = command("sw", "validate", "tiny", "--machine", "demo", "--build", build["id"])
    assert validation["state"] == "passed" and validation["simulated"]
    command("sw", "promote", "tiny", "--machine", "demo", "--build", build["id"], "--no-commit")
    assert command("sw", "check", "tiny", "--machine", "demo")["next_action"] == "none"
    events = command("sw", "history", "tiny", "--machine", "demo")["events"]
    for event in events:
        assert event["actor"] == "agent"
        assert event["actor_detail"]["agent"] == "codex"
        assert event["actor_detail"]["session"] == "portable-test"
    assert list(elsewhere.iterdir()) == []

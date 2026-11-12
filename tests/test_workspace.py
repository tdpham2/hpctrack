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
    assert {"demo", "graspa"} <= set(payload["data"]["records"])
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

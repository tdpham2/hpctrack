import json

import pytest

from hpctrack import cli, skills
from hpctrack.config import templates
from hpctrack.errors import TrackError
from hpctrack.util import digest, write_json


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home with spaces"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HPCTRACK_HOME", str(tmp_path / "missing workspace"))
    return home


def invoke(capsys, *args):
    try:
        code = cli.main(args)
    except SystemExit as exc:
        code = exc.code
    return code, json.loads(capsys.readouterr().out)


def test_cli_install_before_workspace_without_service(home, monkeypatch, capsys):
    def refuse(*args):
        pytest.fail("Skill commands must not load configuration, ledger, or backends")

    monkeypatch.setattr(cli, "Settings", refuse)
    monkeypatch.setattr(cli, "Service", refuse)
    code, result = invoke(capsys, "skills", "status")
    assert code == 0 and result["ok"]
    assert [d["status"] for d in result["data"]["destinations"]] == ["missing", "missing"]
    code, result = invoke(capsys, "skills", "install", "--agent", "all")
    assert code == 0 and len(result["data"]["destinations"]) == 2
    assert not (home / ".hpctrack").exists()
    assert not (home.parent / "missing workspace").exists()
    assert not list(home.rglob("*.db"))
    code, result = invoke(capsys, "skills", "install", "--agent", "invalid")
    assert code == 2 and result["error"] == "usage_error"


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode", "pi", "all"])
def test_destinations_and_identical_resources(home, agent):
    global_rules = home / ".agents/AGENTS.md"
    settings = home / ".claude/settings.json"
    for path in (global_rules, settings):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserve user configuration")
    result = skills.install(agent)
    assert global_rules.read_text() == settings.read_text() == "preserve user configuration"
    selected = set(skills.DESTINATIONS.values()) if agent == "all" else {skills.DESTINATIONS[agent]}
    assert {item["path"] for item in result["destinations"]} == {str(home / p) for p in selected}
    for relative in selected:
        directory = home / relative
        for name, content in skills.packaged_files().items():
            assert (directory / name).read_bytes() == content
        manifest = json.loads((directory / skills.MANIFEST).read_text())
        assert manifest["version"] == skills.__version__
        assert manifest["files"] == {n: digest(c) for n, c in skills.packaged_files().items()}
    assert not (home / ".codex").exists()
    assert not (home / ".config").exists()
    assert not (home / ".pi").exists()
    if agent == "all":
        assert (home / skills.DESTINATIONS["claude"] / skills.MANIFEST).read_bytes() == (
            home / skills.DESTINATIONS["codex"] / skills.MANIFEST
        ).read_bytes()


def test_references_come_from_workspace_templates():
    files = skills.packaged_files()
    source = templates() / "workspace"
    assert files["references/AGENTS.md"] == (source / "AGENTS.md").read_bytes()
    assert (
        files["references/build-software.md"]
        == (source / "skills/build-software/SKILL.md").read_bytes()
    )


def test_dry_run_and_repeat_are_write_free(home):
    preview = skills.install("all", dry_run=True)
    assert all(item["changes"] for item in preview["destinations"])
    assert list(home.iterdir()) == []
    assert skills.install("all")["destinations"] == preview["destinations"]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob("*") if p.is_file()}
    assert all(item["status"] == "current" for item in skills.status()["destinations"])
    assert all(not item["changes"] for item in skills.install("all")["destinations"])
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}


def test_managed_upgrade_updates_adds_and_removes_files(home, monkeypatch):
    current = skills.packaged_files()
    old = {**current, "SKILL.md": b"old skill", "references/retired.md": b"old procedure"}
    with monkeypatch.context() as patch:
        patch.setattr(skills, "__version__", "0.0.1")
        patch.setattr(skills, "packaged_files", lambda: old)
        skills.install("all")
    assert all(item["status"] == "outdated" for item in skills.status()["destinations"])
    directory = home / skills.DESTINATIONS["codex"]
    (directory / "personal.txt").write_text("keep this unrelated file")
    preview = skills.install("all", dry_run=True)
    assert (directory / "SKILL.md").read_bytes() == b"old skill"
    assert {change["action"] for change in preview["destinations"][0]["changes"]} == {
        "update",
        "remove",
    }
    skills.install("all")
    assert (directory / "personal.txt").read_text() == "keep this unrelated file"
    assert not (directory / "references/retired.md").exists()
    assert all(item["status"] == "current" for item in skills.status()["destinations"])
    monkeypatch.setattr(skills, "packaged_files", lambda: {**current, "references/new.md": b"new"})
    skills.install("all")
    assert (directory / "references/new.md").read_bytes() == b"new"


@pytest.mark.parametrize("change", ["edit", "delete", "symlink", "manifest", "traversal"])
def test_modified_files_refused_before_any_destination_changes(home, monkeypatch, change):
    skills.install("all")
    directory = home / skills.DESTINATIONS["codex"]
    target = directory / "SKILL.md"
    if change == "edit":
        target.write_text("user edits")
    elif change == "delete":
        target.unlink()
    elif change == "symlink":
        target.unlink()
        target.symlink_to(home / "outside")
    elif change == "manifest":
        (directory / skills.MANIFEST).write_text("not JSON")
    else:
        path = directory / skills.MANIFEST
        manifest = json.loads(path.read_text())
        manifest["files"]["../outside"] = digest(b"outside")
        write_json(path, manifest)
    first = home / skills.DESTINATIONS["claude"] / skills.MANIFEST
    before = first.read_bytes()
    monkeypatch.setattr(skills, "__version__", "0.2.0")
    assert skills.status()["destinations"][1]["status"] == "modified"
    for dry_run in (True, False):
        with pytest.raises(TrackError) as error:
            skills.install("all", dry_run=dry_run)
        assert error.value.code == 30 and error.value.result["error"] == "skill_conflict"
        assert first.read_bytes() == before


def test_unmanaged_directory_and_upgrade_collision(home, monkeypatch, capsys):
    directory = home / skills.DESTINATIONS["codex"]
    directory.mkdir(parents=True)
    target = directory / "SKILL.md"
    target.write_bytes(skills.packaged_files()["SKILL.md"])
    code, result = invoke(capsys, "skills", "install", "--agent", "all")
    assert code == 30 and result["error"] == "skill_conflict"
    assert not (home / ".claude").exists()
    target.unlink()
    skills.install("codex")
    extra = directory / "references/new.md"
    extra.write_bytes(b"user content")
    current = skills.packaged_files()
    monkeypatch.setattr(
        skills, "packaged_files", lambda: {**current, "references/new.md": b"package"}
    )
    with pytest.raises(TrackError):
        skills.install("codex")
    assert extra.read_bytes() == b"user content"


@pytest.mark.parametrize("component", [".agents", ".agents/skills", ".agents/skills/hpctrack"])
def test_symlinked_destination_refused(home, component):
    outside = home.parent / "outside"
    outside.mkdir()
    target = home / component
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(TrackError):
        skills.install("codex")
    assert list(outside.iterdir()) == []

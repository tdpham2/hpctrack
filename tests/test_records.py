import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

import hpctrack.service as service_module
from hpctrack.errors import TrackError
from hpctrack.records import project_record
from hpctrack.service import Service


def test_complete_lifecycle_and_idempotent_resume(service, record, accepted):
    build, candidate, passed = accepted
    assert candidate["state"] == "reference_pending"
    assert passed["state"] == "passed"
    result = service.promote("tiny", "demo", build["id"], no_commit=True)
    assert result["manifest"]["status"] == "verified"
    assert result["manifest"]["simulated"] is True
    before = service.store.history("tiny/demo")
    service.resume(result["operation_id"])
    assert service.store.history("tiny/demo") == before
    manifest = json.loads((record / "manifest.json").read_text())
    assert manifest["current_build"] == build["id"]
    events = [json.loads(line) for line in (record / "history.jsonl").read_text().splitlines()]
    assert len({event["id"] for event in events}) == len(events)


def test_candidate_is_not_promotion_evidence(service, record):
    build = service.build("tiny", "demo", wait_timeout=10)
    candidate = service.validate("tiny", "demo", wait_timeout=10)
    assert candidate["metrics"]["sum_of_squares"] == 30
    with pytest.raises(TrackError, match="passing comparison") as error:
        service.promote("tiny", "demo", build["id"], True)
    assert error.value.code == 30
    with pytest.raises(TrackError):
        service.accept_reference("tiny", "demo", candidate["id"], False)
    service.store.actor = "agent"
    with pytest.raises(TrackError):
        service.accept_reference("tiny", "demo", candidate["id"], True)


def test_accepted_reference_requires_new_comparison(service, record):
    build = service.build("tiny", "demo", wait_timeout=10)
    candidate = service.validate("tiny", "demo", wait_timeout=10)
    service.accept_reference("tiny", "demo", candidate["id"], True)
    with pytest.raises(TrackError):
        service.promote("tiny", "demo", build["id"], True)


def test_wrong_accepted_reference_fails_scientific_comparison(service, record, accepted):
    reference = service.store.get("reference", "tiny/demo")
    reference["metrics"]["sum_of_squares"]["value"] = 12345
    # Deliberately construct a wrong *accepted* fixture, rather than hand-editing a projection.
    service.store.put("reference", "tiny/demo", reference)
    project_record(service.settings, service.store, "tiny", "demo")
    with pytest.raises(TrackError) as error:
        service.validate("tiny", "demo", wait_timeout=10)
    assert error.value.code == 10
    assert error.value.result["validation"]["state"] == "failed"


def test_reference_tampering_blocks_before_submission(service, record, accepted):
    path = record / "test/reference.json"
    reference = json.loads(path.read_text())
    reference["metrics"]["sum_of_squares"]["value"] = 42
    path.write_text(json.dumps(reference))
    count = len(service.backend("demo").list(None, True))
    with pytest.raises(TrackError) as error:
        service.validate("tiny", "demo")
    assert error.value.result["error"] == "reference_changed"
    assert len(service.backend("demo").list(None, True)) == count


def test_changed_test_blocks_validation_and_promotion(service, record, accepted):
    build, _, _ = accepted
    (record / "test/check.py").write_text((record / "test/check.py").read_text() + "\n# changed\n")
    with pytest.raises(TrackError):
        service.validate("tiny", "demo")
    with pytest.raises(TrackError):
        service.promote("tiny", "demo", build["id"], True)


def test_changed_environment_blocks_promotion(service, record, accepted):
    config = yaml.safe_load((record / "record.yaml").read_text())
    config["environment_probes"] = {"compiler": ["cc", "--version"]}
    (record / "record.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(TrackError):
        service.promote("tiny", "demo", accepted[0]["id"], True)


def test_failed_candidate_preserves_current(service, record, accepted):
    current = accepted[0]["id"]
    service.promote("tiny", "demo", current, True)
    source = record / "source/calculate.py"
    source.write_text(source.read_text().replace("sum(value * value for value in values)", "999"))
    replacement = service.build("tiny", "demo", wait_timeout=10)
    with pytest.raises(TrackError) as error:
        service.validate("tiny", "demo", replacement["id"], wait_timeout=10)
    assert error.value.code == 10
    metadata = service.store.get("record", "tiny/demo")
    assert metadata["current_build"] == current and metadata["status"] == "verified"


def test_failed_build_preserves_logs(service, record):
    (record / "build.sh").write_text("echo failure >&2\nexit 9\n")
    with pytest.raises(TrackError) as error:
        service.build("tiny", "demo", wait_timeout=10)
    assert error.value.code == 10
    build = error.value.result["build"]
    assert service.transport("demo").read(build["logs"] + "/stderr.log") == b"failure\n"


def test_resume_build_from_new_controller_uses_immutable_snapshot(service, record, config_path):
    script = record / "build.sh"
    script.write_text("sleep 0.3\n" + script.read_text())
    with pytest.raises(TrackError) as error:
        service.build("tiny", "demo", wait_timeout=0)
    assert error.value.code == 40
    operation_id = error.value.result["operation_id"]
    script.write_text("exit 99\n")
    other = Service(service.settings)
    try:
        resumed = other.resume(operation_id, wait_timeout=10)
        assert resumed["operations"][0]["state"] == "built"
        assert len(other.store.all("build")) == 1
    finally:
        other.store.close()


def test_git_commit_preserves_unrelated_staging(service, record, accepted):
    root = service.settings.root

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test User")
    git("config", "user.email", "test@example.invalid")
    (root / "unrelated.txt").write_text("keep staged\n")
    git("add", "unrelated.txt")
    result = service.promote("tiny", "demo", accepted[0]["id"])
    assert len(result["git_commit"]) == 40
    assert git("diff", "--cached", "--name-only") == "unrelated.txt"
    committed = git("show", "--pretty=", "--name-only", "HEAD").splitlines()
    assert committed and all(path.startswith("software/tiny/demo/") for path in committed)


def test_commit_failure_is_resumable_without_revalidation(service, record, accepted):
    with pytest.raises(TrackError) as error:
        service.promote("tiny", "demo", accepted[0]["id"])
    assert error.value.result["error"] == "git_required"
    operation_id = error.value.result["operation_id"]
    root = service.settings.root
    for args in (
        ("init", "-b", "main"),
        ("config", "user.name", "Test"),
        ("config", "user.email", "test@example.invalid"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    count = len(service.backend("demo").list(None, True))
    result = service.resume(operation_id)
    assert len(result["operations"][0]["git_commit"]) == 40
    assert len(service.backend("demo").list(None, True)) == count


def test_result_checkpoint_finishes_without_remote_access(service, record, monkeypatch):
    def crash(*args):
        raise RuntimeError("simulate crash after result persistence")

    with monkeypatch.context() as patch:
        patch.setattr(service_module, "project_record", crash)
        with pytest.raises(RuntimeError):
            service.build("tiny", "demo", wait_timeout=10)
    operation_id = service.store.all("build")[0]["id"]
    with monkeypatch.context() as patch:
        patch.setattr(service, "transport", crash)
        result = service.resume(operation_id)
    assert result["operations"][0]["state"] == "built"


def test_validation_checkpoint_finishes_without_remote_access(service, record, monkeypatch):
    service.build("tiny", "demo", wait_timeout=10)

    def crash(*args):
        raise RuntimeError("simulate disconnect after result persistence")

    with monkeypatch.context() as patch:
        patch.setattr(service_module, "project_record", crash)
        with pytest.raises(RuntimeError):
            service.validate("tiny", "demo", wait_timeout=10)
    operation_id = service.store.all("validation")[0]["id"]
    with monkeypatch.context() as patch:
        patch.setattr(service, "transport", crash)
        result = service.resume(operation_id)
    assert result["operations"][0]["state"] == "reference_pending"


def test_snapshot_tampering_refuses_resumed_execution(service, record, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(service, "_run_build", lambda operation, wait: operation)
        operation = service.build("tiny", "demo")
    (Path(operation["data"]["snapshot"]) / "build.sh").write_text("echo changed\n")
    with pytest.raises(TrackError) as error:
        service.resume(operation["id"])
    assert error.value.result["error"] == "snapshot_changed"
    assert service.store.all("build") == []


def test_recipe_change_blocks_promotion(service, record, accepted):
    (record / "build.sh").write_text("exit 99\n")
    with pytest.raises(TrackError) as error:
        service.promote("tiny", "demo", accepted[0]["id"], True)
    assert error.value.result["error"] == "promotion_refused"


def test_local_source_cannot_escape_record(service, record):
    config = yaml.safe_load((record / "record.yaml").read_text())
    config["source"]["url"] = "../outside"
    (record / "record.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(TrackError) as error:
        service.build("tiny", "demo")
    assert error.value.code == 2
    assert service.store.all("build") == []


def test_pending_promotion_does_not_commit_changed_test(service, record, accepted):
    with pytest.raises(TrackError) as error:
        service.promote("tiny", "demo", accepted[0]["id"])
    operation_id = error.value.result["operation_id"]
    (record / "test/input/values.json").write_text("[99]\n")
    with pytest.raises(TrackError) as resumed:
        service.resume(operation_id)
    assert resumed.value.result["error"] == "promotion_changed"


def test_failed_revalidation_blocks_older_pass(service, record, accepted):
    build = accepted[0]
    service.promote("tiny", "demo", build["id"], True)
    (Path(build["prefix"]) / "bin/calculate.py").write_text("raise SystemExit(7)\n")
    with pytest.raises(TrackError) as failed:
        service.validate("tiny", "demo", build["id"], wait_timeout=10)
    assert failed.value.code == 10
    assert (
        service.store.get("build", build["id"])["last_validation_id"]
        == (failed.value.result["validation"]["id"])
    )
    with pytest.raises(TrackError) as refused:
        service.promote("tiny", "demo", build["id"], True)
    assert refused.value.result["error"] == "promotion_refused"
    metadata = service.store.get("record", "tiny/demo")
    assert metadata["current_build"] == build["id"] and metadata["status"] == "broken"


def test_pending_promotion_rechecks_environment_and_source(service, record, accepted):
    with pytest.raises(TrackError) as pending:
        service.promote("tiny", "demo", accepted[0]["id"])
    assert pending.value.result["error"] == "git_required"
    operation_id = pending.value.result["operation_id"]
    declaration = record / "record.yaml"
    original = declaration.read_bytes()
    changed = yaml.safe_load(original)
    changed["environment_probes"] = {"compiler": ["different-compiler", "--version"]}
    declaration.write_text(yaml.safe_dump(changed))
    with pytest.raises(TrackError) as refused:
        service.resume(operation_id)
    assert refused.value.result["error"] == "promotion_changed"
    declaration.write_bytes(original)
    (record / "source/calculate.py").write_text("raise SystemExit(7)\n")
    with pytest.raises(TrackError) as refused:
        service.resume(operation_id)
    assert refused.value.result["error"] == "source_changed"
    assert service.store.operation(operation_id)["status"] == "commit_pending"


def test_working_tree_completion_lifecycle(service, record, tmp_path, monkeypatch):
    source = tmp_path / "user-source"
    source.mkdir()
    program = source / "calculate.py"
    program.write_bytes((record / "source/calculate.py").read_bytes())
    for args in (
        ("init", "-b", "main"),
        ("config", "user.name", "Test"),
        ("config", "user.email", "test@example.invalid"),
        ("add", "calculate.py"),
        ("commit", "-m", "Test source"),
    ):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    captured = program.read_text() + "\n# User's uncommitted change\n"
    program.write_text(captured)
    (source / "install.sh").write_text("#!/bin/sh\necho 'user install script'\n")
    (source / "install.sh").chmod(0o700)
    (source / "stale.o").write_bytes(b"old object")
    (source / "stale.x").write_bytes(b"old executable")
    declaration = yaml.safe_load((record / "record.yaml").read_text())
    declaration.update(
        source={"type": "working_tree", "url": str(source), "exclude": ["*.o", "*.x"]},
        validation_mode="completion",
        metrics={},
    )
    (record / "record.yaml").write_text(yaml.safe_dump(declaration))
    (record / "build.sh").write_text(
        '#!/bin/bash\nset -eu\n"$SRC_DIR/install.sh"\n'
        'mkdir -p "$PREFIX/bin"\ncp "$SRC_DIR/calculate.py" "$PREFIX/bin/calculate.py"\n'
    )
    checker = Path(__file__).resolve().parents[1] / "examples/graspa/record/test/check.py"
    (record / "test/check.py").write_bytes(checker.read_bytes())
    # Synthetic application output: no GPU or site execution is involved.
    output = (
        "SYNTHETIC TEST OUTPUT\nINITIALIZATION PHASE ENDS\nPRODUCTION PHASE ENDS\n"
        "END OF PROGRAM!\nTotal GPU Energy:\nWork took 1.5 seconds\n"
        "*** GPU DRIFT (GPU FINAL - CPU FINAL) ***\nTotal Energy: -6740.0\n"
    )
    log = record / "test/input/synthetic.log"
    log.write_text(output)
    job = record / "test/job.sh.j2"
    job.write_text(
        job.read_text() + '\ncp {{ (input_dir + "/synthetic.log") | quote }} graspa.stdout.log\n'
    )
    with monkeypatch.context() as patch:
        patch.setattr(service, "_run_build", lambda operation, wait: operation)
        operation = service.build("tiny", "demo")
    frozen = Path(operation["data"]["source_snapshot"])
    assert {p.name for p in frozen.iterdir()} == {"calculate.py", "install.sh"}
    assert operation["data"]["source_commit"]
    assert (frozen / "calculate.py").read_text() == captured
    files = operation["data"]["source_files"]
    assert set(files) == {"calculate.py", "install.sh"}
    install = files["install.sh"]
    assert install == {
        "original_path": str(source / "install.sh"),
        "snapshot_path": str(frozen / "install.sh"),
        "build_path": operation["data"]["directory"] + "/source/install.sh",
        "sha256": hashlib.sha256((source / "install.sh").read_bytes()).hexdigest(),
    }
    program.write_text("raise SystemExit(99)\n")  # Later edits must not affect resume.
    build = service.resume(operation["id"], wait_timeout=10)["operations"][0]
    # The committed build keeps only content hashes; full paths stay in the operation.
    assert build["source_files"] == {name: info["sha256"] for name, info in files.items()}
    manifest = json.loads((record / "manifest.json").read_text())
    assert str(source) not in json.dumps(manifest["builds"][0]["source_files"])
    assert files["calculate.py"]["sha256"] == hashlib.sha256(captured.encode()).hexdigest()
    assert Path(install["build_path"]).read_bytes() == Path(install["snapshot_path"]).read_bytes()
    assert (Path(build["record_snapshot"]) / "build.sh").read_bytes() == (
        record / "build.sh"
    ).read_bytes()
    assert (Path(build["prefix"]) / "bin/calculate.py").read_text() == captured
    assert program.read_text() == "raise SystemExit(99)\n"
    assert (source / "stale.o").read_bytes() == b"old object"
    validation = service.validate("tiny", "demo", build["id"], wait_timeout=10)
    assert not (Path(validation["logs"]) / "gpu-info.txt").exists()
    assert (Path(validation["record_snapshot"]) / "test/input/synthetic.log").read_text() == output
    assert validation["state"] == "passed" and validation["validation_mode"] == "completion"
    assert validation["metrics"]["gpu_drift_internal"] == -6740.0
    assert validation["reference_hash"] is None
    assert not (record / "test/reference.json").exists()
    promoted = service.promote("tiny", "demo", build["id"], True)
    assert promoted["manifest"]["status"] == "validated"
    assert promoted["manifest"]["simulated"] is True
    # A zero-exit application with incomplete output still fails its completion checker.
    log.write_text(output.replace("PRODUCTION PHASE ENDS", "truncated"))
    with pytest.raises(TrackError) as failed:
        service.validate("tiny", "demo", build["id"], wait_timeout=10)
    assert failed.value.code == 10
    assert service.store.get("record", "tiny/demo")["status"] == "broken"

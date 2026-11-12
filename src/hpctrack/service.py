import json
import shlex
import time
from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateError

from hpctrack.backends.base import check_budget
from hpctrack.backends.fake import FakeBackend
from hpctrack.backends.iri import IRIBackend
from hpctrack.backends.pbs_ssh import PBSBackend
from hpctrack.errors import TrackError
from hpctrack.models import TERMINAL, JobSpec
from hpctrack.records import (
    check_reference_file,
    commit_record,
    compare,
    contract_hash,
    init_record,
    load_record,
    project_record,
    snapshot,
    validate_metrics,
)
from hpctrack.remote import LocalTransport, SSHTransport, prepare_worker, worker_result
from hpctrack.store import Store
from hpctrack.util import digest, now, read_tree, tree_hash


class Service:
    def __init__(self, settings, backend_factory=None, transport_factory=None):
        self.settings = settings
        self.store = Store(settings.state)
        self.backend_factory = backend_factory
        self.transport_factory = transport_factory

    def transport(self, machine, live=True):
        config = self.settings.machine(machine, live=live)
        if self.transport_factory:
            return self.transport_factory(machine, config)
        return (LocalTransport if config.transport == "local" else SSHTransport)(machine, config)

    def backend(self, machine):
        config = self.settings.machine(machine, live=True)
        if self.backend_factory:
            return self.backend_factory(machine, config)
        if config.backend == "iri":
            return IRIBackend(machine, config)
        return (FakeBackend if config.backend == "fake" else PBSBackend)(
            machine, config, self.transport(machine)
        )

    def doctor(self):
        results = {}
        codes = []
        for name, config in self.settings.config.machines.items():
            item = {
                "simulated": config.backend == "fake",
                "proxy": "configured" if config.proxy else "unset",
            }
            for component, check in (
                ("ssh", lambda n=name: self.transport(n).check()),
                (
                    "backend",
                    lambda n=name: {
                        "state": "reachable",
                        "jobs": len(self.backend(n).list(None, False)),
                    },
                ),
            ):
                try:
                    item[component] = check()
                except TrackError as exc:
                    item[component] = exc.result
                    codes.append(exc.code)
            results[name] = item
        if codes:
            raise TrackError(
                "health_check_failed",
                "Some health checks failed",
                20 if 20 in codes else codes[0],
                machines=results,
            )
        return {"machines": results, "state_dir": str(self.settings.state)}

    def init(self, name, machine, template=None):
        path = self.settings.record_path(name, machine)
        config = self.settings.machine(machine)
        init_record(path, config, template)
        record = {
            "record_key": f"{name}/{machine}",
            "name": name,
            "machine": machine,
            "status": "unvalidated",
            "current_build": None,
            "simulated": config.backend == "fake",
        }
        self.store.put("record", record["record_key"], record, machine)
        return project_record(self.settings, self.store, name, machine)

    def record(self, name, machine):
        path = self.settings.record_path(name, machine)
        metadata = self.store.get("record", f"{name}/{machine}")
        if not metadata:
            raise TrackError("unknown_record", "Initialize this record with sw init", 2)
        return path, load_record(path), metadata

    def fingerprint(self, machine, record):
        transport = self.transport(machine)
        if transport.simulated:
            facts = {
                "environment": "local-demo-v1",
                "simulated": True,
                "declared_probes": record.environment_probes,
            }
        else:
            facts = {"simulated": False}
            probes = {"kernel": ["uname", "-sr"], **record.environment_probes}
            for key, argv in probes.items():
                result = transport.run(argv)
                if result.returncode:
                    raise TrackError("fingerprint_failed", f"Environment probe {key} failed")
                facts[key] = result.stdout.decode(errors="replace").strip()
        return {"hash": digest(facts), "facts": facts}

    def _operation(self, kind, machine, name=None, **data):
        config = self.settings.machine(machine, live=True)
        data.update(
            machine=machine,
            simulated=config.backend == "fake",
            machine_hash=digest(config.model_dump()),
        )
        if name:
            data.update(name=name, record_key=f"{name}/{machine}")
        return self.store.new_operation(kind, data)

    def _save(self, operation, status=None):
        if status:
            operation["status"] = status
        self.store.save_operation(operation)

    def _stage_tree(self, transport, path, destination):
        for name, content in read_tree(path).items():
            transport.write(f"{destination}/{name}", content)

    def build(self, name, machine, ref=None, wait_timeout=30):
        path, record, _ = self.record(name, machine)
        transport, config = self.transport(machine), self.settings.machine(machine, live=True)
        if record.source.type == "local":
            if ref is not None:
                raise TrackError(
                    "invalid_ref", "Local demo sources use content snapshots, not refs", 2
                )
            if not transport.simulated:
                raise TrackError("local_source_refused", "Local source snapshots are demo-only", 30)
            source_path = (path / record.source.url).resolve()
            if path not in source_path.parents:
                raise TrackError(
                    "source_outside_record", "Demo source must be inside its record", 30
                )
            resolved = tree_hash(read_tree(source_path))
        else:
            if transport.simulated:
                raise TrackError(
                    "demo_source_required",
                    "Demo builds require an in-record local source snapshot",
                    30,
                )
            requested = ref or record.source.ref
            if len(requested) == 40 and all(c in "0123456789abcdef" for c in requested.lower()):
                resolved = requested.lower()
            else:
                response = transport.run(
                    ["git", "ls-remote", record.source.url, requested, requested + "^{}"]
                )
                rows = response.stdout.decode().strip().splitlines()
                peeled = [line for line in rows if line.endswith("^{}")]
                commits = {line.split()[0] for line in (peeled or rows) if line.strip()}
                if response.returncode or len(commits) != 1:
                    raise TrackError(
                        "source_unresolved", "Source ref did not resolve to one immutable commit", 2
                    )
                resolved = commits.pop()
        fingerprint = self.fingerprint(machine, record)
        operation = self._operation(
            "build",
            machine,
            name,
            source_ref=resolved,
            fingerprint=fingerprint,
            source={**record.source.model_dump(), "ref": ref or record.source.ref},
        )
        data = operation["data"]
        data["directory"] = f"{config.work_root}/builds/{operation['id']}"
        data["prefix"] = f"{config.software_root}/{name}/{operation['id']}"
        data["snapshot"] = str(
            snapshot(path, self.settings.state / "operations" / operation["id"] / "record")
        )
        data["snapshot_hash"] = tree_hash(read_tree(Path(data["snapshot"])))
        data["recipe_hash"] = digest((Path(data["snapshot"]) / "build.sh").read_bytes())
        if record.source.type == "local":
            data["source_ref"] = tree_hash(read_tree(Path(data["snapshot"]) / record.source.url))
        self._save(operation, "prepared")
        return self._run_build(operation, wait_timeout)

    def _run_build(self, operation, wait_timeout):
        data = operation["data"]
        existing = self.store.get("build", operation["id"])
        if existing:
            return self._finish_build(operation, existing)
        transport = self.transport(data["machine"])
        directory = data["directory"]
        if operation["status"] == "prepared":
            self._verify_snapshot(data)
            self._stage_tree(transport, Path(data["snapshot"]), directory + "/recipe")
            transport.mkdir(data["prefix"])
            source_dir = directory + "/source"
            if data["source"]["type"] == "local":
                source_dir = directory + "/recipe/" + data["source"]["url"]
            environment = {
                "PREFIX": data["prefix"],
                "SRC_REF": data["source_ref"],
                "SRC_URL": data["source"]["url"],
                "SRC_DIR": source_dir,
            }
            prepare_worker(
                transport,
                directory,
                ["bash", directory + "/recipe/build.sh"],
                directory,
                environment,
            )
            self._save(operation, "launching")
            try:
                transport.start(directory)
            except TrackError as exc:
                exc.result["operation_id"] = operation["id"]
                raise
            self._save(operation, "running")
        deadline = time.monotonic() + wait_timeout
        while True:
            result = worker_result(transport, directory)
            if result is not None:
                break
            if time.monotonic() >= deadline:
                raise TrackError(
                    "operation_pending",
                    "Build is pending; resume will inspect its existing worker",
                    40,
                    operation_id=operation["id"],
                    logs=directory,
                )
            time.sleep(min(0.1 if transport.simulated else 2, max(0, deadline - time.monotonic())))
        passed = result.get("exit_status") == 0
        build = {
            "id": operation["id"],
            "record_key": data["record_key"],
            "machine": data["machine"],
            "name": data["name"],
            "prefix": data["prefix"],
            "built_at": data.get("completed_at", now()),
            "state": "built" if passed else "failed",
            "source_ref": data["source_ref"],
            "source": data["source"],
            "recipe_hash": data["recipe_hash"],
            "build_fingerprint": data["fingerprint"],
            "simulated": data["simulated"],
            "logs": directory,
        }
        self.store.put("build", build["id"], build, data["machine"], operation["id"])
        return self._finish_build(operation, build)

    def _finish_build(self, operation, build):
        data = operation["data"]
        passed = build["state"] == "built"
        project_record(self.settings, self.store, data["name"], data["machine"])
        self._save(operation, "finished" if passed else "failed")
        if not passed:
            raise TrackError("build_failed", "Build recipe failed", 10, build=build)
        return build

    def _verify_snapshot(self, data):
        if tree_hash(read_tree(Path(data["snapshot"]))) != data["snapshot_hash"]:
            raise TrackError(
                "snapshot_changed", "Stored operation inputs changed; refusing remote execution", 30
            )

    def _spec(self, operation, script, resources, workdir):
        data = operation["data"]
        config = self.settings.machine(data["machine"], live=True)
        spec = JobSpec(
            **resources,
            operation_id=operation["id"],
            machine=data["machine"],
            name=f"ht-{operation['kind'][:8]}-{operation['id']}",
            script=script,
            workdir=workdir,
            stdout_path=workdir + "/stdout.log",
            stderr_path=workdir + "/stderr.log",
            filesystems=config.filesystems,
            environment={"HPCTRACK_OPERATION_ID": operation["id"]},
        )
        check_budget(spec, config)
        return spec

    def _remember_job(self, job, owned=False, project=None):
        key = f"{job.machine}/{job.job_id}"
        old = self.store.get("job", key) or {}
        values = job.model_dump()
        data = {
            **old,
            **{key: value for key, value in values.items() if value is not None},
            "tool_owned": old.get("tool_owned", False) or owned,
            "project": project if project is not None else old.get("project"),
        }
        data.pop("last_observed_at", None)
        if not job.name and old.get("name"):
            data["name"] = old["name"]
        if job.state == "unknown" and old.get("state") not in (None, "unknown"):
            data["last_known_state"] = old["state"]
        changed = {k: v for k, v in old.items() if k != "last_observed_at"} != data
        data["last_observed_at"] = now()
        self.store.put("job", key, data, job.machine, job.operation_id, audit=changed)
        return data

    def _submit(self, operation):
        data = operation["data"]
        backend = self.backend(data["machine"])
        if operation["status"] in ("submitting", "submission_unknown"):
            matches = [
                job for job in backend.list(None, True) if job.operation_id == operation["id"]
            ]
            if len(matches) != 1:
                raise TrackError(
                    "submission_unknown",
                    "Cannot reconcile submission; refusing to resubmit",
                    40,
                    operation_id=operation["id"],
                )
            job = matches[0]
        elif data.get("job_id"):
            return backend.get(data["job_id"])
        else:
            spec = JobSpec.model_validate(data["spec"])
            config = self.settings.machine(data["machine"], live=True)
            check_budget(spec, config)
            active = backend.list(config.user, False)
            if (
                sum(job.queue == spec.queue and job.state not in TERMINAL for job in active)
                >= config.queues[spec.queue].max_active
            ):
                raise TrackError(
                    "queue_full",
                    "Configured queue occupancy limit reached; resume later",
                    30,
                    operation_id=operation["id"],
                )
            self._save(operation, "submitting")
            try:
                job = backend.submit(spec)
            except TrackError as exc:
                # Even a service error might follow acceptance. Do not retry blindly.
                self._save(operation, "submission_unknown")
                exc.result["operation_id"] = operation["id"]
                raise
            except Exception as exc:
                self._save(operation, "submission_unknown")
                raise TrackError(
                    "submission_unknown",
                    "Submission outcome could not be recorded",
                    40,
                    operation_id=operation["id"],
                ) from exc
        data["job_id"] = job.job_id
        self._remember_job(job, owned=True, project=data.get("project"))
        self._save(operation, "running")
        return job

    def submit_job(self, machine, script, resources, workdir=None, project=None):
        operation = self._operation("submit", machine, project=project)
        config = self.settings.machine(machine, live=True)
        directory = workdir or f"{config.work_root}/jobs/{operation['id']}"
        spec = self._spec(operation, script, resources, directory)
        self.transport(machine).mkdir(directory)
        operation["data"]["spec"] = spec.model_dump()
        self._save(operation, "prepared")
        job = self._submit(operation)
        self._save(operation, "finished")
        return {
            "operation_id": operation["id"],
            "job": self._remember_job(job, owned=True, project=project),
        }

    def validate(self, name, machine, build_id=None, wait_timeout=30):
        path, record, metadata = self.record(name, machine)
        if build_id is None:
            build_id = metadata["current_build"]
            if not build_id:
                builds = [
                    b
                    for b in self.store.all("build")
                    if b["record_key"] == metadata["record_key"] and b["state"] == "built"
                ]
                build_id = max(builds, key=lambda b: b["built_at"])["id"] if builds else None
        build = self.store.get("build", build_id)
        if not build or build["record_key"] != metadata["record_key"] or build["state"] != "built":
            raise TrackError(
                "invalid_build", "Select a successful build belonging to this record", 30
            )
        reference = self.store.get("reference", metadata["record_key"])
        check_reference_file(path, reference)
        if reference and reference["contract_hash"] != contract_hash(path, record):
            raise TrackError(
                "inputs_changed",
                "Accepted reference belongs to different test inputs or tolerances",
                30,
            )
        operation = self._operation(
            "validate",
            machine,
            name,
            build_id=build_id,
            contract_hash=contract_hash(path, record),
            reference=reference,
            reference_hash=digest(reference) if reference else None,
            fingerprint=self.fingerprint(machine, record),
            tolerances=record.metrics,
        )
        config = self.settings.machine(machine, live=True)
        directory = f"{config.work_root}/validations/{operation['id']}"
        data = operation["data"]
        data["directory"] = directory
        data["snapshot"] = str(
            snapshot(path, self.settings.state / "operations" / operation["id"] / "record")
        )
        data["snapshot_hash"] = tree_hash(read_tree(Path(data["snapshot"])))
        environment = Environment(undefined=StrictUndefined)
        frozen_path = Path(data["snapshot"])
        frozen_record = load_record(frozen_path)
        if contract_hash(frozen_path, frozen_record) != data["contract_hash"]:
            raise TrackError(
                "inputs_changed", "Validation inputs changed while being snapshotted", 30
            )
        environment.filters["quote"] = shlex.quote
        try:
            body = environment.from_string((frozen_path / "test/job.sh.j2").read_text()).render(
                prefix=build["prefix"],
                workdir=directory,
                input_dir=directory + "/input",
                nodes=record.validation.nodes,
                source_ref=build["source_ref"],
            )
        except TemplateError as exc:
            raise TrackError(
                "invalid_template", "Validation template could not be rendered", 2
            ) from exc
        # Validate the body before wrapping it, so embedded resource directives cannot disappear.
        self._spec(operation, body, record.validation.model_dump(), directory)
        checker = ["python3", directory + "/check.py", directory]
        if reference:
            checker.append(directory + "/reference.json")
        script = (
            "set -eu\n"
            + body
            + "\n"
            + shlex.join(checker)
            + " > "
            + shlex.quote(directory + "/check.json")
            + "\n"
        )
        data["spec"] = self._spec(
            operation, script, record.validation.model_dump(), directory
        ).model_dump()
        self._save(operation, "prepared")
        return self._run_validation(operation, wait_timeout)

    def _run_validation(self, operation, wait_timeout):
        data = operation["data"]
        existing = self.store.get("validation", operation["id"])
        if existing:
            return self._finish_validation(operation, existing)
        transport = self.transport(data["machine"])
        if operation["status"] == "prepared":
            self._verify_snapshot(data)
            path = Path(data["snapshot"])
            self._stage_tree(transport, path / "test/input", data["directory"] + "/input")
            transport.write(data["directory"] + "/check.py", (path / "test/check.py").read_bytes())
            if data["reference"]:
                transport.write(
                    data["directory"] + "/reference.json", json.dumps(data["reference"])
                )
        job = self._submit(operation)
        deadline = time.monotonic() + wait_timeout
        backend = self.backend(data["machine"])
        while job.state not in TERMINAL:
            job = backend.get(job.job_id)
            self._remember_job(job, owned=True)
            if job.state in TERMINAL:
                break
            if time.monotonic() >= deadline:
                raise TrackError(
                    "operation_pending",
                    "Validation is pending; resume uses the existing job",
                    40,
                    operation_id=operation["id"],
                    job_id=job.job_id,
                )
            time.sleep(min(0.1 if transport.simulated else 2, max(0, deadline - time.monotonic())))
        checker = {}
        raw = transport.read(data["directory"] + "/check.json")
        try:
            checker = json.loads(raw) if raw else {}
            if not isinstance(checker, dict) or not isinstance(checker.get("passed"), bool):
                raise ValueError
            json.dumps(checker, allow_nan=False)
            if not isinstance(checker.get("messages", []), list):
                raise ValueError
            validate_metrics(checker.get("metrics"), data["tolerances"])
        except (ValueError, TypeError, TrackError):
            checker = {
                "passed": False,
                "metrics": {},
                "messages": ["Checker output missing or invalid"],
            }
        passed = job.state == "finished" and job.exit_status in (0, None) and checker["passed"]
        if passed and data["reference"]:
            passed = compare(checker["metrics"], data["reference"])
        state = ("passed" if data["reference"] else "reference_pending") if passed else "failed"
        validation = {
            "id": operation["id"],
            "record_key": data["record_key"],
            "build_id": data["build_id"],
            "machine": data["machine"],
            "job_id": job.job_id,
            "state": state,
            "metrics": checker["metrics"],
            "messages": checker.get("messages", []),
            "contract_hash": data["contract_hash"],
            "reference_hash": data["reference_hash"],
            "fingerprint": data["fingerprint"],
            "tolerances": data["tolerances"],
            "simulated": data["simulated"],
            "logs": data["directory"],
            "completed_at": now(),
        }
        validation = self.store.get("validation", operation["id"]) or validation
        self.store.put("validation", operation["id"], validation, data["machine"], operation["id"])
        return self._finish_validation(operation, validation)

    def _finish_validation(self, operation, validation):
        data = operation["data"]
        state = validation["state"]
        if state == "passed":
            build = self.store.get("build", data["build_id"])
            build["last_validation_id"] = operation["id"]
            self.store.put("build", build["id"], build, data["machine"], operation["id"])
        metadata = self.store.get("record", data["record_key"])
        if metadata["current_build"] == data["build_id"]:
            metadata["status"] = "verified" if state == "passed" else "broken"
            self.store.put("record", data["record_key"], metadata, data["machine"], operation["id"])
        project_record(self.settings, self.store, data["name"], data["machine"])
        self._save(operation, "failed" if state == "failed" else "finished")
        if state == "failed":
            raise TrackError(
                "validation_failed",
                "Calculation or scientific comparison failed",
                10,
                validation=validation,
            )
        return validation

    def accept_reference(self, name, machine, validation_id, yes):
        if not yes or self.store.actor != "human":
            raise TrackError(
                "human_confirmation_required",
                "A human must accept the reviewed reference with --yes",
                30,
            )
        path, record, metadata = self.record(name, machine)
        validation = self.store.get("validation", validation_id)
        if (
            not validation
            or validation["record_key"] != metadata["record_key"]
            or validation["state"] != "reference_pending"
        ):
            raise TrackError(
                "invalid_candidate", "Choose a successful candidate-reference validation", 30
            )
        if validation["contract_hash"] != contract_hash(path, record):
            raise TrackError(
                "inputs_changed", "Test inputs or tolerances changed since candidate extraction", 30
            )
        reference = {
            "schema_version": 1,
            "record_key": metadata["record_key"],
            "validation_id": validation_id,
            "simulated": validation["simulated"],
            "contract_hash": validation["contract_hash"],
            "metrics": {
                key: {"value": validation["metrics"][key], "absolute_tolerance": tolerance}
                for key, tolerance in validation["tolerances"].items()
            },
        }
        existing = self.store.get("reference", metadata["record_key"])
        if existing and existing != reference:
            raise TrackError(
                "reference_exists",
                "Reference replacement requires a separate reviewed migration",
                30,
            )
        self.store.put("reference", metadata["record_key"], reference, machine)
        project_record(self.settings, self.store, name, machine)
        return reference

    def promote(self, name, machine, build_id, no_commit=False):
        path, record, metadata = self.record(name, machine)
        build = self.store.get("build", build_id)
        reference = self.store.get("reference", metadata["record_key"])
        check_reference_file(path, reference)
        validation = (
            self.store.get("validation", build.get("last_validation_id")) if build else None
        )
        if (
            not build
            or build["record_key"] != metadata["record_key"]
            or not validation
            or validation["state"] != "passed"
            or not reference
            or validation["reference_hash"] != digest(reference)
            or validation["contract_hash"] != contract_hash(path, record)
            or build["recipe_hash"] != digest((path / "build.sh").read_bytes())
            or build["source"]["type"] != record.source.type
            or build["source"]["url"] != record.source.url
            or validation["fingerprint"]["hash"] != self.fingerprint(machine, record)["hash"]
        ):
            raise TrackError(
                "promotion_refused", "Build needs a passing comparison with current provenance", 30
            )
        if (
            record.source.type == "local"
            and tree_hash(read_tree(path / record.source.url)) != build["source_ref"]
        ):
            raise TrackError(
                "source_changed", "Demo source no longer matches the built snapshot", 30
            )
        operation = self._operation(
            "promote",
            machine,
            name,
            build_id=build_id,
            no_commit=no_commit,
            validation_id=validation["id"],
            previous_build=metadata["current_build"],
        )
        self._save(operation, "prepared")
        return self._run_promotion(operation)

    def _run_promotion(self, operation):
        data = operation["data"]
        metadata = self.store.get("record", data["record_key"])
        if metadata["current_build"] not in (data["previous_build"], data["build_id"]):
            raise TrackError(
                "promotion_superseded", "A different build was promoted after this operation", 30
            )
        path, record, _ = self.record(data["name"], data["machine"])
        reference = self.store.get("reference", data["record_key"])
        check_reference_file(path, reference)
        validation = self.store.get("validation", data["validation_id"])
        build = self.store.get("build", data["build_id"])
        if (
            not reference
            or validation["reference_hash"] != digest(reference)
            or validation["contract_hash"] != contract_hash(path, record)
            or build["recipe_hash"] != digest((path / "build.sh").read_bytes())
        ):
            raise TrackError(
                "promotion_changed", "Promotion evidence changed before the commit completed", 30
            )
        metadata.update(current_build=data["build_id"], status="verified")
        self.store.put("record", data["record_key"], metadata, data["machine"], operation["id"])
        self._save(operation, "commit_pending")
        manifest = project_record(self.settings, self.store, data["name"], data["machine"])
        if data["no_commit"]:
            commit = "skipped_explicitly"
        else:
            try:
                commit = commit_record(
                    self.settings.root,
                    self.settings.record_path(data["name"], data["machine"]),
                    operation["id"],
                    data["name"],
                )
            except TrackError as exc:
                exc.result["operation_id"] = operation["id"]
                raise
        data["git_commit"] = commit
        self._save(operation, "finished")
        return {"manifest": manifest, "git_commit": commit, "operation_id": operation["id"]}

    def sync(self, machine=None):
        jobs, errors = [], []
        for name in [machine] if machine else self.settings.config.machines:
            try:
                backend = self.backend(name)
                seen = set()
                for job in backend.list(None, True):
                    seen.add(job.job_id)
                    jobs.append(self._remember_job(job))
                for previous in self.store.all("job"):
                    if (
                        previous["machine"] == name
                        and previous["state"] not in TERMINAL
                        and previous["job_id"] not in seen
                    ):
                        jobs.append(self._remember_job(backend.get(previous["job_id"])))
            except TrackError as exc:
                errors.append(exc)
        if errors:
            raise TrackError(
                "sync_partial",
                "Some machines could not be synchronized",
                errors[0].code,
                jobs=jobs,
                errors=[exc.result for exc in errors],
            )
        return {"jobs": jobs, "observed_at": now()}

    def cancel(self, machine, job_id, yes=False):
        key = f"{machine}/{job_id}"
        job = self.store.get("job", key)
        if not yes and not (job and job.get("tool_owned")):
            raise TrackError(
                "confirmation_required", "External job cancellation requires --yes", 30
            )
        operation = self._operation("cancel", machine, job_id=job_id)
        self._save(operation, "cancelling")
        self.backend(machine).cancel(job_id)
        self._save(operation, "finished")
        return {"machine": machine, "job_id": job_id, "cancel_requested": True}

    def resume(self, operation_id=None, wait_timeout=30):
        operations = [self.store.operation(operation_id)] if operation_id else self.store.pending()
        results = []
        for operation in operations:
            data = operation["data"]
            if operation["status"] in ("finished", "failed"):
                results.append(operation)
                continue
            if operation["status"] == "preparing":
                operation["data"]["failure"] = "preparation_incomplete; no launch was authorized"
                self._save(operation, "failed")
                results.append(operation)
                continue
            if (
                digest(self.settings.machine(data["machine"], live=True).model_dump())
                != data["machine_hash"]
            ):
                raise TrackError(
                    "config_changed",
                    "Restore the operation's machine configuration before resume",
                    30,
                )
            if operation["kind"] == "build":
                results.append(self._run_build(operation, wait_timeout))
            elif operation["kind"] == "validate":
                results.append(self._run_validation(operation, wait_timeout))
            elif operation["kind"] == "submit":
                job = self._submit(operation)
                self._save(operation, "finished")
                results.append(job.model_dump())
            elif operation["kind"] == "promote":
                results.append(self._run_promotion(operation))
            elif operation["kind"] == "cancel":
                job = self.backend(data["machine"]).get(data["job_id"])
                if job.state not in TERMINAL:
                    raise TrackError(
                        "cancel_pending", "Cancellation is not confirmed; inspect the job", 40
                    )
                self._save(operation, "finished")
                results.append(job.model_dump())
        return {"operations": results}

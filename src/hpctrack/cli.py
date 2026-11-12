import json
from pathlib import Path

import click
from pydantic import ValidationError

from hpctrack import __version__
from hpctrack.backends.base import walltime_seconds
from hpctrack.config import Settings, init_workspace, template_names, workspace_config
from hpctrack.errors import TrackError
from hpctrack.models import TERMINAL
from hpctrack.records import HEADINGS
from hpctrack.service import Service


def json_flag(function):
    return click.option(
        "--json", "json_output", is_flag=True, expose_value=False, help="Emit JSON (the default)."
    )(function)


def machine_option(function):
    return click.option("--machine", required=True)(function)


def wait_option(function):
    return click.option(
        "--wait-timeout",
        type=click.FloatRange(min=0),
        default=30.0,
        show_default=True,
        help="Seconds to wait; timeout does not cancel work.",
    )(function)


WORKSPACE_FREE = ("init", "templates")


@click.group()
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, path_type=Path),
    help="Data home; defaults to $HPCTRACK_HOME, then ~/.hpctrack.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    help="Advanced: explicit configuration file; its directory becomes the root.",
)
@click.option("--state-dir", type=click.Path(path_type=Path))
@click.version_option(__version__)
@json_flag
@click.pass_context
def cli(ctx, workspace, config_path, state_dir):
    """Track HPC jobs and reproducible software records. Global options precede commands."""
    ctx.meta["workspace"] = workspace
    if ctx.invoked_subcommand in WORKSPACE_FREE:
        return
    service = Service(Settings(config_path or workspace_config(workspace), state_dir))
    ctx.obj = service
    ctx.call_on_close(service.store.close)


@cli.command("init")
@click.option(
    "--machines",
    default="demo",
    show_default=True,
    help="Packaged machine template; see templates list.",
)
@click.option("--no-git", is_flag=True, help="Do not initialize a Git repository.")
@json_flag
@click.pass_context
def init_workspace_command(ctx, machines, no_git):
    """Create a per-user workspace (records, ledger state, agent rules)."""
    return init_workspace(ctx.meta["workspace"], machines, not no_git)


@cli.group()
@json_flag
def templates():
    """Packaged record and machine templates."""


@templates.command("list")
@json_flag
def list_templates():
    return {"records": template_names("records"), "machines": template_names("machines")}


@cli.command()
@json_flag
@click.pass_obj
def doctor(service):
    """Check configured services independently without authenticating."""
    return service.doctor()


@cli.command()
@click.argument("machine")
@json_flag
@click.pass_obj
def connect(service, machine):
    """Human-only interactive SSH authentication."""
    if service.store.actor != "human":
        raise TrackError("human_only", "Agents must never authenticate", 30)
    transport = service.transport(machine, live=False)
    return transport.check() if transport.config.transport == "local" else transport.connect()


@cli.command()
@json_flag
@click.pass_obj
def status(service):
    """Show stored records and active jobs; use jobs sync for fresh observations."""
    return {
        "software": service.store.all("record"),
        "jobs": [job for job in service.store.all("job") if job["state"] not in TERMINAL],
    }


@cli.group()
@json_flag
def jobs():
    """Submit, inspect, synchronize, label, and cancel jobs."""


@jobs.command("submit")
@click.argument("script", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@machine_option
@click.option("--nodes", type=click.IntRange(min=1), required=True)
@click.option("--walltime", required=True, help="HH:MM:SS or seconds")
@click.option("--queue", required=True)
@click.option("--account", required=True)
@click.option("--workdir")
@click.option("--project")
@json_flag
@click.pass_obj
def submit(service, script, machine, nodes, walltime, queue, account, workdir, project):
    with service.store.mutation():
        return service.submit_job(
            machine,
            script.read_text(),
            {
                "nodes": nodes,
                "walltime": walltime_seconds(walltime),
                "queue": queue,
                "account": account,
            },
            workdir,
            project,
        )


@jobs.command("list")
@click.option("--machine")
@click.option("--project")
@click.option("--all", "include_finished", is_flag=True)
@json_flag
@click.pass_obj
def list_jobs(service, machine, project, include_finished):
    if machine:
        service.settings.machine(machine)
    return {
        "jobs": [
            job
            for job in service.store.all("job")
            if (not machine or job["machine"] == machine)
            and (not project or job.get("project") == project)
            and (include_finished or job["state"] not in TERMINAL)
        ]
    }


@jobs.command()
@click.option("--machine")
@json_flag
@click.pass_obj
def sync(service, machine):
    with service.store.mutation():
        return service.sync(machine)


@jobs.command()
@click.argument("job_id")
@machine_option
@json_flag
@click.pass_obj
def show(service, job_id, machine):
    job = service.backend(machine).get(job_id)
    data = {"job": job.model_dump(), "output_tail": None}
    if job.stdout_path:
        try:
            transport = service.transport(machine)
            if transport.simulated:
                raw = transport.read(job.stdout_path)
                data["output_tail"] = (
                    "\n".join(raw.decode(errors="replace").splitlines()[-40:])[-16000:]
                    if raw
                    else None
                )
            else:
                data["output_tail"] = transport.tail(job.stdout_path)
        except TrackError as exc:
            raise TrackError(
                exc.result["error"],
                exc.result["message"],
                exc.code,
                data=data,
                fix=exc.result.get("fix"),
            ) from exc
    return data


@jobs.command()
@click.argument("job_id")
@machine_option
@click.option("--project", required=True)
@json_flag
@click.pass_obj
def tag(service, job_id, machine, project):
    with service.store.mutation():
        key = f"{machine}/{job_id}"
        job = service.store.get("job", key)
        if not job:
            raise TrackError("unknown_job", "Synchronize the job before tagging it", 2)
        job["project"] = project
        service.store.put("job", key, job, machine)
        return job


@jobs.command()
@click.argument("job_id")
@machine_option
@click.option("--yes", is_flag=True)
@json_flag
@click.pass_obj
def cancel(service, job_id, machine, yes):
    with service.store.mutation():
        return service.cancel(machine, job_id, yes)


@cli.group()
@json_flag
def sw():
    """Manage reproducible builds and scientific validation records."""


@sw.command("list")
@json_flag
@click.pass_obj
def list_software(service):
    return {"software": service.store.all("record")}


@sw.command("show")
@click.argument("name")
@machine_option
@json_flag
@click.pass_obj
def show_software(service, name, machine):
    path, _, metadata = service.record(name, machine)
    return {
        "record": metadata,
        "notes": (path / "NOTES.md").read_text(),
        "builds": [
            b for b in service.store.all("build") if b["record_key"] == metadata["record_key"]
        ],
        "validations": [
            v for v in service.store.all("validation") if v["record_key"] == metadata["record_key"]
        ],
        "history": service.store.history(metadata["record_key"])[-25:],
    }


@sw.command("init")
@click.argument("name")
@machine_option
@click.option("--template", help="Packaged template name (see templates list) or directory.")
@json_flag
@click.pass_obj
def init_software(service, name, machine, template):
    with service.store.mutation():
        return service.init(name, machine, template)


@sw.command()
@click.argument("name")
@machine_option
@json_flag
@click.pass_obj
def check(service, name, machine):
    """Offline: report whether a rebuild or revalidation is needed and the next action."""
    return service.check(name, machine)


@sw.command()
@click.argument("name")
@machine_option
@click.option("--message", required=True)
@click.option(
    "--section",
    type=click.Choice(HEADINGS),
    default="Change log",
    show_default=True,
)
@json_flag
@click.pass_obj
def note(service, name, machine, message, section):
    """Append a dated, attributed entry to the record's NOTES.md and the ledger."""
    with service.store.mutation():
        return service.note(name, machine, message, section)


@sw.command()
@click.argument("name")
@machine_option
@click.option("--since", type=click.IntRange(min=0), default=0)
@json_flag
@click.pass_obj
def history(service, name, machine, since):
    """Ledger events for one record."""
    _, _, metadata = service.record(name, machine)
    return service.ledger(metadata["record_key"], since=since)


@sw.command()
@click.argument("name")
@machine_option
@click.option("--ref")
@wait_option
@json_flag
@click.pass_obj
def build(service, name, machine, ref, wait_timeout):
    with service.store.mutation():
        return service.build(name, machine, ref, wait_timeout)


@sw.command()
@click.argument("name")
@machine_option
@click.option("--build", "build_id")
@wait_option
@json_flag
@click.pass_obj
def validate(service, name, machine, build_id, wait_timeout):
    with service.store.mutation():
        return service.validate(name, machine, build_id, wait_timeout)


@sw.group()
@json_flag
def reference():
    """Explicit human acceptance of scientific reference evidence."""


@reference.command()
@click.argument("name")
@machine_option
@click.option("--validation", "validation_id", required=True)
@click.option("--yes", is_flag=True)
@json_flag
@click.pass_obj
def accept(service, name, machine, validation_id, yes):
    with service.store.mutation():
        return service.accept_reference(name, machine, validation_id, yes)


@sw.command()
@click.argument("name")
@machine_option
@click.option("--build", "build_id", required=True)
@click.option("--no-commit", is_flag=True, help="Explicitly skip Git for a non-Git demo workspace.")
@json_flag
@click.pass_obj
def promote(service, name, machine, build_id, no_commit):
    with service.store.mutation():
        return service.promote(name, machine, build_id, no_commit)


@cli.group()
@json_flag
def ledger():
    """Portable view of the authoritative SQLite event ledger."""


@ledger.command("export")
@click.option("--record", "record_key", help="NAME/MACHINE")
@click.option("--machine")
@click.option("--since", type=click.IntRange(min=0), default=0, help="Last exported sequence.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write JSONL here; otherwise return events inline.",
)
@json_flag
@click.pass_obj
def export(service, record_key, machine, since, output):
    if machine:
        service.settings.machine(machine)
    return service.ledger(record_key, machine, since, output)


@cli.command()
@click.option("--operation", "operation_id")
@wait_option
@json_flag
@click.pass_obj
def resume(service, operation_id, wait_timeout):
    with service.store.mutation():
        return service.resume(operation_id, wait_timeout)


def main(args=None):
    """Keep stdout a single JSON object for both CLI and application failures."""
    try:
        result = cli.main(args=args, standalone_mode=False)
        if result is not None and not isinstance(result, int):
            click.echo(json.dumps({"ok": True, "data": result}, allow_nan=False))
        return 0
    except TrackError as exc:
        click.echo(json.dumps(exc.result, allow_nan=False))
        raise SystemExit(exc.code) from None
    except click.ClickException as exc:
        click.echo(
            json.dumps({"ok": False, "error": "usage_error", "message": exc.format_message()})
        )
        raise SystemExit(2) from None
    except (ValidationError, ValueError) as exc:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_input",
                    "message": "Invalid input",
                    "reason": type(exc).__name__,
                }
            )
        )
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "interrupted",
                    "message": "Remote work may continue; use resume",
                }
            )
        )
        raise SystemExit(40) from None
    except Exception as exc:
        # Do not dump exception strings/tracebacks that might contain credentials or HTTP headers.
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "unexpected_error",
                    "message": "Command failed",
                    "reason": type(exc).__name__,
                }
            )
        )
        raise SystemExit(1) from None

"""Standalone detached worker, also copied to remote hosts. Standard library only."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def run(directory):
    directory = Path(directory).resolve()
    try:
        (directory / "claimed").mkdir()
    except FileExistsError:
        return  # An operation is executed at most once, even after a lost launch response.
    (directory / "pid").write_text(str(os.getpid()))
    request = json.loads((directory / "request.json").read_text())
    cancelled = False
    process = None

    def cancel(signum, frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    result = {"exit_status": 1, "cancelled": False}
    try:
        environment = {**os.environ, **request.get("environment", {})}
        with open(request["stdout"], "ab") as stdout, open(request["stderr"], "ab") as stderr:
            process = subprocess.Popen(
                request["argv"],
                cwd=request["cwd"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            started = time.monotonic()
            while True:
                if cancelled or (directory / "cancel.request").exists():
                    cancelled = True
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        result["exit_status"] = process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        result["exit_status"] = process.wait()
                    break
                try:
                    result["exit_status"] = process.wait(timeout=0.05)
                    break
                except subprocess.TimeoutExpired:
                    limit = request.get("timeout")
                    if limit and time.monotonic() - started >= limit:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        result.update(exit_status=124, timed_out=True)
                        break
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
        result["cancelled"] = cancelled
        temporary = directory / "result.tmp"
        with temporary.open("w") as stream:
            json.dump(result, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / "result.json")


if __name__ == "__main__":
    run(sys.argv[1])

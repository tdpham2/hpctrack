import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from hpctrack.errors import TrackError, auth_required
from hpctrack.util import atomic_write, digest, within


class LocalTransport:
    """Local file/worker operations, shared by the demo and explicit local PBS."""

    def __init__(self, machine, config, runner=None):
        self.machine = machine
        self.config = config
        self.simulated = config.backend == "fake"
        self.runner = runner or subprocess.run

    def check(self):
        return {"state": "simulated" if self.simulated else "local", "simulated": self.simulated}

    def safe(self, path):
        for root in (self.config.work_root, self.config.software_root):
            try:
                return within(root, path)
            except TrackError:
                pass
        raise TrackError("path_outside_root", "Local path is outside configured roots", 30)

    def write(self, path, data):
        atomic_write(self.safe(path), data)

    def read(self, path):
        path = self.safe(path)
        return path.read_bytes() if path.exists() else None

    def mkdir(self, path):
        self.safe(path).mkdir(parents=True, exist_ok=True)

    def run(self, argv, timeout=30, input=None):
        try:
            kwargs = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
            return self.runner(argv, capture_output=True, timeout=timeout, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise TrackError("remote_timeout", "Command exceeded its time limit") from exc
        except OSError as exc:
            raise TrackError("local_command_failed", "Could not start local command") from exc

    def tail(self, path, lines=40):
        if not path or not Path(path).is_absolute():
            return None
        result = self.run(["tail", "-n", str(lines), "--", path])
        return result.stdout.decode(errors="replace")[-16000:] if result.returncode == 0 else None

    def start(self, directory):
        directory = self.safe(directory)
        with open(directory / "launcher.log", "ab") as log:
            subprocess.Popen(
                [sys.executable, str(directory / "worker.py"), str(directory)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

    def cancel(self, directory):
        directory = self.safe(directory)
        if (directory / "result.json").exists():
            return
        # The owning worker signals its own child process. No PID lookup/reuse race.
        self.write(directory / "cancel.request", "cancel\n")


class SSHTransport:
    simulated = False

    def __init__(self, machine, config, runner=None):
        self.machine = machine
        self.config = config
        self.runner = runner or subprocess.run
        # A short path also avoids Unix-domain socket path length limits on macOS.
        self.socket_dir = Path(tempfile.gettempdir()) / f"hpctrack-{os.getuid()}"
        self.socket = self.socket_dir / digest([machine, config.ssh_alias])[:20]

    def options(self):
        return [
            "-S",
            str(self.socket),
            "-o",
            "BatchMode=yes",
            "-o",
            "ControlMaster=no",
            "-o",
            "ProxyCommand=false",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=2",
        ]

    def check(self):
        try:
            result = self.runner(
                [
                    "ssh",
                    "-S",
                    str(self.socket),
                    "-O",
                    "check",
                    "-o",
                    "BatchMode=yes",
                    self.config.ssh_alias,
                ],
                capture_output=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise auth_required(self.machine) from exc
        if result.returncode:
            raise auth_required(self.machine)
        return {"state": "connected", "simulated": False, "socket": str(self.socket)}

    def connect(self):
        if not sys.stdin.isatty():
            raise TrackError("terminal_required", "Run connect in a human-controlled terminal", 20)
        self.socket_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_dir.chmod(0o700)
        try:
            with open("/dev/tty", "r+b", buffering=0) as terminal:
                result = self.runner(
                    [
                        "ssh",
                        "-MNf",
                        "-S",
                        str(self.socket),
                        "-o",
                        "ControlMaster=yes",
                        "-o",
                        "ControlPersist=3600",
                        "-o",
                        "ConnectTimeout=10",
                        "-o",
                        "ServerAliveInterval=30",
                        "-o",
                        "ServerAliveCountMax=3",
                        self.config.ssh_alias,
                    ],
                    stdin=terminal,
                    stdout=terminal,
                    stderr=terminal,
                    timeout=120,
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise auth_required(self.machine) from exc
        if result.returncode:
            raise auth_required(self.machine)
        return self.check()

    def run(self, argv, timeout=30, input=None):
        self.check()
        command = ["ssh", "-T", *self.options(), self.config.ssh_alias, shlex.join(argv)]
        try:
            kwargs = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
            result = self.runner(command, capture_output=True, timeout=timeout, **kwargs)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TrackError(
                "transport_error", "SSH command failed or timed out", machine=self.machine
            ) from exc
        if result.returncode == 255:
            self.check()
            raise TrackError("transport_error", "SSH channel failed", machine=self.machine)
        return result

    def safe(self, path):
        path = PurePosixPath(path)
        if ".." in path.parts:
            raise TrackError("path_outside_root", "Parent traversal is refused", 30)
        roots = [PurePosixPath(self.config.work_root), PurePosixPath(self.config.software_root)]
        if not any(root in path.parents for root in roots):
            raise TrackError("path_outside_root", "Remote path must be under a configured root", 30)
        # Check the target's canonical path, not this workstation's filesystem.
        script = (
            "import os,sys,json; p=os.path.realpath(sys.argv[1]); "
            "roots=json.loads(sys.argv[2]); "
            "sys.exit(0 if any(p.startswith(os.path.realpath(r).rstrip('/')+'/') "
            "for r in roots) else 30)"
        )
        result = self.run(["python3", "-c", script, str(path), json.dumps([str(r) for r in roots])])
        if result.returncode:
            raise TrackError("path_outside_root", "Cannot verify canonical remote path", 30)
        return str(path)

    def mkdir(self, path):
        path = self.safe(path)
        result = self.run(["mkdir", "-p", "--", path])
        if result.returncode:
            raise TrackError("remote_write", "Could not create remote directory")

    def write(self, path, data):
        path = self.safe(path)
        if isinstance(data, str):
            data = data.encode()
        script = (
            "import os,sys,tempfile; from pathlib import Path; p=Path(sys.argv[1]); "
            "p.parent.mkdir(parents=True,exist_ok=True); "
            "fd,t=tempfile.mkstemp(dir=p.parent); f=os.fdopen(fd,'wb'); "
            "f.write(sys.stdin.buffer.read()); f.flush(); os.fsync(f.fileno()); "
            "f.close(); os.replace(t,p)"
        )
        result = self.run(["python3", "-c", script, path], input=data)
        if result.returncode:
            raise TrackError("remote_write", "Could not stage remote file")

    def read(self, path):
        path = self.safe(path)
        result = self.run(
            [
                "python3",
                "-c",
                "from pathlib import Path; import sys; "
                "p=Path(sys.argv[1]); sys.exit(44) if not p.exists() else "
                "sys.stdout.buffer.write(p.read_bytes()) and None",
                path,
            ]
        )
        if result.returncode == 44:
            return None
        if result.returncode:
            raise TrackError("remote_read", "Could not read remote file")
        return result.stdout

    def tail(self, path, lines=40):
        # Job output may legitimately live outside hpctrack's write roots.
        if not path or not path.startswith("/"):
            return None
        result = self.run(["tail", "-n", str(lines), "--", path])
        return result.stdout.decode(errors="replace")[-16000:] if result.returncode == 0 else None

    def start(self, directory):
        directory = self.safe(directory)
        command = (
            f"nohup python3 {shlex.quote(directory + '/worker.py')} {shlex.quote(directory)} "
            f"</dev/null >>{shlex.quote(directory + '/launcher.log')} 2>&1 &"
        )
        result = self.run(["bash", "-c", command])
        if result.returncode:
            raise TrackError("launch_unknown", "Detached launch could not be confirmed", 40)


def prepare_worker(transport, directory, argv, cwd, environment=None, timeout=None):
    transport.mkdir(directory)
    transport.write(f"{directory}/worker.py", Path(__file__).with_name("worker.py").read_bytes())
    request = {
        "argv": argv,
        "cwd": cwd,
        "environment": environment or {},
        "timeout": timeout,
        "stdout": f"{directory}/stdout.log",
        "stderr": f"{directory}/stderr.log",
    }
    transport.write(f"{directory}/request.json", json.dumps(request))


def worker_result(transport, directory):
    data = transport.read(f"{directory}/result.json")
    if data is None:
        return None
    try:
        return json.loads(data)
    except (ValueError, TypeError) as exc:
        raise TrackError("invalid_result", "Worker completion evidence is malformed") from exc

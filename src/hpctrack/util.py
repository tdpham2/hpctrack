import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from hpctrack.errors import TrackError


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(value).hexdigest()


def identifier(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", value):
        raise TrackError("invalid_name", "Names must contain letters, digits, dots, _ or -", 2)
    return value


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    fd, temporary = tempfile.mkstemp(prefix=".hpctrack-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, data):
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")


def within(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if path == root or root not in path.parents:
        raise TrackError(
            "path_outside_root",
            "Path must be beneath its configured root",
            30,
            path=str(path),
            root=str(root),
        )
    return path


def read_tree(root, exclude=()):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        names = [relative, *relative.parents]
        if any(fnmatch(name.as_posix(), pattern) for name in names for pattern in exclude):
            continue
        if path.is_symlink():
            raise TrackError("symlink_refused", "Record inputs cannot contain symlinks", 30)
        if path.is_file():
            if path.stat().st_size > 10 * 1024 * 1024:
                raise TrackError(
                    "input_too_large", "Individual staged files must be under 10 MiB", 30
                )
            result[relative.as_posix()] = path.read_bytes()
    return result


def tree_hash(files):
    return digest({name: digest(content) for name, content in sorted(files.items())})

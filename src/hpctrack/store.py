import contextlib
import fcntl
import json
import os
import sqlite3
import uuid
from pathlib import Path

from hpctrack.errors import TrackError
from hpctrack.util import now


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "hpctrack.db", timeout=5)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise TrackError("schema_version", "Database was created by a newer hpctrack", 2)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            kind TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(kind,key));
        CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            time TEXT NOT NULL, machine TEXT, kind TEXT NOT NULL, subject TEXT NOT NULL,
            actor TEXT NOT NULL, operation_id TEXT, payload TEXT NOT NULL);
        PRAGMA user_version=1;
        """)
        self.actor = os.environ.get("HPCTRACK_ACTOR", "human")
        if self.actor not in ("human", "agent"):
            raise TrackError("invalid_actor", "HPCTRACK_ACTOR must be human or agent", 2)

    @contextlib.contextmanager
    def mutation(self):
        with open(self.root / "controller.lock", "a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TrackError(
                    "controller_busy", "Another mutating command is active", 30
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def get(self, kind, key):
        row = self.db.execute(
            "SELECT payload FROM entities WHERE kind=? AND key=?", (kind, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM entities WHERE kind=? ORDER BY key", (kind,)
            )
        ]

    def put(self, kind, key, data, machine=None, operation_id=None, audit=True):
        if self.get(kind, key) == data:
            return
        with self.db:
            self.db.execute(
                "INSERT INTO entities VALUES (?,?,?) ON CONFLICT(kind,key) "
                "DO UPDATE SET payload=excluded.payload",
                (kind, key, json.dumps(data)),
            )
            if audit:
                self._event(kind, key, data, machine, operation_id)

    def _event(self, kind, subject, data, machine=None, operation_id=None):
        self.db.execute(
            "INSERT INTO events(id,time,machine,kind,subject,actor,operation_id,payload) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                now(),
                machine,
                kind,
                subject,
                self.actor,
                operation_id,
                json.dumps(data),
            ),
        )

    def new_operation(self, kind, data):
        operation = {"id": uuid.uuid4().hex, "kind": kind, "status": "preparing", "data": data}
        self.save_operation(operation)
        return operation

    def save_operation(self, operation):
        previous = self.db.execute(
            "SELECT payload FROM operations WHERE id=?", (operation["id"],)
        ).fetchone()
        if previous and json.loads(previous[0]) == operation:
            return
        with self.db:
            self.db.execute(
                "INSERT INTO operations VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET status=excluded.status,payload=excluded.payload",
                (operation["id"], operation["kind"], operation["status"], json.dumps(operation)),
            )
            self._event(
                "operation",
                operation["id"],
                {"status": operation["status"], "record_key": operation["data"].get("record_key")},
                operation["data"].get("machine"),
                operation["id"],
            )

    def operation(self, operation_id):
        row = self.db.execute(
            "SELECT payload FROM operations WHERE id=?", (operation_id,)
        ).fetchone()
        if not row:
            raise TrackError("unknown_operation", "Operation not found", 2)
        return json.loads(row[0])

    def pending(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM operations WHERE status NOT IN ('finished','failed') ORDER BY rowid"
            )
        ]

    def history(self, subject):
        rows = self.db.execute("SELECT * FROM events ORDER BY sequence")
        events = [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
        return [
            event
            for event in events
            if event["subject"] == subject or event["payload"].get("record_key") == subject
        ]

    def close(self):
        self.db.close()

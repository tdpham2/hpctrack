import contextlib
import fcntl
import getpass
import json
import os
import sqlite3
import uuid
from pathlib import Path

from hpctrack.errors import TrackError
from hpctrack.util import identifier, now

SCHEMA_VERSION = 2


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "hpctrack.db", timeout=5)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
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
            actor TEXT NOT NULL, operation_id TEXT, payload TEXT NOT NULL,
            actor_detail TEXT);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(events)")}
        if "actor_detail" not in columns:  # Version 1 databases keep their events unchanged.
            self.db.execute("ALTER TABLE events ADD COLUMN actor_detail TEXT")
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.actor = os.environ.get("HPCTRACK_ACTOR", "human")
        if self.actor not in ("human", "agent"):
            raise TrackError("invalid_actor", "HPCTRACK_ACTOR must be human or agent", 2)
        self.actor_detail = {"kind": self.actor, "user": None, "agent": None, "session": None}
        try:
            self.actor_detail["user"] = getpass.getuser()
        except (OSError, KeyError):
            pass
        for key in ("agent", "session"):
            value = os.environ.get(f"HPCTRACK_{key.upper()}")
            if value:
                # Short labels only; never accept free text that could carry credentials.
                try:
                    self.actor_detail[key] = identifier(value)
                except TrackError as exc:
                    raise TrackError(
                        "invalid_actor", f"HPCTRACK_{key.upper()} must be a short identifier", 2
                    ) from exc

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
            "INSERT INTO events(id,time,machine,kind,subject,actor,operation_id,payload,"
            "actor_detail) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                now(),
                machine,
                kind,
                subject,
                self.actor,
                operation_id,
                json.dumps(data),
                json.dumps(self.actor_detail),
            ),
        )

    def event(self, kind, subject, data, machine=None, operation_id=None):
        with self.db:
            self._event(kind, subject, data, machine, operation_id)

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

    def events(self, subject=None, machine=None, since=0):
        query, parameters = "SELECT * FROM events WHERE sequence>?", [since]
        if subject:
            query += " AND (subject=? OR json_extract(payload,'$.record_key')=?)"
            parameters += [subject, subject]
        if machine:
            query += " AND machine=?"
            parameters.append(machine)
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
                "actor_detail": json.loads(row["actor_detail"]) if row["actor_detail"] else None,
            }
            for row in self.db.execute(query + " ORDER BY sequence", parameters)
        ]

    def history(self, subject):
        return self.events(subject)

    def close(self):
        self.db.close()

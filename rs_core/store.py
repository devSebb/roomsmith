"""SQLite storage: projects, revisions (full scene snapshots), command receipts,
undo/redo stacks, photos, metadata.

The agent tools and the dashboard backend may run in different processes, so
this file is the only shared state. WAL mode lets a reader and a writer coexist;
every write runs inside ``BEGIN IMMEDIATE`` and checks the expected revision
inside the transaction, which is what makes commands atomic and conflict-safe.

Only the database *path* is needed. The Hermes-facing layer resolves the path
through ``plugins.plugin_storage``; tests pass a temporary file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from rs_core.model import SCHEMA_VERSION

HISTORY_CAP = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    head_revision INTEGER NOT NULL DEFAULT 0,
    agent_seen_revision INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS revisions (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at REAL NOT NULL,
    actor TEXT NOT NULL,
    summary TEXT NOT NULL,
    changed_ids TEXT NOT NULL,
    scene TEXT NOT NULL,
    PRIMARY KEY (project_id, revision)
);
CREATE TABLE IF NOT EXISTS commands (
    command_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    project_id TEXT PRIMARY KEY,
    undo_stack TEXT NOT NULL,
    redo_stack TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    file TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    created_at REAL NOT NULL
);
"""


class RevisionConflict(Exception):
    def __init__(self, expected: int, current: int):
        super().__init__(f"expected revision {expected}, current is {current}")
        self.expected = expected
        self.current = current


class NotFound(Exception):
    pass


class Store:
    """One connection per Store; safe to share across threads via the lock."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._tx_depth = 0
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=10000")
        with self._lock:
            # executescript manages its own transaction; keep it out of _tx()
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """A write transaction (BEGIN IMMEDIATE). Reentrant: nested uses join the
        outer transaction, so a caller can hold the database write lock across a
        read-modify-write (see ``write_transaction``)."""
        with self._lock:
            if self._tx_depth > 0:
                self._tx_depth += 1
                try:
                    yield self._conn
                finally:
                    self._tx_depth -= 1
                return
            self._conn.execute("BEGIN IMMEDIATE")
            self._tx_depth = 1
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")
            finally:
                self._tx_depth = 0

    @contextmanager
    def write_transaction(self) -> Iterator[None]:
        """Hold the database write lock while reading and then committing a scene.
        Other processes' writers wait (busy_timeout) instead of racing."""
        with self._tx():
            yield

    # ------------------------------------------------------------ meta

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------ projects

    def create_project(self, project_id: str, name: str, scene: dict, actor: str = "system", summary: str = "Created room") -> dict:
        now = time.time()
        with self._tx() as c:
            c.execute(
                "INSERT INTO projects(id, name, created_at, updated_at, head_revision, agent_seen_revision) VALUES (?, ?, ?, ?, 1, 0)",
                (project_id, name, now, now),
            )
            c.execute(
                "INSERT INTO revisions(project_id, revision, created_at, actor, summary, changed_ids, scene) VALUES (?, 1, ?, ?, ?, ?, ?)",
                (project_id, now, actor, summary, "[]", json.dumps(scene, separators=(",", ":"))),
            )
            c.execute("INSERT INTO history(project_id, undo_stack, redo_stack) VALUES (?, '[]', '[]')", (project_id,))
            c.execute("INSERT INTO meta(key, value) VALUES ('active_project', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (project_id,))
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict:
        with self._lock:
            row = self._conn.execute("SELECT * FROM projects WHERE id = ? AND deleted = 0", (project_id,)).fetchone()
        if row is None:
            raise NotFound(f"No project {project_id!r}")
        return dict(row)

    def list_projects(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM projects WHERE deleted = 0 ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def active_project_id(self) -> str | None:
        pid = self.get_meta("active_project")
        if pid is None:
            return None
        try:
            self.get_project(pid)
        except NotFound:
            return None
        return pid

    def set_active(self, project_id: str) -> None:
        self.get_project(project_id)
        self.set_meta("active_project", project_id)

    def rename_project(self, project_id: str, name: str) -> None:
        with self._tx() as c:
            if c.execute("UPDATE projects SET name = ?, updated_at = ? WHERE id = ? AND deleted = 0", (name, time.time(), project_id)).rowcount == 0:
                raise NotFound(f"No project {project_id!r}")

    def delete_project(self, project_id: str) -> None:
        with self._tx() as c:
            if c.execute("UPDATE projects SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0", (time.time(), project_id)).rowcount == 0:
                raise NotFound(f"No project {project_id!r}")
            row = c.execute("SELECT value FROM meta WHERE key = 'active_project'").fetchone()
            if row and row["value"] == project_id:
                nxt = c.execute("SELECT id FROM projects WHERE deleted = 0 ORDER BY updated_at DESC LIMIT 1").fetchone()
                if nxt:
                    c.execute("UPDATE meta SET value = ? WHERE key = 'active_project'", (nxt["id"],))
                else:
                    c.execute("DELETE FROM meta WHERE key = 'active_project'")

    # ------------------------------------------------------------ revisions

    def head(self, project_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT r.revision, r.created_at, r.actor, r.summary, r.changed_ids, p.name, p.agent_seen_revision "
                "FROM projects p JOIN revisions r ON r.project_id = p.id AND r.revision = p.head_revision "
                "WHERE p.id = ? AND p.deleted = 0",
                (project_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"No project {project_id!r}")
        return {
            "project_id": project_id,
            "name": row["name"],
            "revision": row["revision"],
            "updated_at": row["created_at"],
            "actor": row["actor"],
            "summary": row["summary"],
            "changed_ids": json.loads(row["changed_ids"]),
            "agent_seen_revision": row["agent_seen_revision"],
        }

    def get_scene(self, project_id: str, revision: int | None = None) -> tuple[dict, int]:
        with self._lock:
            if revision is None:
                row = self._conn.execute(
                    "SELECT r.scene, r.revision FROM projects p JOIN revisions r ON r.project_id = p.id AND r.revision = p.head_revision WHERE p.id = ? AND p.deleted = 0",
                    (project_id,),
                ).fetchone()
            else:
                row = self._conn.execute("SELECT scene, revision FROM revisions WHERE project_id = ? AND revision = ?", (project_id, int(revision))).fetchone()
        if row is None:
            raise NotFound(f"No scene for project {project_id!r} at revision {revision}")
        return json.loads(row["scene"]), int(row["revision"])

    def list_revisions(self, project_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT revision, created_at, actor, summary, changed_ids FROM revisions WHERE project_id = ? ORDER BY revision DESC LIMIT ?",
                (project_id, int(limit)),
            ).fetchall()
        return [
            {"revision": r["revision"], "created_at": r["created_at"], "actor": r["actor"], "summary": r["summary"], "changed_ids": json.loads(r["changed_ids"])}
            for r in rows
        ]

    def get_command_result(self, command_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT result FROM commands WHERE command_id = ?", (command_id,)).fetchone()
        return json.loads(row["result"]) if row else None

    def commit_revision(
        self,
        project_id: str,
        expected_revision: int | None,
        scene: dict,
        actor: str,
        summary: str,
        changed_ids: list[str],
        command_id: str | None = None,
        result: dict | None = None,
        history_mode: str = "edit",
        restore_revision: int | None = None,
    ) -> int:
        """Append a revision. `history_mode` is 'edit' (push undo, clear redo),
        'undo' or 'redo' (stack bookkeeping done here), or 'none'."""
        now = time.time()
        with self._tx() as c:
            row = c.execute("SELECT head_revision FROM projects WHERE id = ? AND deleted = 0", (project_id,)).fetchone()
            if row is None:
                raise NotFound(f"No project {project_id!r}")
            current = int(row["head_revision"])
            if expected_revision is not None and int(expected_revision) != current:
                raise RevisionConflict(int(expected_revision), current)
            if command_id is not None:
                existing = c.execute("SELECT result FROM commands WHERE command_id = ?", (command_id,)).fetchone()
                if existing is not None:
                    return int(json.loads(existing["result"]).get("revision", current))
            new_rev = current + 1
            c.execute(
                "INSERT INTO revisions(project_id, revision, created_at, actor, summary, changed_ids, scene) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, new_rev, now, actor, summary, json.dumps(changed_ids), json.dumps(scene, separators=(",", ":"))),
            )
            c.execute("UPDATE projects SET head_revision = ?, updated_at = ? WHERE id = ?", (new_rev, now, project_id))
            h = c.execute("SELECT undo_stack, redo_stack FROM history WHERE project_id = ?", (project_id,)).fetchone()
            undo = json.loads(h["undo_stack"]) if h else []
            redo = json.loads(h["redo_stack"]) if h else []
            if history_mode == "edit":
                undo.append(current)
                redo = []
            elif history_mode == "undo":
                # caller popped `restore_revision` from undo; current head goes to redo
                undo = [r for r in undo if r != restore_revision] if restore_revision is not None else undo
                redo.append(current)
            elif history_mode == "redo":
                redo = [r for r in redo if r != restore_revision] if restore_revision is not None else redo
                undo.append(current)
            undo = undo[-HISTORY_CAP:]
            redo = redo[-HISTORY_CAP:]
            c.execute(
                "INSERT INTO history(project_id, undo_stack, redo_stack) VALUES (?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET undo_stack = excluded.undo_stack, redo_stack = excluded.redo_stack",
                (project_id, json.dumps(undo), json.dumps(redo)),
            )
            if command_id is not None:
                payload = dict(result or {})
                payload["revision"] = new_rev
                c.execute("INSERT INTO commands(command_id, project_id, created_at, result) VALUES (?, ?, ?, ?)", (command_id, project_id, now, json.dumps(payload)))
            # prune: keep the newest HISTORY_CAP revisions plus anything a stack references
            keep = set(undo) | set(redo) | {new_rev}
            floor = new_rev - HISTORY_CAP
            if floor > 1:
                referenced = ",".join(str(r) for r in keep) or "0"
                c.execute(f"DELETE FROM revisions WHERE project_id = ? AND revision < ? AND revision NOT IN ({referenced})", (project_id, floor))
        return new_rev

    def history_stacks(self, project_id: str) -> tuple[list[int], list[int]]:
        with self._lock:
            h = self._conn.execute("SELECT undo_stack, redo_stack FROM history WHERE project_id = ?", (project_id,)).fetchone()
        if h is None:
            return [], []
        return json.loads(h["undo_stack"]), json.loads(h["redo_stack"])

    def mark_agent_seen(self, project_id: str, revision: int) -> None:
        with self._tx() as c:
            c.execute("UPDATE projects SET agent_seen_revision = MAX(agent_seen_revision, ?) WHERE id = ?", (int(revision), project_id))

    def revisions_between(self, project_id: str, after: int, upto: int | None = None) -> list[dict]:
        with self._lock:
            if upto is None:
                rows = self._conn.execute(
                    "SELECT revision, created_at, actor, summary, changed_ids FROM revisions WHERE project_id = ? AND revision > ? ORDER BY revision",
                    (project_id, int(after)),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT revision, created_at, actor, summary, changed_ids FROM revisions WHERE project_id = ? AND revision > ? AND revision <= ? ORDER BY revision",
                    (project_id, int(after), int(upto)),
                ).fetchall()
        return [{"revision": r["revision"], "created_at": r["created_at"], "actor": r["actor"], "summary": r["summary"], "changed_ids": json.loads(r["changed_ids"])} for r in rows]

    # ------------------------------------------------------------ photos

    def add_photo(self, photo_id: str, file: str, sha256: str, width: int | None, height: int | None, project_id: str | None = None) -> dict:
        now = time.time()
        with self._tx() as c:
            c.execute(
                "INSERT INTO photos(id, project_id, file, sha256, width, height, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET project_id = excluded.project_id",
                (photo_id, project_id, file, sha256, width, height, now),
            )
        return self.get_photo(photo_id)

    def get_photo(self, photo_id: str) -> dict:
        with self._lock:
            row = self._conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if row is None:
            raise NotFound(f"No photo {photo_id!r}")
        return dict(row)

    def photos_for(self, project_id: str | None) -> list[dict]:
        with self._lock:
            if project_id is None:
                rows = self._conn.execute("SELECT * FROM photos WHERE project_id IS NULL ORDER BY created_at DESC").fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM photos WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def attach_photo(self, photo_id: str, project_id: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE photos SET project_id = ? WHERE id = ?", (project_id, photo_id))

    # ------------------------------------------------------------ diagnostics

    def stats(self) -> dict[str, Any]:
        with self._lock:
            projects = self._conn.execute("SELECT COUNT(*) AS n FROM projects WHERE deleted = 0").fetchone()["n"]
            revisions = self._conn.execute("SELECT COUNT(*) AS n FROM revisions").fetchone()["n"]
        return {"path": str(self.path), "projects": projects, "revisions": revisions, "schema_version": self.get_meta("schema_version")}

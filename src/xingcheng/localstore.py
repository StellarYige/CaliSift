"""Transactional local state. The UI never writes an authoritative calendar."""

from __future__ import annotations

import base64
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

from .calendar import effective, empty_calendar, identity, now, validate_calendar


class LocalError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + "." + identity() + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != data:
            raise OSError("文件回读校验失败")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LocalStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.evidence_dir = self.root / "evidence"
        self.backup_dir = self.root / "backups"
        self.jobs_dir = self.root / "jobs"
        for folder in (self.evidence_dir, self.backup_dir, self.jobs_dir):
            folder.mkdir(exist_ok=True)
        self.path = self.root / "calendar.sqlite3"
        self.lock = threading.RLock()
        self.session = identity()
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise LocalError(
                    "SCHEMA_TOO_NEW",
                    "数据来自更新版本，请升级 CaliSift 后打开；原数据已保留",
                )
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise LocalError(
                    "STORAGE_FAILED", "本机数据库损坏，请从备份恢复；原文件已保留"
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
                    calendar TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS event_index (
                    workspace TEXT NOT NULL REFERENCES workspaces(id), id TEXT NOT NULL,
                    day TEXT, ending TEXT, title TEXT, location TEXT, category TEXT,
                    hidden INTEGER, cancelled INTEGER, archived INTEGER, status TEXT,
                    PRIMARY KEY(workspace,id));
                CREATE INDEX IF NOT EXISTS events_by_date ON event_index(workspace,day);
                CREATE TABLE IF NOT EXISTS documents (
                    kind TEXT NOT NULL, id TEXT NOT NULL, workspace TEXT NOT NULL,
                    body TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE INDEX IF NOT EXISTS documents_by_workspace ON documents(kind,workspace);
                CREATE TABLE IF NOT EXISTS previews (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, version INTEGER NOT NULL,
                    session TEXT NOT NULL, body TEXT NOT NULL, receipt TEXT);
                PRAGMA user_version=1;
            """
            )
            db.execute("DELETE FROM previews WHERE receipt IS NULL")

    @contextmanager
    def connection(self, writing=False):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA busy_timeout=10000")
                db.execute("PRAGMA synchronous=FULL")
                if writing:
                    db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def create_workspace(self, name, calendar=None):
        name = name.strip() if isinstance(name, str) else ""
        calendar = deepcopy(calendar) if calendar else empty_calendar(name)
        validate_calendar(calendar)
        if name != calendar["personName"]:
            raise LocalError("INVALID_INPUT", "工作区姓名与日历不一致")
        wid = identity()
        with self.connection(True) as db:
            db.execute(
                "INSERT INTO workspaces VALUES(?,?,?,?,?)",
                (wid, name, calendar["version"], encode(calendar), now()),
            )
            self._index(db, wid, calendar)
        return self.workspace(wid)

    def workspaces(self):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,name,version,updated_at FROM workspaces ORDER BY updated_at DESC"
                )
            ]

    def workspace(self, wid):
        with self.connection() as db:
            row = db.execute("SELECT * FROM workspaces WHERE id=?", (wid,)).fetchone()
            if row is None:
                raise LocalError("NOT_FOUND", "工作区不存在，请重新选择")
            result = dict(row)
            result["calendar"] = json.loads(row["calendar"])
            return result

    def _index(self, db, wid, calendar):
        db.execute("DELETE FROM event_index WHERE workspace=?", (wid,))
        values = []
        for record in calendar["events"]:
            event = effective(record)
            values.append(
                (
                    wid,
                    record["id"],
                    event["date"],
                    event["end_date"] or event["date"],
                    event["title"],
                    event["location"],
                    event["category"],
                    record["hidden"],
                    record.get("cancelled", False),
                    record.get("archived", False),
                    event["status"],
                )
            )
        db.executemany("INSERT INTO event_index VALUES(?,?,?,?,?,?,?,?,?,?,?)", values)

    def document(self, kind, item_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT body FROM documents WHERE kind=? AND id=?", (kind, item_id)
            ).fetchone()
            if row is None:
                raise LocalError("NOT_FOUND", "记录不存在，请刷新后重试")
            return json.loads(row[0])

    def documents(self, kind, wid=None):
        with self.connection() as db:
            rows = db.execute(
                "SELECT body FROM documents WHERE kind=?"
                + (" AND workspace=?" if wid else "")
                + " ORDER BY updated_at DESC",
                (kind, wid) if wid else (kind,),
            )
            return [json.loads(row[0]) for row in rows]

    @staticmethod
    def _put(db, kind, item_id, wid, value):
        db.execute(
            "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)",
            (kind, item_id, wid, encode(value), now()),
        )

    def put(self, kind, item_id, wid, value):
        with self.connection(True) as db:
            self._put(db, kind, item_id, wid, value)

    def delete(self, kind, item_id):
        with self.connection(True) as db:
            db.execute("DELETE FROM documents WHERE kind=? AND id=?", (kind, item_id))

    def preview(self, wid, result, dependency=None):
        pid = identity()
        body = dict(result=result, dependency=dependency)
        with self.connection(True) as db:
            db.execute(
                "INSERT INTO previews VALUES(?,?,?,?,?,NULL)",
                (pid, wid, result["base_version"], self.session, encode(body)),
            )
            db.execute(
                "DELETE FROM previews WHERE receipt IS NULL AND rowid NOT IN (SELECT rowid FROM previews WHERE receipt IS NULL ORDER BY rowid DESC LIMIT 20)"
            )
        return dict(
            preview_id=pid,
            base_version=result["base_version"],
            summary=result["summary"],
        )

    def commit(self, pid, expected_version):
        with self.connection(True) as db:
            row = db.execute("SELECT * FROM previews WHERE id=?", (pid,)).fetchone()
            if not row:
                raise LocalError("VERSION_CONFLICT", "预览已失效，请重新预览")
            if row["receipt"]:
                return json.loads(row["receipt"])
            if row["session"] != self.session:
                raise LocalError("VERSION_CONFLICT", "程序已重新启动，请重新预览")
            current = db.execute(
                "SELECT version FROM workspaces WHERE id=?", (row["workspace"],)
            ).fetchone()
            if (
                current is None
                or current[0] != expected_version
                or expected_version != row["version"]
            ):
                raise LocalError("VERSION_CONFLICT", "日历已变化，请重新预览")
            body = json.loads(row["body"])
            dependency = body.get("dependency")
            if dependency:
                document = db.execute(
                    "SELECT body FROM documents WHERE kind=? AND id=?",
                    (dependency["kind"], dependency["id"]),
                ).fetchone()
                if (
                    document is None
                    or digest(json.loads(document[0])) != dependency["digest"]
                ):
                    raise LocalError("VERSION_CONFLICT", "导入草稿已变化，请重新预览")
            result = body["result"]
            if result["summary"].get("unresolved"):
                raise LocalError(
                    "CONFIRMATION_REQUIRED", "请先处理变更对应关系和个人修正冲突"
                )
            calendar = result["calendar"]
            validate_calendar(calendar)
            if calendar["version"] != expected_version + 1:
                raise LocalError("VERSION_CONFLICT", "候选版本无效，请重新预览")
            self.verify_evidence(calendar)
            db.execute(
                "UPDATE workspaces SET name=?, version=?, calendar=?, updated_at=? WHERE id=?",
                (
                    calendar["personName"],
                    calendar["version"],
                    encode(calendar),
                    now(),
                    row["workspace"],
                ),
            )
            self._index(db, row["workspace"], calendar)
            receipt = dict(
                workspace_id=row["workspace"],
                version=calendar["version"],
                preview_id=pid,
                job_id=(
                    dependency["id"]
                    if dependency and dependency["kind"] == "job"
                    else None
                ),
            )
            if receipt["job_id"]:
                job = json.loads(document[0])
                job.update(status="committed", committed_version=calendar["version"])
                self._put(db, "job", job["id"], row["workspace"], job)
            db.execute(
                "UPDATE previews SET receipt=?, body=? WHERE id=?",
                (encode(receipt), "{}", pid),
            )
        return receipt

    def evidence(self, evidence_id):
        if not isinstance(evidence_id, str) or not re.fullmatch(
            "[a-f0-9]{20}", evidence_id
        ):
            raise LocalError("INVALID_INPUT", "证据编号无效")
        path = self.evidence_dir / (evidence_id + ".jpg")
        if not path.is_file():
            raise LocalError("EVIDENCE_MISSING", "局部证据缺失，请从完整备份恢复")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest()[:20] != evidence_id:
            raise LocalError("EVIDENCE_MISSING", "局部证据损坏，请从完整备份恢复")
        return data

    def externalize(self, value):
        value = deepcopy(value)

        def walk(item):
            if isinstance(item, list):
                for child in item:
                    walk(child)
            elif isinstance(item, dict):
                for key, child in item.items():
                    if key == "crops" and isinstance(child, dict):
                        for eid, content in child.items():
                            if not isinstance(content, str):
                                raise LocalError("INVALID_INPUT", "图片证据格式无效")
                            if content.startswith("evidence:"):
                                self.evidence(eid)
                            else:
                                data = base64.b64decode(content, validate=True)
                                if hashlib.sha256(data).hexdigest()[:20] != eid:
                                    raise LocalError(
                                        "INVALID_INPUT", "图片证据校验失败"
                                    )
                                target = self.evidence_dir / (eid + ".jpg")
                                if target.exists() and target.read_bytes() != data:
                                    raise LocalError(
                                        "EVIDENCE_MISSING", "证据编号冲突，原文件已保留"
                                    )
                                if not target.exists():
                                    atomic_write(target, data)
                            child[eid] = "evidence:" + eid
                    else:
                        walk(child)

        walk(value)
        self.verify_evidence(value)
        return value

    @staticmethod
    def evidence_ids(value):
        ids = set()

        def walk(item):
            if isinstance(item, list):
                for child in item:
                    walk(child)
            elif isinstance(item, dict):
                for key, child in item.items():
                    if (
                        key == "image"
                        and isinstance(child, str)
                        and re.fullmatch("[a-f0-9]{20}", child)
                    ):
                        ids.add(child)
                    elif key == "crops" and isinstance(child, dict):
                        ids.update(child)
                    else:
                        walk(child)

        walk(value)
        return ids

    def verify_evidence(self, value):
        for eid in self.evidence_ids(value):
            self.evidence(eid)

    def safety_backup(self, reason="daily"):
        day = date.today().isoformat()
        if reason == "daily" and any(self.backup_dir.glob(day + "-daily-*.sqlite3")):
            return None
        target = self.backup_dir / (day + "-" + reason + "-" + identity() + ".sqlite3")
        temporary = target.with_suffix(".tmp")
        try:
            with self.connection() as db:
                with closing(sqlite3.connect(temporary)) as backup:
                    db.backup(backup)
                    if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise OSError("备份校验失败")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        for old in sorted(
            self.backup_dir.glob("*.sqlite3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[7:]:
            old.unlink()
        return target

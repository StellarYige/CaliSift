import json
import sqlite3
from copy import deepcopy
import pytest
from xingcheng.application import Application
from xingcheng.backup import pack_backup, unpack_backup
from xingcheng.localstore import LocalStore, LocalError
from tests.test_desktop_store import local, draft, change, imported


def test_preferences_do_not_invalidate_calendar_preview_and_survive_backup(
    local, tmp_path
):
    app, wid = local
    preview = change(
        app, wid, dict(type="append", source_name="工作"), draft(app, wid), False
    )
    before = app.workspace(wid)["version"]
    snapshot = app.get_preferences(wid)
    values = deepcopy(snapshot["values"])
    values.update(theme="dark", font_size=20, week_start=0)
    values["categories"].append(dict(name="健身", color="#1256ab", active=True))
    app.save_preferences(wid, snapshot["revision"], values)
    assert app.workspace(wid)["version"] == before
    with pytest.raises(LocalError, match="偏好已变化"):
        app.save_preferences(wid, snapshot["revision"], values)
    app.commit_change(preview["preview_id"], before)
    payload = unpack_backup(pack_backup(app.store, wid))
    assert payload["version"] == 2 and payload["preferences"] == values
    with_other = Application(tmp_path / "other-device")
    try:
        restore = with_other.prepare_restore(pack_backup(app.store, wid))
        restored = with_other.restore_backup(restore["token"])
        assert restored["preferences"]["values"] == values
        assert (
            with_other.events(restored["id"])["items"][0]["id"]
            == app.events(wid)["items"][0]["id"]
        )
        assert with_other.device_preferences()["last_workspace"] == ""
    finally:
        with_other.close()


def test_v1_migration_is_atomic_and_keeps_a_recovery_point(tmp_path, monkeypatch):
    root = tmp_path / "old"
    store = LocalStore(root)
    wid = store.create_workspace("星辰奕歌")["id"]
    with store.connection(True) as db:
        calendar = store.workspace(wid)["calendar"]
        calendar["settings"] = dict(large_text=True, colors={"工作": "#123456"})
        db.execute(
            "UPDATE workspaces SET calendar=? WHERE id=?", (json.dumps(calendar), wid)
        )
        db.execute("DELETE FROM documents WHERE kind='preferences'")
        db.execute("PRAGMA user_version=1")
    original = LocalStore._put

    def fail(*args):
        raise OSError("interrupted")

    monkeypatch.setattr(LocalStore, "_put", staticmethod(fail))
    with pytest.raises(OSError, match="interrupted"):
        LocalStore(root)
    with sqlite3.connect(root / "calendar.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM documents WHERE kind='preferences'"
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(LocalStore, "_put", staticmethod(original))
    migrated = LocalStore(root)
    prefs = migrated.preferences(wid)["values"]
    assert prefs["theme"] == "light" and prefs["font_size"] == 17
    assert prefs["categories"][0]["color"] == "#123456"
    assert list((root / "backups").glob("*-upgrade-v2-*.sqlite3"))


def test_bulk_courses_validate_before_creating_draft_and_keep_semester(local):
    app, wid = local
    semester = dict(
        monday="2026-12-28", weeks=3, periods=[dict(start="08:00", end="08:45")]
    )
    first = dict(title="课程甲", weekday=1, periods=[1], parity="odd")
    second = dict(title="课程乙", weekday=2, periods=[1], parity="even")
    with pytest.raises(ValueError):
        app.course_draft(
            wid, semester=semester, courses=[first, {**second, "periods": [2]}]
        )
    assert app.list_jobs(wid) == []
    job = app.course_draft(wid, semester=semester, courses=[first, second])
    assert len(job["report"]["events"]) == 3
    assert app.last_semester(wid) == semester
    t = app.save_template("学期", {"semester": semester})
    app.save_template("更新名称", t["rules"], template_id=t["id"])
    assert len(app.templates()) == 1
    app.delete_template(t["id"])
    assert app.templates() == [] and app.last_semester(wid) == semester

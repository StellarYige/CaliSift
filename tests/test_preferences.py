from copy import deepcopy
import pytest
from xingcheng.application import Application
from xingcheng.backup import pack_backup, unpack_backup
from xingcheng.localstore import LocalError
from tests.test_browser_application import local, draft, change, imported


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
    with_other = Application()
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
        pass


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


def test_replacing_workspace_invalidates_a_preferences_form_opened_before_restore(
    local,
):
    app, wid = local
    old = app.get_preferences(wid)
    prepared = app.prepare_restore(pack_backup(app.store, wid))
    app.restore_backup(prepared["token"], wid, app.workspace(wid)["version"])
    assert app.get_preferences(wid)["revision"] > old["revision"]
    with pytest.raises(LocalError, match="偏好已变化"):
        app.save_preferences(wid, old["revision"], old["values"])

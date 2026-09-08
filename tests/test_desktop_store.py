"""Failure and migration contracts for the new authoritative local calendar."""

from copy import deepcopy
import base64
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from xingcheng.application import Application
from xingcheng.backup import fnv_js, pack_backup, unpack_backup
from xingcheng.calendar import effective, identity, now, empty_calendar
from xingcheng.localstore import LocalError, LocalStore, atomic_write, encode
from tests.test_calendar import report, NAME


@pytest.fixture
def local(tmp_path):
    app = Application(tmp_path / "data")
    wid = app.create_workspace(NAME)["id"]
    yield app, wid
    app.close()


def draft(app, wid, value=None):
    job = dict(
        id=identity(),
        workspace_id=wid,
        status="review",
        created_at=now(),
        files=[],
        generation=0,
        year=2026,
        source_id="",
        rules={},
        report=report() if value is None else value,
    )
    app.store.put("job", job["id"], wid, job)
    return job["id"]


def change(app, wid, operation, job=None, commit=True):
    value = app.preview_change(wid, app.workspace(wid)["version"], operation, job)
    if commit:
        return app.commit_change(value["preview_id"], value["base_version"])
    return value


def imported(app, wid):
    change(app, wid, dict(type="append", source_name="工作"), draft(app, wid))
    return app.store.workspace(wid)["calendar"]


def test_snapshot_commit_idempotency_and_stale_drafts(local):
    app, wid = local
    jid = draft(app, wid)
    first = change(app, wid, dict(type="append", source_name="工作"), jid, False)
    assert app.events(wid)["total"] == 0
    app.edit_draft(jid, [dict(index=0, values={"location": "新地点"})])
    with pytest.raises(LocalError, match="草稿已变化"):
        app.commit_change(first["preview_id"], first["base_version"])
    second = change(app, wid, dict(type="append", source_name="工作"), jid, False)
    receipt = app.commit_change(second["preview_id"], second["base_version"])
    assert app.commit_change(second["preview_id"], second["base_version"]) == receipt
    assert app.events(wid)["total"] == 1
    assert app.events(wid)["items"][0]["location"] == "新地点"
    assert app.get_job(jid)["status"] == "committed"
    with pytest.raises(LocalError):
        app.edit_draft(jid, [dict(index=0, values={})])


def test_recovery_points_release_handles_and_publish_only_complete_files(
    local, monkeypatch
):
    from xingcheng import localstore

    app, wid = local
    target = app.store.safety_backup()
    moved = target.with_suffix(".checked")
    target.replace(moved)  # Windows refuses this if the SQLite handle is still open.
    moved.unlink()

    def interrupted(*args):
        raise OSError("interrupted snapshot switch")

    monkeypatch.setattr(localstore.os, "replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        app.store.safety_backup()
    assert list(app.store.backup_dir.iterdir()) == []
    assert app.workspace(wid)["version"] == 0


def test_two_previews_one_winner_and_restart_invalidation(local, tmp_path):
    app, wid = local
    a = change(
        app,
        wid,
        dict(type="manual", values=dict(date="2026-09-01", title="一")),
        commit=False,
    )
    b = change(
        app,
        wid,
        dict(type="manual", values=dict(date="2026-09-02", title="二")),
        commit=False,
    )
    app.commit_change(a["preview_id"], 0)
    with pytest.raises(LocalError):
        app.commit_change(b["preview_id"], 0)
    c = change(app, wid, dict(type="settings", settings={}), commit=False)
    with pytest.raises(LocalError, match="已被"):
        Application(tmp_path / "data")
    app.close()
    reopened = Application(tmp_path / "data")
    try:
        assert reopened.events(wid)["total"] == 1
        with pytest.raises(LocalError):
            reopened.commit_change(c["preview_id"], c["base_version"])
    finally:
        reopened.close()


def test_failed_commit_rolls_back_calendar_index_and_job(local, monkeypatch):
    app, wid = local
    original = app.store.workspace(wid)
    jid = draft(app, wid)
    candidate = change(app, wid, dict(type="append"), jid, False)
    with monkeypatch.context() as patch:
        patch.setattr(
            app.store, "_index", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
        )
        with pytest.raises(OSError):
            app.commit_change(candidate["preview_id"], 0)
    assert app.store.workspace(wid) == original
    assert app.get_job(jid)["status"] == "review"
    app.commit_change(candidate["preview_id"], 0)
    assert app.events(wid)["total"] == 1


def test_atomic_file_failure_retains_previous_and_removes_temporary(
    tmp_path, monkeypatch
):
    path = tmp_path / "backup.zip"
    path.write_bytes(b"old")
    monkeypatch.setattr(
        "xingcheng.localstore.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        atomic_write(path, b"new")
    assert path.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [path]


def test_update_corrections_other_source_and_undo(local):
    app, wid = local
    c = imported(app, wid)
    eid = c["events"][0]["id"]
    sid = c["sources"][0]["id"]
    change(app, wid, dict(type="append", source_name="培训"), draft(app, wid))
    change(app, wid, dict(type="edit", event_id=eid, values={"location": "个人地点"}))
    incoming = report(timing="14:00-16:00")
    incoming["events"][0]["location"] = "新版地点"
    jid = draft(app, wid, incoming)
    op = dict(
        type="update",
        source_id=sid,
        coverage=["2026-09-01", "2026-09-30"],
        mappings={"0": eid},
    )
    blocked = change(app, wid, op, jid, False)
    assert blocked["old_candidates"][0]["id"] == eid
    with pytest.raises(LocalError, match="冲突"):
        app.commit_change(blocked["preview_id"], blocked["base_version"])
    op["correction_choices"] = {eid: "keep"}
    change(app, wid, op, jid)
    assert {e["start"] for e in app.events(wid)["items"]} == {"08:00", "14:00"}
    assert all(e["location"] == "个人地点" for e in app.events(wid)["items"])
    change(app, wid, dict(type="undo"))
    assert app.events(wid)["total"] == 1
    assert app.events(wid)["items"][0]["id"] == eid


def test_archive_overnight_filter_hidden_and_reimport(local):
    app, wid = local
    change(
        app,
        wid,
        dict(
            type="manual",
            values=dict(
                date="2026-09-07",
                title="夜班",
                category="工作",
                start="20:00",
                end="08:00",
                end_date="2026-09-08",
            ),
        ),
    )
    change(
        app,
        wid,
        dict(
            type="manual",
            values=dict(date="2026-09-07", title="休息", category="休息", all_day=True),
        ),
    )
    night = next(e for e in app.events(wid)["items"] if e["title"] == "夜班")
    assert app.events(wid, date_from="2026-09-08", date_to="2026-09-08")["total"] == 1
    change(app, wid, dict(type="settings", settings={"hide_rest": True}))
    assert app.events(wid)["total"] == 1
    change(app, wid, dict(type="archive", before="2026-09-08"))
    assert app.events(wid, view="archived")["total"] == 1
    change(app, wid, dict(type="archive", before="2026-09-09"))
    assert app.events(wid)["total"] == 0
    change(app, wid, dict(type="archive", event_ids=[night["id"]], restore=True))
    assert app.events(wid, query="夜", category="工作")["items"][0]["id"] == night["id"]
    change(app, wid, dict(type="hide", event_id=night["id"]))
    assert app.events(wid, view="hidden")["total"] == 1
    change(app, wid, dict(type="restore", event_id=night["id"]))
    assert app.events(wid)["total"] == 1


def test_backup_restore_evidence_integrity_and_export_identity(local, tmp_path):
    app, wid = local
    data = b"local-crop"
    eid = hashlib.sha256(data).hexdigest()[:20]
    r = report()
    r["events"][0]["sources"][0]["evidence"]["image"] = eid
    r["files"][0]["ocr"] = {
        "crops": {eid: base64.b64encode(data).decode()},
        "blocks": [{"text": "private"}],
        "preview_image": "whole-image",
    }
    r = app.store.externalize(r)
    change(app, wid, dict(type="append"), draft(app, wid, r))
    profile = app.save_profile(wid, "我的日历", {"alarm": 15})
    app.export_file(wid, 1, {"alarm": 15}, tmp_path / "one.ics", profile["id"])
    app.save_template(
        "班次",
        {"shifts": [dict(name="早", aliases=["早"], start="08:00", end="16:00")]},
    )
    backup = pack_backup(app.store, wid)
    payload = unpack_backup(backup)
    assert payload["evidence"]["crops"][eid] == base64.b64encode(data).decode()
    assert "whole-image" not in encode(payload)
    assert '"text":"private"' not in encode(payload)
    assert all(not record["path"] for record in payload["exports"])
    prepared = app.prepare_restore(backup)
    restored = app.restore_backup(prepared["token"])
    newwid = restored["id"]
    assert newwid != wid
    assert app.events(newwid)["items"][0]["id"] == app.events(wid)["items"][0]["id"]
    assert (
        app.store.documents("export", newwid)[0]["profile_id"]
        == app.store.documents("profile", newwid)[0]["id"]
    )
    assert "path" not in app.store.documents("export", newwid)[0]
    app.export_file(newwid, restored["version"], {"alarm": 15}, tmp_path / "two.ics")
    uid = lambda p: next(
        s for s in p.read_text(encoding="utf-8").splitlines() if s.startswith("UID:")
    )
    assert uid(tmp_path / "one.ics") == uid(tmp_path / "two.ics")
    (app.store.evidence_dir / (eid + ".jpg")).write_bytes(b"corrupt")
    with pytest.raises(LocalError):
        pack_backup(app.store, wid)


def test_restore_stale_preview_version_and_sequence_never_regress(local, tmp_path):
    app, wid = local
    imported(app, wid)
    app.export_file(wid, 1, {"alarm": 15}, tmp_path / "one.ics")
    backup = pack_backup(app.store, wid)
    app.export_file(wid, 1, {"alarm": 30}, tmp_path / "two.ics")
    token = app.prepare_restore(backup)["token"]
    with pytest.raises(LocalError):
        app.restore_backup(token, wid, 0)
    app.restore_backup(token, wid, 1)
    assert app.workspace(wid)["version"] == 2
    result = app.export_file(wid, 2, {"alarm": 15}, tmp_path / "three.ics")
    assert "SEQUENCE:2" in (tmp_path / "three.ics").read_text(encoding="utf-8")
    assert result["count"] == 1
    with pytest.raises(LocalError):
        app.restore_backup(token)


def test_v1_and_v2_migration_preserve_id_and_personal_review(local):
    app, wid = local
    r = report()
    old = deepcopy(r["events"][0])
    r["events"][0]["location"] = "个人地点"
    r["events"][0]["reviews"] = [
        dict(before=old, after={"location": "个人地点"}, edited_at=now())
    ]
    snapshot = dict(version=1, personName=NAME, report=r, savedAt=now())
    first = app.restore_backup(app.prepare_restore(encode(snapshot).encode())["token"])
    migrated = app.store.workspace(first["id"])["calendar"]
    assert migrated["events"][0]["id"] == r["events"][0]["id"]
    assert migrated["events"][0]["overrides"]["location"] == "个人地点"
    payload = encode(dict(schema=2, calendar=migrated, referenceYear=2026))
    envelope = encode(dict(payload=payload, checksum=fnv_js(payload))).encode()
    second = app.restore_backup(app.prepare_restore(envelope)["token"])
    assert app.events(second["id"])["items"][0]["id"] == r["events"][0]["id"]
    with pytest.raises(LocalError):
        unpack_backup(encode(dict(payload=payload, checksum="bad")).encode())
    assert fnv_js("😀") == "cb31c4b8"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/data", "x\\y"])
def test_restore_rejects_unsafe_archive_paths(local, name):
    app, wid = local
    prior = app.store.workspace(wid)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr(name, b"data")
    with pytest.raises(LocalError):
        app.prepare_restore(data.getvalue())
    assert app.store.workspace(wid) == prior


def test_invalid_inputs_do_not_mutate_and_auxiliary_documents(local):
    app, wid = local
    for operation in [
        dict(type="append"),
        dict(type="archive"),
        dict(type="manual", values={}),
    ]:
        with pytest.raises((ValueError, KeyError)):
            change(app, wid, operation)
    with pytest.raises(LocalError):
        app.preview_change(wid, 9, dict(type="undo"))
    jid = draft(app, wid)
    other = app.create_workspace("星辰奕歌乙")["id"]
    with pytest.raises(LocalError):
        change(app, other, dict(type="append"), jid)
    with pytest.raises(LocalError):
        change(app, wid, dict(type="undo"), jid)
    for edits in [
        [],
        [dict(index=99, values={})],
        [dict(index=0, values={}), dict(index=0, values={})],
    ]:
        with pytest.raises(LocalError):
            app.edit_draft(jid, edits)
    with pytest.raises(LocalError):
        app.store.workspace("missing")
    with pytest.raises(LocalError):
        app.store.document("job", "missing")
    for evidence in ["../escape", "0" * 20]:
        with pytest.raises(LocalError):
            app.store.evidence(evidence)
    app.store.delete("job", jid)
    assert not app.list_jobs(wid)


def test_template_course_and_export_filters(local, tmp_path):
    app, wid = local
    template = app.save_template(
        "学校",
        {
            "semester": dict(
                monday="2026-12-28", weeks=4, periods=[dict(start="08:00", end="08:45")]
            )
        },
        "已核对作息",
    )
    copy = app.import_template(app.export_template(template["id"]))
    assert copy["id"] != template["id"] and len(app.templates()) == 2
    with pytest.raises(LocalError):
        app.import_template('{"format":"calisift.template","version":99}')
    with pytest.raises(LocalError):
        app.save_template("", {})
    with pytest.raises(LocalError):
        app.save_profile(wid, "", {})
    job = app.course_draft(
        wid,
        dict(title="课程", weekday=1, periods=[1], parity="odd"),
        template["rules"]["semester"],
    )
    assert [e["date"] for e in job["report"]["events"]] == ["2026-12-28", "2027-01-11"]
    change(app, wid, dict(type="append", source_name="学校"), job["id"])
    sid = app.workspace(wid)["sources"][0]["id"]
    assert app.events(wid, source_id=sid, date_from="2027-01-01")["total"] == 1
    assert app.events(wid, source_id="other")["total"] == 0
    assert app.events(wid, query="学校")["total"] == 2
    assert app.events(wid, category="培训")["total"] == 0
    preview = app.export_preview(
        wid, {"from": "2027-01-01", "category": "学习", "source_id": sid}
    )
    assert preview["count"] == 1
    assert app.export_preview(wid, {"source_id": "other"})["count"] == 0
    assert app.export_preview(wid, {"category": "工作"})["count"] == 0
    with pytest.raises(LocalError):
        app.export_file(wid, 0, {}, tmp_path / "x.ics")
    with pytest.raises(LocalError):
        app.export_file(wid, 1, {"category": "工作"}, tmp_path / "x.ics")
    change(
        app, wid, dict(type="manual", values=dict(date="2027-01-01", title="时间待填"))
    )
    assert app.export_preview(wid, {})["blocked"]
    with pytest.raises(LocalError):
        app.export_file(wid, 2, {}, tmp_path / "x.ics")


def test_schema_migration_refuses_newer_database(tmp_path):
    path = tmp_path / "calendar.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    before = path.read_bytes()
    with pytest.raises(LocalError, match="更新版本"):
        LocalStore(tmp_path)
    assert path.read_bytes() == before


def test_saved_calendar_survives_recovery_point_failure(local, monkeypatch):
    app, wid = local
    monkeypatch.setattr(
        app.store,
        "safety_backup",
        lambda *a: (_ for _ in ()).throw(OSError("disk full")),
    )
    result = change(
        app, wid, dict(type="manual", values=dict(date="2026-09-01", title="考试"))
    )
    assert result["warning"] and app.events(wid)["total"] == 1

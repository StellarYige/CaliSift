from copy import deepcopy
from datetime import date
import pytest
from fastapi.testclient import TestClient
from xingcheng.api import app
from xingcheng.calendar import (
    empty_calendar,
    transform,
    export_ics,
    effective,
    validate_calendar,
)
from xingcheng.parsing import parse_file
from xingcheng.rules import expand_course
from scripts.generate_fixtures import NAME, csv_bytes


def report(day="2026-09-07", title="培训", timing="08:00-10:00", filename="表.csv"):
    return parse_file(
        csv_bytes([["日期", "姓名", "事项", "时间"], [day, NAME, title, timing]]),
        filename,
        NAME,
        2026,
    ).to_dict()


def apply(calendar, **op):
    return transform(calendar, calendar["version"], op)


def saved():
    return apply(
        empty_calendar(NAME), type="append", report=report(), source_name="工作"
    )["calendar"]


def update(c, r, **options):
    return apply(
        c,
        type="update",
        source_id=c["sources"][0]["id"],
        report=r,
        coverage=["2026-09-01", "2026-09-30"],
        **options,
    )


def test_append_preserves_identity_and_duplicate_contributions():
    c = saved()
    before = deepcopy(c)
    first = c["events"][0]["id"]
    result = apply(
        c, type="append", report=report(filename="另一个文件.csv"), source_name="培训"
    )
    assert len(result["calendar"]["events"]) == 1
    assert result["calendar"]["events"][0]["id"] == first
    assert len(result["calendar"]["events"][0]["contributions"]) == 2
    assert result["summary"]["duplicates"] == 1
    result = apply(
        result["calendar"],
        type="append",
        report=report(day="2026-09-08"),
        source_name="次日",
    )
    assert len(result["report"]["events"]) == 2
    assert c == before  # original transaction was never mutated


def test_same_filename_changed_content_is_new_by_default():
    c = saved()
    r = apply(c, type="append", report=report(timing="14:00-16:00"))
    assert len(r["report"]["events"]) == 2
    assert c["events"][0]["id"] != r["calendar"]["events"][1]["id"]


def test_update_requires_explicit_mapping_and_cancel_acknowledgement():
    c = saved()
    old = c["events"][0]["id"]
    result = update(c, report(timing="14:00-16:00"))
    assert len(result["summary"]["unresolved"]) == 1
    mapped = update(c, report(timing="14:00-16:00"), mappings={"0": old})
    assert not mapped["summary"]["unresolved"]
    assert mapped["calendar"]["events"][0]["id"] == old
    assert mapped["calendar"]["events"][0]["sequence"] == 1
    assert mapped["summary"]["changed"][0]["kinds"] == ["改时间"]


@pytest.mark.parametrize("bad", ["empty", "no_name", "partial", "pending"])
def test_incomplete_update_never_cancels(bad):
    c = saved()
    r = report(day="2026-09-08")
    if bad == "empty":
        r["events"] = []
    if bad == "no_name":
        r["files"][0]["sheets"][0]["name_matches"] = 0
    if bad == "partial":
        r["files"].append(dict(filename="坏表.csv", status="error", sheets=[]))
    if bad == "pending":
        p = deepcopy(r["events"][0])
        p.update(date=None, status="pending")
        r["pending"] = [p]
    result = update(c, r)
    assert not result["summary"]["cancelled"]
    assert result["report"]["events"][0]["date"] == "2026-09-07"


def test_other_source_retains_original_when_one_changes_or_cancels():
    c = apply(saved(), type="append", report=report(), source_name="另一个来源")[
        "calendar"
    ]
    old = c["events"][0]["id"]
    r = update(c, report(timing="14:00-16:00"), mappings={"0": old})
    assert sorted(e["start"] for e in r["report"]["events"]) == ["08:00", "14:00"]
    assert len(r["calendar"]["events"][0]["contributions"]) == 1
    restored = apply(r["calendar"], type="undo")
    assert len(restored["report"]["events"]) == 1
    assert len(restored["calendar"]["events"][0]["contributions"]) == 2
    cancelled = update(c, report(day="2026-09-09"), cancel_ids=[old])
    assert len(cancelled["report"]["events"]) == 2


def test_personal_override_choices_and_undo_preserve_later_unrelated_changes():
    c = saved()
    eid = c["events"][0]["id"]
    c = apply(c, type="edit", event_id=eid, values={"location": "我选的地点"})[
        "calendar"
    ]
    r = report()
    r["events"][0]["location"] = "新版地点"
    conflict = update(c, r, mappings={"0": eid})
    assert conflict["summary"]["unresolved"]
    keep = update(c, r, mappings={"0": eid}, correction_choices={eid: "keep"})
    assert keep["report"]["events"][0]["location"] == "我选的地点"
    adopt = update(c, r, mappings={"0": eid}, correction_choices={eid: "new"})
    assert adopt["report"]["events"][0]["location"] == "新版地点"
    extra = apply(
        adopt["calendar"], type="manual", values=dict(date="2026-10-02", title="考试")
    )["calendar"]
    undone = apply(extra, type="undo")
    assert len(undone["report"]["events"]) == 2
    assert undone["report"]["events"][0]["location"] == "我选的地点"
    assert undone["report"]["events"][0]["id"] == eid
    assert (
        undone["report"]["events"][0]["sequence"]
        > adopt["report"]["events"][0]["sequence"]
    )


def test_version_limits_and_hidden_restore():
    c = saved()
    eid = c["events"][0]["id"]
    with pytest.raises(ValueError, match="已变化"):
        transform(c, 0, dict(type="hide", event_id=eid))
    hidden = apply(c, type="hide", event_id=eid)["calendar"]
    assert not apply(hidden, type="restore", event_id=eid)["calendar"]["events"][0][
        "hidden"
    ]
    for _ in range(5):
        c = apply(c, type="append", source_id=c["sources"][0]["id"], report=report())[
            "calendar"
        ]
    assert len(c["sources"][0]["revisions"]) == 3
    invalid = deepcopy(c)
    invalid["sources"] *= 101
    with pytest.raises(ValueError):
        validate_calendar(invalid)


def test_rules_source_scope_explicit_time_and_rule_revisions():
    c = apply(
        empty_calendar(NAME), type="append", report=report(title="早", timing="")
    )["calendar"]
    rule = {
        "shifts": [
            dict(
                name="早班",
                aliases=["早", "早班"],
                start="22:00",
                end="06:00",
                next_day=True,
            )
        ]
    }
    r = apply(
        c, type="source_config", source_id=c["sources"][0]["id"], rules=rule, apply=True
    )
    assert r["report"]["events"][0]["end_date"] == "2026-09-08"
    assert "个人规则" in r["report"]["events"][0]["field_basis"]["start"]
    rule["shifts"][0]["start"] = "21:00"
    r = apply(
        r["calendar"],
        type="source_config",
        source_id=c["sources"][0]["id"],
        rules=rule,
        apply=True,
    )
    assert r["report"]["events"][0]["start"] == "21:00"
    explicit = saved()
    r = apply(
        explicit,
        type="source_config",
        source_id=explicit["sources"][0]["id"],
        rules=rule,
        apply=True,
    )
    assert r["report"]["events"][0]["start"] == "08:00"


def test_courses_cross_year_parity_periods_and_single_edit():
    semester = dict(
        monday="2026-12-28",
        weeks=4,
        periods=[dict(start="08:00", end="08:45"), dict(start="09:00", end="09:45")],
    )
    course = dict(title="课程", weekday=1, periods=[1, 2], parity="odd")
    r = expand_course(course, semester)
    assert [e["date"] for e in r["events"]] == ["2026-12-28", "2027-01-11"]
    c = apply(empty_calendar(NAME), type="append", report=r)["calendar"]
    result = apply(
        c,
        type="edit",
        event_id=c["events"][0]["id"],
        values={"date": "2026-12-29", "end_date": "2026-12-29"},
    )
    assert result["report"]["events"][1]["date"] == "2027-01-11"
    course.update(parity="all", weeks=[2, 4])
    assert len(expand_course(course, semester)["events"]) == 2
    with pytest.raises(ValueError):
        expand_course({**course, "periods": [1, 3]}, semester)


def test_ics_unicode_folding_escaping_point_all_day_and_stable_uid():
    c = saved()
    eid = c["events"][0]["id"]
    c = apply(
        c,
        type="edit",
        event_id=eid,
        values={"title": "培训,;\\\n" + "中文" * 50, "notes": ["地点\n下一行"]},
    )["calendar"]
    ics = export_ics(c, {"alarm": 15})
    assert f"UID:{eid}@xingcheng.local" in ics and "SEQUENCE:1" in ics
    assert "TRIGGER:-PT15M" in ics and "\\,\\;\\\\\\n" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    point = apply(empty_calendar(NAME), type="append", report=report(timing="14:00"))[
        "calendar"
    ]
    assert "DTEND" not in export_ics(point, {})
    day = apply(
        empty_calendar(NAME),
        type="manual",
        values=dict(date="2026-09-07", title="考试"),
    )["calendar"]
    with pytest.raises(ValueError, match="全天"):
        export_ics(day, {})
    day = apply(
        day, type="edit", event_id=day["events"][0]["id"], values={"all_day": True}
    )["calendar"]
    assert "DTEND;VALUE=DATE:20260908" in export_ics(day, {})


def test_real_http_calendar_transform_export_and_validation():
    client = TestClient(app)
    c = saved()
    r = client.post(
        "/api/calendar/transform",
        json=dict(
            calendar=c,
            expected_version=c["version"],
            operation=dict(type="hide", event_id="missing"),
        ),
    )
    assert r.status_code == 422
    r = client.post(
        "/api/calendar/export", json=dict(calendar=c, options={"alarm": 30})
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith(
        "text/calendar"
    )
    assert "BEGIN:VALARM" in r.text


def test_rule_changes_split_shared_events_without_changing_other_source():
    first = apply(
        empty_calendar(NAME), type="append", report=report(title="早", timing="")
    )["calendar"]
    c = apply(
        first,
        type="append",
        report=report(title="早", timing=""),
        source_name="其他单位",
    )["calendar"]
    rules = {"shifts": [dict(name="早班", aliases=["早"], start="08:00", end="16:00")]}
    result = apply(
        c,
        type="source_config",
        source_id=c["sources"][0]["id"],
        rules=rules,
        apply=True,
    )
    assert len(result["report"]["events"]) == 2
    assert {e["start"] for e in result["report"]["events"]} == {None, "08:00"}


def test_batch_draft_keeps_original_and_manual_correction_separate():
    r = report()
    original = deepcopy(r["events"][0])
    r["events"][0]["location"] = "手动地点"
    r["events"][0]["reviews"] = [
        dict(before=original, edited_at="2026-09-07T00:00:00Z")
    ]
    result = apply(empty_calendar(NAME), type="append", report=r)
    e = result["calendar"]["events"][0]
    assert (
        e["base"]["location"] == "" and e["contributions"][0]["raw"]["location"] == ""
    )
    assert e["overrides"]["location"] == "手动地点"
    assert result["report"]["events"][0]["field_basis"]["location"] == "手动修正"


def test_export_filters_and_hidden_pending_items():
    c = saved()
    sid = c["sources"][0]["id"]
    assert "VEVENT" not in export_ics(c, {"source_id": "missing"})
    assert "VEVENT" not in export_ics(c, {"category": "学习"})
    assert "VEVENT" not in export_ics(c, {"from": "2026-10-01"})
    assert "VEVENT" not in export_ics(c, {"to": "2026-08-01"})
    assert "VEVENT" in export_ics(c, {"source_id": sid})
    with pytest.raises(ValueError):
        export_ics(c, {"from": "2026-10-01", "to": "2026-09-01"})
    c = apply(c, type="hide", event_id=c["events"][0]["id"])["calendar"]
    assert "VEVENT" not in export_ics(c, {})


def test_shared_source_correction_choice_survives_repeated_preview():
    c = apply(saved(), type="append", report=report(), source_name="另一个来源")[
        "calendar"
    ]
    eid = c["events"][0]["id"]
    c = apply(c, type="edit", event_id=eid, values={"location": "手动地点"})["calendar"]
    r = report(timing="14:00-16:00")
    r["events"][0]["location"] = "新版地点"
    first = update(c, r, mappings={"0": eid})
    assert first["summary"]["correction_conflicts"][0]["id"] == eid
    second = update(c, r, mappings={"0": eid}, correction_choices={eid: "new"})
    assert not second["summary"]["unresolved"]
    assert {e["location"] for e in second["report"]["events"]} == {
        "手动地点",
        "新版地点",
    }

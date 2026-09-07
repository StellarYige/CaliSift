from copy import deepcopy
import io
import json
import sys
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from xingcheng.api import app
from xingcheng.parsing import parse_file
from xingcheng.rules import validate_rules, expand_course
from scripts.generate_fixtures import csv_bytes, NAME


@pytest.mark.parametrize(
    "rules",
    [
        {"unknown": 1},
        {"shifts": [{}]},
        {
            "shifts": [
                dict(name="早班", aliases=["早", "早"], start="08:00", end="16:00")
            ]
        },
        {"shifts": [dict(name="早班", aliases=["早"], start="25:00", end="16:00")]},
        {"shifts": [dict(name="夜班", aliases=["夜"], start="22:00", end="06:00")]},
        {"semester": dict(monday="2026-09-08", weeks=20, periods=[])},
        {"semester": dict(monday="2026-09-07", weeks=0, periods=[])},
        {"semester": dict(monday="2026-09-07", weeks=20, periods=[])},
        {
            "semester": dict(
                monday="2026-09-07",
                weeks=20,
                periods=[dict(start="08:00", end="07:00")],
            )
        },
        {
            "semester": dict(
                monday="2026-09-07",
                weeks=20,
                periods=[
                    dict(start="08:00", end="09:00"),
                    dict(start="08:45", end="09:30"),
                ],
            )
        },
        {"template": {"layout": "unknown"}},
        {"template": {"layout": "records", "header_row": -1}},
        {"template": {"layout": "records", "header_row": 0}},
    ],
)
def test_invalid_explicit_rules_have_actionable_errors(rules):
    with pytest.raises(ValueError):
        validate_rules(rules)


@pytest.mark.parametrize(
    "rules",
    [
        {"shifts": {}},
        {"shifts": [dict(name="早", aliases="早", start="08:00", end="16:00")]},
        {
            "shifts": [
                dict(
                    name="早",
                    aliases=["早"],
                    start="08:00",
                    end="16:00",
                    private_token="never share",
                )
            ]
        },
        {
            "shifts": [
                dict(
                    name="早",
                    aliases=["早"],
                    start="08:00",
                    end="16:00",
                    next_day="yes",
                )
            ]
        },
        {
            "semester": dict(
                monday="2026-09-07",
                weeks=20,
                periods=[dict(start="08:00", end="09:00", command="no")],
            )
        },
        {
            "template": dict(
                layout="records", header_row=0, headers=["姓名"], mapping={"name": -1}
            )
        },
        {
            "template": dict(
                layout="records",
                header_row=0,
                headers=["姓名"],
                mapping={"name": 0},
                script="no",
            )
        },
    ],
)
def test_shared_templates_reject_undeclared_fields_and_bad_types(rules):
    with pytest.raises(ValueError):
        validate_rules(rules)


def test_template_custom_headers_and_mismatch_fail_closed():
    rows = [["哪一天", "谁的", "做什么"], ["2026-09-07", NAME, "培训"]]
    template = dict(
        layout="records",
        header_row=0,
        headers=rows[0],
        mapping=dict(name=1, date=0, title=2),
    )
    assert validate_rules({"template": template})
    r = parse_file(csv_bytes(rows), "表.csv", NAME, 2026, template)
    assert r.events[0].title == "培训" and r.events[0].date == "2026-09-07"
    bad = deepcopy(template)
    bad["headers"] = ["新结构"]
    r = parse_file(csv_bytes(rows), "表.csv", NAME, 2026, bad)
    assert not r.events and r.pending and r.warnings


@pytest.mark.parametrize("horizontal", [True, False])
def test_explicit_matrix_axes(horizontal):
    rows = [
        ["姓名", "2026-09-07", "2026-09-08"],
        [NAME, "早", "夜"],
        ["星辰奕歌甲", "晚", "休"],
    ]
    if not horizontal:
        rows = [list(r) for r in zip(*rows)]
    t = dict(
        layout="names_rows" if horizontal else "names_columns",
        header_row=0,
        headers=rows[0],
        mapping={"name": 0, "date": 0},
    )
    r = parse_file(csv_bytes(rows), "表.csv", NAME, 2026, t)
    assert len(r.events) == 2
    assert [e.date for e in r.events] == ["2026-09-07", "2026-09-08"]


def test_worker_rule_path_and_layout_hint_without_network(tmp_path):
    from xingcheng.worker import main

    file = tmp_path / "input.csv"
    file.write_bytes(csv_bytes([["日期", "姓名", "事项"], ["2026-09-07", NAME, "早"]]))
    settings = dict(
        filename="表.csv",
        name=NAME,
        reference_year=2026,
        rules={
            "shifts": [dict(name="早班", aliases=["早"], start="08:00", end="16:00")]
        },
    )
    out = io.StringIO()
    with (
        patch.object(sys, "argv", ["worker", str(file)]),
        patch.object(sys, "stdin", io.StringIO(json.dumps(settings))),
        patch.object(sys, "stdout", out),
    ):
        main()
    value = json.loads(out.getvalue())
    assert value["events"][0]["start"] == "08:00"
    assert "个人规则" in value["events"][0]["sources"][0]["evidence"]["time"]


def test_http_rules_courses_and_ocr_failures():
    client = TestClient(app)
    content = csv_bytes([["日期", "姓名", "事项"], ["2026-09-07", NAME, "早"]])
    rule = {"shifts": [dict(name="早班", aliases=["早"], start="08:00", end="16:00")]}
    r = client.post(
        "/api/parse",
        files={"files": ("表.csv", content)},
        data=dict(name=NAME, reference_year=2026, rules=json.dumps(rule)),
    )
    assert r.status_code == 200 and r.json()["events"][0]["start"] == "08:00"
    assert (
        client.post(
            "/api/parse",
            files={"files": ("表.csv", content)},
            data=dict(name=NAME, reference_year=2026, rules="bad"),
        ).status_code
        == 422
    )
    semester = dict(
        monday="2026-09-07", weeks=4, periods=[dict(start="08:00", end="08:45")]
    )
    course = dict(title="课程", weekday=2, periods=[1], parity="even")
    r = client.post("/api/calendar/course", json=dict(course=course, semester=semester))
    assert r.status_code == 200 and len(r.json()["events"]) == 2
    for c in [
        {**course, "weeks": [8]},
        {**course, "parity": "bad"},
        {**course, "title": ""},
        {**course, "week_from": 4, "week_to": 1},
    ]:
        assert (
            client.post(
                "/api/calendar/course", json=dict(course=c, semester=semester)
            ).status_code
            == 422
        )
    with patch(
        "xingcheng.ocr.recognize_isolated",
        return_value={"events": [], "pending": [], "files": []},
    ):
        assert (
            client.post(
                "/api/ocr",
                files={"file": ("image.png", b"x")},
                data=dict(name=NAME, reference_year=2026),
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/api/ocr",
            files={"file": ("image.png", b"x")},
            data=dict(name="甲 乙", reference_year=2026),
        ).status_code
        == 422
    )

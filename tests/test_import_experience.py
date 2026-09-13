from tests.test_browser_application import write_download
"""Synthetic regression cases, not real anonymized schedules or acceptance data."""

from datetime import datetime
from pathlib import Path
import json

import pytest

from scripts.generate_fixtures import NAME, csv_bytes, xlsx_bytes
from xingcheng.aggregate import merge_reports
from xingcheng.parsing import parse_file
from xingcheng.temporal import Context, parse_date, parse_time
from tests.test_browser_application import local, draft, change

ROOT = Path(__file__).resolve().parents[1]


def parse(rows):
    return merge_reports([parse_file(csv_bytes(rows), "synthetic.csv", NAME, 2026)])


@pytest.mark.parametrize("transpose", [False, True])
def test_matrix_skips_other_peoples_times_on_date_axis(transpose):
    rows = [
        ["姓名", "2026-09-08", "2026-09-09"],
        ["林知夏", "早班 08:00-16:00", "夜班 22:00-06:00"],
        [NAME, "夜班 22:00-06:00", "早班 08:00-16:00"],
        [NAME + "甲", "休息", "休息"],
    ]
    if transpose:
        rows = list(map(list, zip(*rows)))
    report = parse(rows)
    assert not report.pending
    assert [(e.date, e.start, e.end_date) for e in report.events] == [
        ("2026-09-08", "22:00", "2026-09-09"),
        ("2026-09-09", "08:00", "2026-09-09"),
    ]
    assert {e.sources[0].name_cell for e in report.events} == {
        "C1" if transpose else "A3"
    }


@pytest.mark.parametrize(
    "value,start,end,next_day",
    [
        ("晚上十点至次日六点", "22:00", "06:00", True),
        ("8-16时", "08:00", "16:00", False),
        ("8至次日9点", "08:00", "09:00", True),
    ],
)
def test_explicit_hour_ranges(value, start, end, next_day):
    timing = parse_time(value)
    assert (timing.start, timing.end, timing.next_day) == (start, end, next_day)
    assert timing.warning is None


@pytest.mark.parametrize("ending", ["次日09:00", "次日08:00", "24:00"])
def test_separate_end_column_preserves_explicit_next_day(ending):
    report = parse(
        [
            ["日期", "姓名", "事项", "开始时间", "结束时间"],
            ["2026-12-31", NAME, "值班", "08:00", ending],
        ]
    )
    assert not report.pending
    event = report.events[0]
    expected_end = "00:00" if ending == "24:00" else ending.removeprefix("次日")
    assert (event.start, event.end, event.end_date) == (
        "08:00",
        expected_end,
        "2027-01-01",
    )


def test_full_excel_timestamps_preserve_end_date_and_midnight():
    rows = [
        ["日期", "姓名", "事项", "开始时间", "结束时间"],
        [
            datetime(2026, 12, 31),
            NAME,
            "值班",
            datetime(2026, 12, 31, 0),
            datetime(2027, 1, 1, 9),
        ],
    ]
    result = parse_file(xlsx_bytes({"安排": rows}), "synthetic.xlsx", NAME, 2026)
    assert not result.pending
    event = result.events[0]
    assert (event.start, event.end, event.end_date) == ("00:00", "09:00", "2027-01-01")


@pytest.mark.parametrize("start,end", [("", "10:00"), ("08:00", "待定"), ("待定", "")])
def test_unresolved_explicit_time_is_pending(start, end):
    result = parse(
        [
            ["日期", "姓名", "事项", "开始时间", "结束时间"],
            ["2026-09-08", NAME, "培训", start, end],
        ]
    )
    assert not result.events and len(result.pending) == 1
    assert any("时间" in w for w in result.pending[0].warnings)


def test_spaced_multiple_dates_never_silently_take_first():
    day, warnings = parse_date("2026 / 9 / 8、2026 / 9 / 9", Context(2026))
    assert day is None and warnings


@pytest.mark.parametrize("value", ["08:00-16:00", "夜班 22:00-06:00", "8-16时"])
def test_time_axis_is_not_invalid_month_day(value):
    assert parse_date(value, Context(2026), allow_day=True) == (None, [])


@pytest.mark.parametrize("value", [0.999999, "25-26", "08:00-99:00"])
def test_invalid_or_out_of_day_times_do_not_produce_exportable_values(value):
    timing = parse_time(value)
    assert timing.warning and timing.start is None


@pytest.mark.parametrize(
    "path,expected,pending,conflicts",
    [
        (
            "samples/九月排班.csv",
            [
                ("2026-09-08", "早班", "08:00", "16:00", "2026-09-08"),
                ("2026-09-10", "夜班", "20:00", "08:00", "2026-09-11"),
            ],
            0,
            0,
        ),
        (
            "samples/培训通知.csv",
            [
                ("2026-09-09", "急救培训", "09:00", "11:00", "2026-09-09"),
                ("2026-09-12", "资格考试", "14:00", "16:00", "2026-09-12"),
            ],
            0,
            0,
        ),
        (
            "tests/fixtures/9月排班表.xlsx",
            [
                ("2026-09-07", "早班", "08:00", "16:00", "2026-09-07"),
                ("2026-09-08", "休息", None, None, None),
            ],
            0,
            0,
        ),
        (
            "tests/fixtures/培训安排.xlsx",
            [("2026-09-12", "消防培训", "14:00", None, None)],
            0,
            0,
        ),
        (
            "tests/fixtures/国庆值班表.xlsx",
            [("2026-10-02", "国庆值班", None, None, None)],
            0,
            0,
        ),
        (
            "tests/fixtures/冲突与重复.xlsx",
            [
                ("2026-09-07", "早班", "08:00", "16:00", "2026-09-07"),
                ("2026-09-07", "应急演练", "15:00", "17:00", "2026-09-07"),
            ],
            0,
            1,
        ),
        (
            "tests/fixtures/纵向排班.xls",
            [
                ("2026-09-09", "夜班", "22:00", "06:00", "2026-09-10"),
                ("2026-09-10", "休息", None, None, None),
            ],
            0,
            0,
        ),
        (
            "tests/fixtures/考试安排.csv",
            [("2026-09-15", "计算机基础", "09:00", "11:00", "2026-09-15")],
            0,
            0,
        ),
        (
            "tests/fixtures/合并表头.xlsx",
            [
                ("2026-09-07", "早班", None, None, None),
                ("2026-09-08", "晚班", None, None, None),
            ],
            0,
            0,
        ),
        ("tests/fixtures/周期课表待确认.xlsx", [], 1, 0),
    ],
)
def test_existing_sample_bytes_without_regenerating(path, expected, pending, conflicts):
    file = ROOT / path
    result = merge_reports([parse_file(file.read_bytes(), file.name, NAME, 2026)])
    assert [
        (e.date, e.title, e.start, e.end, e.end_date) for e in result.events
    ] == expected
    assert len(result.pending) == pending
    assert len(result.conflicts) == conflicts
    assert all(e.sources[0].name_cell for e in result.events + result.pending)


def test_existing_annotated_development_corpus_and_provenance():
    from scripts.evaluate_accuracy import evaluate

    result = evaluate(ROOT / "tests/fixtures/accuracy/development.json", False)
    assert sum(case["correct"] for case in result["cases"]) == 8
    assert sum(case["produced"] for case in result["cases"]) == 8
    assert result["totals"]["table"]["name_mismatches"] == 0
    assert not result["acceptance_passed"]
    assert all(case["manual_operations"] is None for case in result["cases"])
    corpus = json.loads(
        (ROOT / "tests/fixtures/table-corpus.json").read_text(encoding="utf-8")
    )
    supplied = {
        str(file.relative_to(ROOT)).replace("\\", "/")
        for base in (ROOT / "samples", ROOT / "tests/fixtures")
        for file in base.rglob("*")
        if file.suffix in {".csv", ".xls", ".xlsx"}
    }
    assert supplied == set(corpus["synthetic_files"] + corpus["real_anonymized_files"])
    assert not set(corpus["synthetic_files"]) & set(corpus["real_anonymized_files"])


def test_review_recomputes_conflicts_and_keeps_original_warnings(local):
    app, wid = local
    report = parse(
        [
            ["日期", "姓名", "事项", "时间"],
            ["9月8日", NAME, "值班", "08:00-10:00"],
            ["9月8日", NAME, "培训", "09:00-11:00"],
        ]
    ).to_dict()
    jid = draft(app, wid, report)
    assert len(app.get_job(jid)["report"]["conflicts"]) == 1
    revised = app.edit_draft(
        jid,
        [
            {
                "index": 1,
                "values": {
                    "start": "10:00",
                    "end": "11:00",
                    "status": "confirmed",
                },
            }
        ],
    )["report"]
    assert revised["conflicts"] == []
    corrected = revised["events"][1]
    assert corrected["warnings"] == []
    assert corrected["reviews"][0]["before"]["warnings"]
    assert corrected["sources"] == report["events"][1]["sources"]
    revised = app.edit_draft(jid, [{"index": 1, "values": {"start": "09:30"}}])[
        "report"
    ]
    assert revised["conflicts"][0]["event_ids"] == [e["id"] for e in revised["events"]]


def test_preview_includes_conflicts_with_saved_events_and_both_sources(local):
    app, wid = local
    old = parse(
        [
            ["日期", "姓名", "事项", "时间"],
            ["2026-09-08", NAME, "原有值班", "08:00-16:00"],
        ]
    ).to_dict()
    new = parse(
        [
            ["日期", "姓名", "事项", "时间"],
            ["2026-09-08", NAME, "新增培训", "09:00-10:00"],
        ]
    ).to_dict()
    change(
        app, wid, {"type": "append", "source_name": "原有安排"}, draft(app, wid, old)
    )
    assert new["conflicts"] == []
    preview = change(
        app,
        wid,
        {"type": "append", "source_name": "新通知"},
        draft(app, wid, new),
        False,
    )
    conflicts = preview["summary"]["schedule_conflicts"]
    assert len(conflicts) == 1 and conflicts[0]["kind"] == "definite"
    events = preview["summary"]["schedule_conflict_events"]
    assert set(events) == set(conflicts[0]["event_ids"])
    assert {e["title"] for e in events.values()} == {"原有值班", "新增培训"}
    assert all(e["sources"][0]["excerpt"] for e in events.values())
    assert app.workspace(wid)["count"] == 1


def test_same_named_staged_files_expose_their_distinct_source_identity(local, tmp_path):
    from tests.test_browser_application import finish, input_files

    app, wid = local
    paths = []
    for i in range(2):
        directory = tmp_path / str(i)
        directory.mkdir()
        path = directory / "排班.csv"
        path.write_bytes(
            csv_bytes(
                [
                    ["姓名", "日期", "事项", "时间"],
                    [NAME, f"2026-09-{8+i:02}", "值班", "08:00-16:00"],
                ]
            )
        )
        paths.append(str(path))
    job = app.jobs.stage(wid, input_files(paths))
    app.jobs.start(job["id"], 2026)
    ready = finish(app, job["id"])
    assert ready["status"] == "review"
    sources = [e["sources"][0]["file_id"] for e in ready["report"]["events"]]
    assert len(set(sources)) == 2
    assert [f["source_file_ids"] for f in ready["files"]] == [[s] for s in sources]


def test_cross_year_import_review_save_and_ics_snapshot(local, tmp_path):
    app, wid = local
    report = parse(
        [
            ["日期", "姓名", "事项", "开始时间", "结束时间"],
            ["2026-12-31", NAME, "值班", "08:00", "次日09:00"],
            ["日期待定", NAME, "培训", "08:00", ""],
            ["2026-12-31", NAME + "甲", "他人的值班", "10:00", "11:00"],
        ]
    ).to_dict()
    assert len(report["events"]) == len(report["pending"]) == 1
    jid = draft(app, wid, report)
    change(app, wid, {"type": "append", "source_name": "合成跨年回归"}, jid)
    preview = app.export_preview(wid, {"alarm": 15})
    assert preview["count"] == 1 and len(preview["excluded"]) == 1
    target = tmp_path / "snapshot.ics"
    write_download(app, wid, preview["version"], {"alarm": 15}, str(target))
    original = target.read_bytes()
    text = original.decode("utf-8")
    assert "DTSTART;TZID=Asia/Shanghai:20261231T080000" in text
    assert "DTEND;TZID=Asia/Shanghai:20270101T090000" in text
    assert "培训" not in text and "他人的值班" not in text
    assert text.count("BEGIN:VEVENT") == 1
    # Editing the local calendar never mutates an already generated snapshot.
    event_id = app.events(wid)["items"][0]["id"]
    change(
        app,
        wid,
        {"type": "edit", "event_id": event_id, "values": {"location": "新地点"}},
    )
    assert target.read_bytes() == original

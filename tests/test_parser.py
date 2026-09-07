from datetime import datetime, time
from pathlib import Path

import pytest
from openpyxl.utils.datetime import CALENDAR_MAC_1904

from scripts.generate_fixtures import NAME, csv_bytes, generate, xls_bytes, xlsx_bytes
from xingcheng.aggregate import merge_reports
from xingcheng.parsing import matches_name, parse_file


def parse(rows, filename="安排.xlsx", sheets=None, merges=None, **kwargs):
    return merge_reports(
        [
            parse_file(
                xlsx_bytes(sheets or {"安排": rows}, merges, **kwargs),
                filename,
                NAME,
                2026,
            )
        ]
    )


@pytest.mark.parametrize(
    "separator", ["、", ",", "，", ";", "；", "\n", "/", " ", "|", "\t"]
)
def test_exact_multiname(separator):
    report = parse(
        [["日期", "姓名", "事项"], ["2026年9月7日", f"林知夏{separator}{NAME}", "培训"]]
    )
    assert [(e.date, e.title) for e in report.events] == [("2026-09-07", "培训")]


@pytest.mark.parametrize(
    "value",
    ["星辰奕", "小星辰奕歌", "星辰奕歌甲", "星辰奕歌老师", "林知夏", "星 辰奕歌"],
)
def test_no_substring(value):
    assert not matches_name(value, NAME)
    report = parse([["日期", "姓名", "事项"], ["2026-09-07", value, "培训"]])
    assert not report.events and not report.pending


def test_trim_name_and_cell():
    data = csv_bytes([["日期", "姓名", "事项"], ["2026-09-07", f" {NAME} ", "培训"]])
    assert len(parse_file(data, "培训.csv", f" {NAME} ", 2026).events) == 1


def test_demo_files(tmp_path):
    generate(tmp_path)
    reports = [
        parse_file((tmp_path / name).read_bytes(), name, NAME, 2026)
        for name in ["9月排班表.xlsx", "培训安排.xlsx", "国庆值班表.xlsx"]
    ]
    result = merge_reports(reports)
    assert [(e.date, e.start, e.end, e.title) for e in result.events] == [
        ("2026-09-07", "08:00", "16:00", "早班"),
        ("2026-09-08", None, None, "休息"),
        ("2026-09-12", "14:00", None, "消防培训"),
        ("2026-10-02", None, None, "国庆值班"),
    ]
    assert not result.pending
    assert result.events[2].location == "一楼培训室"
    assert result.events[2].notes == ["提前十分钟到场"]
    assert result.events[2].sources[0].name_cell == "D2"
    extra = parse_file(
        (tmp_path / "冲突与重复.xlsx").read_bytes(), "冲突与重复.xlsx", NAME, 2026
    )
    merged = merge_reports(reports + [extra])
    assert len(merged.events) == 5
    assert len(merged.events[0].sources) == 2
    assert [c["kind"] for c in merged.conflicts] == ["definite"]


@pytest.mark.parametrize("ext", ["xls", "xlsx", "csv"])
def test_formats_real_bytes(ext):
    rows = [
        ["日期", "姓名", "事项", "时间"],
        ["2026-09-07", NAME, "培训", "08:00-10:00"],
    ]
    data = {
        "xls": lambda: xls_bytes(rows),
        "xlsx": lambda: xlsx_bytes({"表": rows}),
        "csv": lambda: csv_bytes(rows),
    }[ext]()
    result = parse_file(data, f"培训.{ext}", NAME, 2026)
    assert [(e.date, e.start, e.end) for e in result.events] == [
        ("2026-09-07", "08:00", "10:00")
    ]


@pytest.mark.parametrize(
    "encoding,delimiter", [("utf-8", ","), ("utf-8-sig", ";"), ("gb18030", "\t")]
)
def test_csv_dialects(encoding, delimiter):
    data = csv_bytes(
        [
            ["日期", "姓名", "事项", "备注"],
            ["2026-09-07", NAME, "培训", '携带资料,含"附件"\n第二行'],
        ],
        encoding,
        delimiter,
    )
    result = parse_file(data, "培训.csv", NAME, 2026)
    assert result.events[0].notes == ['携带资料,含"附件"\n第二行']


def test_transposed_schedule():
    result = parse(
        [
            ["日期", NAME, "林知夏"],
            ["9月7日", "夜班 22:00-次日06:00", "早班"],
            ["9月8日", "休息", "早班"],
        ]
    )
    assert [(e.date, e.shift, e.end_date) for e in result.events] == [
        ("2026-09-07", "夜班", "2026-09-08"),
        ("2026-09-08", "休息", None),
    ]


def test_person_filled_grid_does_not_assign_others():
    result = parse(
        [
            ["班次", "9月7日", "9月8日"],
            ["早班", NAME, "林知夏"],
            ["晚班", "林知夏", NAME],
        ]
    )
    assert [(e.date, e.shift) for e in result.events] == [
        ("2026-09-07", "早班"),
        ("2026-09-08", "晚班"),
    ]
    assert all(e.start is None for e in result.events)


def test_person_grid_date_rows():
    result = parse(
        [
            ["日期", "早班", "晚班"],
            ["9月7日", NAME, "林知夏"],
            ["9月8日", "林知夏", NAME],
        ]
    )
    assert [(e.date, e.shift) for e in result.events] == [
        ("2026-09-07", "早班"),
        ("2026-09-08", "晚班"),
    ]


def test_merged_multilevel_header():
    result = parse(
        None,
        sheets={
            "2026年9月": [
                ["姓名", "9月7日", None],
                [None, "早班", "晚班"],
                [NAME, "08:00-16:00", "16:00-23:00"],
            ]
        },
        merges={"2026年9月": ["A1:A2", "B1:C1"]},
    )
    assert [(e.date, e.shift, e.start) for e in result.events] == [
        ("2026-09-07", "早班", "08:00"),
        ("2026-09-07", "晚班", "16:00"),
    ]
    assert result.events[1].sources[0].evidence["date"] == "B1"


@pytest.mark.parametrize("ext", ["xls", "xlsx"])
def test_merged_names_and_dates(ext):
    rows = [
        ["日期", "姓名", "事项", "时间"],
        ["2026-09-07", NAME, "培训", "08:00"],
        [None, None, "考试", "14:00"],
    ]
    data = (
        xls_bytes(rows, [(1, 2, 0, 0), (1, 2, 1, 1)])
        if ext == "xls"
        else xlsx_bytes({"表": rows}, {"表": ["A2:A3", "B2:B3"]})
    )
    result = parse_file(data, f"安排.{ext}", NAME, 2026)
    assert [(e.date, e.title) for e in result.events] == [
        ("2026-09-07", "培训"),
        ("2026-09-07", "考试"),
    ]


def test_blank_dates_not_filled():
    result = parse(
        [["日期", "姓名", "事项"], ["2026-09-07", NAME, "培训"], [None, NAME, "考试"]]
    )
    assert len(result.events) == len(result.pending) == 1
    assert result.pending[0].date is None


def test_multiple_sheets_and_hidden():
    result = parse(
        None,
        sheets={
            "一": [["日期", "姓名", "事项"], ["9月7日", NAME, "培训"]],
            "二": [["日期", "姓名", "事项"], ["9月8日", NAME, "考试"]],
            "空": [],
        },
        hidden=["二"],
    )
    assert len(result.events) == 2
    assert result.events[1].sources[0].hidden
    assert result.files[0]["sheets"][2]["status"] == "empty"


def test_separate_table_contexts():
    result = parse(
        [
            ["2026年9月排班表", None],
            ["姓名", "7日"],
            [NAME, "早班"],
            [],
            ["2026年10月排班表", None],
            ["姓名", "2日"],
            [NAME, "晚班"],
        ]
    )
    assert [(e.date, e.shift) for e in result.events] == [
        ("2026-09-07", "早班"),
        ("2026-10-02", "晚班"),
    ]


def test_repeated_record_header():
    result = parse(
        [
            ["2026年9月安排", None, None],
            ["日期", "姓名", "事项"],
            ["7日", NAME, "培训"],
            ["2026年10月安排", None, None],
            ["日期", "姓名", "事项"],
            ["2日", NAME, "考试"],
        ]
    )
    assert [(e.date, e.title) for e in result.events] == [
        ("2026-09-07", "培训"),
        ("2026-10-02", "考试"),
    ]


def test_side_by_side_tables():
    result = parse(
        [
            ["日期", "姓名", "事项", None, "日期", "姓名", "事项"],
            ["9月7日", NAME, "培训", None, "10月2日", NAME, "考试"],
        ]
    )
    assert [e.date for e in result.events] == ["2026-09-07", "2026-10-02"]


def test_repeated_horizontal_headers_without_blank_separator():
    result = parse(
        [
            ["2026年9月排班表", None],
            ["姓名", "7日"],
            [NAME, "早班"],
            ["2026年10月排班表", None],
            ["姓名", "2日"],
            [NAME, "晚班"],
        ]
    )
    assert [(e.date, e.shift) for e in result.events] == [
        ("2026-09-07", "早班"),
        ("2026-10-02", "晚班"),
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("二〇二六年九月七日", "2026-09-07"),
        ("2026/9/7", "2026-09-07"),
        ("2024年2月29日", "2024-02-29"),
        ("2026.9.7", "2026-09-07"),
        ("9月7号", "2026-09-07"),
    ],
)
def test_dates(value, expected):
    result = parse([["日期", "姓名", "事项"], [value, NAME, "培训"]])
    assert result.events[0].date == expected


@pytest.mark.parametrize(
    "value", ["2026年2月29日", "9月31日", "7日", "每周一", "2026-13-01"]
)
def test_unresolved_date(value):
    result = parse([["日期", "姓名", "事项"], [value, NAME, "培训"]])
    assert not result.events and len(result.pending) == 1


def test_reference_year_warning():
    data = csv_bytes([["日期", "姓名", "事项"], ["9月7日", NAME, "培训"]])
    result = parse_file(data, "培训.csv", NAME, 2027)
    assert result.events[0].date == "2027-09-07"
    assert "2027" in result.events[0].warnings[0]


@pytest.mark.parametrize("epoch", [None, CALENDAR_MAC_1904])
def test_excel_date_and_time(epoch):
    result = parse(
        [
            ["日期", "姓名", "事项", "开始时间", "结束时间"],
            [datetime(2026, 9, 7), NAME, "培训", time(8), time(10)],
        ],
        epoch=epoch,
    )
    assert (result.events[0].date, result.events[0].start, result.events[0].end) == (
        "2026-09-07",
        "08:00",
        "10:00",
    )


def test_xls_1904_epoch():
    data = xls_bytes(
        [["日期", "姓名", "事项"], [datetime(2026, 9, 7), NAME, "培训"]], datemode=True
    )
    assert parse_file(data, "培训.xls", NAME, 2026).events[0].date == "2026-09-07"


def test_weekly_course_pending():
    result = parse([["星期", "节次", "课程", "教师"], ["周一", "1–2节", "数学", NAME]])
    assert not result.events and result.pending


def test_unknown_layout_keeps_name_evidence():
    result = parse([["这是一份通知"], [f"林知夏、{NAME}"], ["下周再定"]])
    assert result.pending[0].sources[0].name_cell == "A2"


def test_short_dash_date_is_not_a_time_range():
    result = parse([["日期", "姓名", "事项"], ["9-7", NAME, "培训"]])
    assert result.events[0].date == "2026-09-07"
    assert result.events[0].start is None


def test_multiple_dates_never_silently_take_first():
    result = parse([["日期", "姓名", "事项"], ["9月7日、9月8日", NAME, "培训"]])
    assert not result.events and result.pending


@pytest.mark.parametrize(
    "columns,values",
    [(["时间"], ["08:00-08:00"]), (["开始时间", "结束时间"], ["08:00", "08:00"])],
)
def test_zero_duration_pending(columns, values):
    result = parse(
        [["日期", "姓名", "事项", *columns], ["9月7日", NAME, "培训", *values]]
    )
    assert not result.events and result.pending


def test_missing_formula_cache():
    result = parse([["日期", "姓名", "事项"], ["=DATE(2026,9,7)", NAME, "培训"]])
    assert result.pending and result.warnings
    assert "公式" in result.warnings[0]


def test_conflicting_dates():
    result = parse(
        [["日期", "培训日期", "姓名", "事项"], ["9月7日", "9月8日", NAME, "培训"]]
    )
    assert not result.events and "日期证据相互矛盾" in result.pending[0].warnings


def test_conflicting_times():
    result = parse(
        [
            ["日期", "时间", "开始时间", "姓名", "事项"],
            ["9月7日", "08:00-10:00", "09:00", NAME, "培训"],
        ]
    )
    assert not result.events and "时间证据相互矛盾" in result.pending[0].warnings


def test_repeated_import_idempotent():
    result = parse([["日期", "姓名", "事项"], ["9月7日", NAME, "培训"]])
    assert merge_reports([result, result]).to_dict() == result.to_dict()


def test_one_schedule_is_not_a_global_shift_legend():
    result = parse([["姓名", "9月7日", "9月8日"], [NAME, "夜班 22:00-06:00", "夜班"]])
    assert result.events[0].start == "22:00"
    assert result.events[1].start is None


def test_conflicting_legends_pending():
    result = parse(
        [
            ["姓名", "9月7日"],
            [NAME, "早班"],
            [],
            ["早班：08:00-16:00"],
            ["早班：09:00-17:00"],
        ]
    )
    assert not result.events and result.pending


@pytest.mark.parametrize(
    "rows",
    [
        [["姓名", "9月7日", "地点", "备注"], [NAME, "早班", "服务中心", "带证件"]],
        [["日期", NAME], ["9月7日", "早班"], ["地点", "服务中心"], ["备注", "带证件"]],
    ],
)
def test_matrix_metadata(rows):
    result = parse(rows)
    assert result.events[0].location == "服务中心"
    assert result.events[0].notes == ["带证件"]


def test_different_location_not_deduplicated():
    result = parse(
        [
            ["日期", "姓名", "事项", "地点"],
            ["9月7日", NAME, "培训", "101"],
            ["9月7日", NAME, "培训", "102"],
        ]
    )
    assert len(result.events) == 2
    assert result.conflicts[0]["kind"] == "possible"


def test_notes_merged():
    result = parse(
        [
            ["日期", "姓名", "事项", "备注"],
            ["9月7日", NAME, "培训", "带笔"],
            ["9月7日", NAME, "培训", "带证件"],
        ]
    )
    assert len(result.events) == 1
    assert result.events[0].notes == ["带笔", "带证件"]


def test_overlap_and_adjacency():
    result = parse(
        [
            ["日期", "姓名", "事项", "时间"],
            ["2026-12-31", NAME, "夜班", "22:00-次日06:00"],
            ["2027-01-01", NAME, "培训", "05:00-07:00"],
            ["2027-01-01", NAME, "考试", "07:00-09:00"],
        ]
    )
    assert result.events[0].end_date == "2027-01-01"
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["kind"] == "definite"


def test_sort_unspecified_time_last_and_rest_no_conflict():
    result = parse(
        [
            ["日期", "姓名", "事项", "时间"],
            ["9月7日", NAME, "休息", ""],
            ["9月7日", NAME, "培训", "14:00"],
            ["9月7日", NAME, "考试", "08:00"],
        ]
    )
    assert [e.title for e in result.events] == ["考试", "培训", "休息"]
    assert len(result.conflicts) == 1


@pytest.mark.parametrize("name,year", [("", 2026), ("甲、乙", 2026), (NAME, 1800)])
def test_invalid_query(name, year):
    with pytest.raises(ValueError):
        parse_file(b"a", "a.csv", name, year)

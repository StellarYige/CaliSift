from copy import deepcopy
from scripts.evaluate_accuracy import score_case
from scripts.generate_fixtures import csv_bytes
from xingcheng.parsing import parse_file, matches_name


def event(row, day):
    return dict(
        date=day,
        title="值班",
        start="08:00",
        end="16:00",
        end_date=day,
        location="",
        anchors=[dict(sheet="CSV", name_cell=f"A{row}", evidence={"date": f"B{row}"})],
    )


def test_repeated_titles_are_paired_by_evidence_even_when_reordered():
    expected = [event(2, "2026-09-08"), event(3, "2026-09-09")]
    actual = [{**e, "sources": e["anchors"]} for e in reversed(expected)]
    cells = [dict(sheet="CSV", cell="A2"), dict(sheet="CSV", cell="A3")]
    assert score_case(actual, expected, cells)["correct"] == 2
    actual[0]["date"] = "2026-09-08"
    measured = score_case(actual, expected, cells)
    assert measured["correct"] == 1 and measured["date_correct"] == 1
    wrong_sheet = deepcopy(actual)
    wrong_sheet[0]["sources"][0]["sheet"] = "其他人"
    assert score_case(wrong_sheet, expected, cells)["name_mismatches"] == 1


def test_ambiguous_or_missing_anchors_cannot_receive_accuracy_credit():
    expected = [event(2, "2026-09-08")]
    actual = [{**expected[0], "sources": expected[0]["anchors"]}] * 2
    measured = score_case(actual, expected, [dict(sheet="CSV", cell="A2")])
    assert measured["correct"] == 0 and measured["ambiguous_anchors"] == 1
    del expected[0]["anchors"]
    assert score_case(actual, expected, [])["unanchored"] == 1


def test_explicit_header_format_notes_are_supported_without_relaxing_name_matching():
    rows = [
        [
            "日期（YYYY-MM-DD）",
            "参加人员\n（完整姓名）",
            "起止时间（24小时制）",
            "事项",
        ],
        ["2026-09-08", "星辰奕歌", "08:00-10:00", "消防培训"],
        ["2026-09-09", "星辰奕歌甲", "08:00-10:00", "消防培训"],
    ]
    report = parse_file(csv_bytes(rows), "格式说明.csv", "星辰奕歌", 2026)
    assert [(e.date, e.start, e.end) for e in report.events] == [
        ("2026-09-08", "08:00", "10:00")
    ]
    assert report.events[0].sources[0].name_cell == "B2"
    # Line breaks may separate two people; do not concatenate them into another name.
    assert not matches_name("星辰\n奕歌", "星辰奕歌")

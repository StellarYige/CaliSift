"""Small, hand-specified development corpus. It is not independent acceptance data."""

import json
from pathlib import Path
from scripts.generate_fixtures import csv_bytes

NAME = "星辰奕歌"


def expected(
    day, title, name_cell, date_cell, start=None, end=None, end_date=None, location=""
):
    return dict(
        date=day,
        title=title,
        start=start,
        end=end,
        end_date=end_date,
        location=location,
        anchors=[dict(sheet="CSV", name_cell=name_cell, evidence={"date": date_cell})],
    )


def main():
    destination = Path("tests/fixtures/accuracy")
    destination.mkdir(parents=True, exist_ok=True)
    definitions = [
        (
            "annotated-headers",
            "records",
            [
                [
                    "日期（YYYY-MM-DD）",
                    "参加人员（完整姓名）",
                    "起止时间（24小时制）",
                    "事项",
                ],
                ["2026-09-08", NAME, "08:00-10:00", "消防培训"],
                ["2026-09-09", NAME + "甲", "08:00-10:00", "消防培训"],
            ],
            [
                expected(
                    "2026-09-08", "消防培训", "B2", "A2", "08:00", "10:00", "2026-09-08"
                )
            ],
        ),
        (
            "names-in-rows",
            "names-rows",
            [
                ["姓名", "2026-09-08", "2026-09-09"],
                [NAME, "早班 08:00-16:00", "夜班 22:00-次日06:00"],
                [NAME + "甲", "夜班", "早班"],
            ],
            [
                expected(
                    "2026-09-08", "早班", "A2", "B1", "08:00", "16:00", "2026-09-08"
                ),
                expected(
                    "2026-09-09", "夜班", "A2", "C1", "22:00", "06:00", "2026-09-10"
                ),
            ],
        ),
        (
            "names-in-columns",
            "names-columns",
            [
                ["日期", NAME, NAME + "甲"],
                ["2026-09-08", "早班 08:00-16:00", "夜班"],
                ["2026-09-09", "休息", "早班"],
            ],
            [
                expected(
                    "2026-09-08", "早班", "B1", "A2", "08:00", "16:00", "2026-09-08"
                ),
                expected("2026-09-09", "休息", "B1", "A3"),
            ],
        ),
        (
            "repeated-records",
            "records",
            [
                ["日期", "姓名", "事项", "时间"],
                ["2026-09-08", NAME, "考试", "09:00-11:00"],
                [],
                ["日期", "姓名", "事项", "时间"],
                ["2026-09-09", NAME, "考试", "14:00-16:00"],
            ],
            [
                expected(
                    "2026-09-08", "考试", "B2", "A2", "09:00", "11:00", "2026-09-08"
                ),
                expected(
                    "2026-09-09", "考试", "B5", "A5", "14:00", "16:00", "2026-09-09"
                ),
            ],
        ),
        (
            "start-only-course",
            "records",
            [
                ["上课日期", "课程", "教师", "开始时间", "教室"],
                ["2026-09-08", "数学", NAME, "08:00", "301"],
            ],
            [expected("2026-09-08", "数学", "C2", "A2", "08:00", location="301")],
        ),
    ]
    cases = []
    for identifier, layout, rows, events in definitions:
        (destination / (identifier + ".csv")).write_bytes(csv_bytes(rows))
        cells = sorted({a["name_cell"] for e in events for a in e["anchors"]})
        cases.append(
            dict(
                id=identifier,
                file=identifier + ".csv",
                kind="table",
                layout=layout,
                provenance="synthetic",
                license="Apache-2.0",
                name=NAME,
                year=2026,
                identity_cells=[dict(sheet="CSV", cell=c) for c in cells],
                expected=events,
            )
        )
    (destination / "development.json").write_text(
        json.dumps(
            dict(
                split="development",
                independent_review=False,
                description="Five development cases across three layout families; explicit expected values authored separately from parsing.",
                cases=cases,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

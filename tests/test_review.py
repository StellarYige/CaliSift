from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from scripts.generate_fixtures import NAME, csv_bytes
from xingcheng.aggregate import merge_reports
from xingcheng.api import app
from xingcheng.parsing import parse_file

client = TestClient(app)


@pytest.fixture
def report():
    rows = [
        ["日期", "姓名", "事项", "时间"],
        ["2026-09-07", NAME, "早班", "08:00-16:00"],
        ["2026-09-07", NAME, "演练", "15:00-17:00"],
        ["每周一", NAME, "课程", "14:00"],
        ["每周二", NAME, "课程二", "14:00"],
    ]
    return merge_reports(
        [parse_file(csv_bytes(rows), "安排.csv", NAME, 2026)]
    ).to_dict()


def correct(report, event=None, **values):
    event = event or report["events"][0]
    return client.post(
        "/api/review",
        json={
            "report": report,
            "edits": [
                {
                    "event_id": event["id"],
                    "values": {"date": "2026-09-08", "title": "早班", **values},
                }
            ],
        },
    )


def test_correction_keeps_evidence_original_and_recomputes_conflicts(report):
    original = deepcopy(report)
    assert len(report["conflicts"]) == 1
    response = correct(
        report, start="08:00", end="16:00", location="一楼", notes=[" 带工作证 "]
    )
    assert response.status_code == 200
    result = response.json()
    assert report == original
    assert not result["conflicts"]
    assert [e["date"] for e in result["events"]] == ["2026-09-07", "2026-09-08"]
    event = result["events"][1]
    assert event["sources"] == original["events"][0]["sources"]
    assert event["reviews"][0]["before"]["date"] == "2026-09-07"
    assert event["notes"] == ["带工作证"]
    assert event["end_date"] == "2026-09-08"
    assert event["id"] != original["events"][0]["id"]
    assert result["pending"] == original["pending"]
    assert result["files"] == original["files"]


def test_confirm_pending_only_selected_record_and_keep_warnings_in_history(report):
    pending = report["pending"][0]
    result = correct(
        report, pending, title="确认课程", date="2026-09-07", start="09:00", end="10:00"
    ).json()
    assert len(result["pending"]) == 1
    event = next(e for e in result["events"] if e["title"] == "确认课程")
    assert event["status"] == "confirmed" and not event["warnings"]
    assert event["reviews"][0]["before"]["warnings"] == pending["warnings"]
    assert event["sources"] == pending["sources"]
    assert len(result["conflicts"]) == 2


def test_duplicate_correction_merges_sources_and_audit(report):
    first = report["events"][0]
    second = report["events"][1]
    result = correct(
        report,
        second,
        date=first["date"],
        title=first["title"],
        shift=first["shift"],
        start=first["start"],
        end=first["end"],
    ).json()
    assert len(result["events"]) == 1
    assert len(result["events"][0]["sources"]) == 2
    assert result["events"][0]["reviews"][0]["before"]["title"] == "演练"
    assert not result["conflicts"]
    assert (
        client.post("/api/merge", json={"reports": [result, result]}).json() == result
    )


def test_repeated_edits_keep_non_recursive_history(report):
    first = correct(report, title="第一次").json()
    event = next(e for e in first["events"] if e["title"] == "第一次")
    second = correct(
        first,
        event,
        title="第二次",
        date="2026-09-09",
        start="22:00",
        end="06:00",
        next_day=True,
    ).json()
    event = second["events"][-1]
    assert event["end_date"] == "2026-09-10"
    assert [r["before"]["title"] for r in event["reviews"]] == ["早班", "第一次"]
    assert all("reviews" not in r["before"] for r in event["reviews"])


@pytest.mark.parametrize(
    "values",
    [
        {"date": ""},
        {"date": "2026-02-30"},
        {"title": " "},
        {"start": "24:00"},
        {"end": "10:00"},
        {"start": "10:00", "end": "09:00"},
        {"start": "10:00", "end": "10:00"},
        {"next_day": True},
        {"sources": []},
        {"date": "9999-12-31", "start": "22:00", "end": "06:00", "next_day": True},
    ],
)
def test_invalid_edits_are_rejected(report, values):
    assert correct(report, **values).status_code == 422


def test_stale_duplicate_and_excessive_edits(report):
    assert correct(report, {"id": "stale"}).status_code == 422
    edit = {
        "event_id": report["events"][0]["id"],
        "values": {"date": "2026-09-08", "title": "早班"},
    }
    assert (
        client.post(
            "/api/review", json={"report": report, "edits": [edit, edit]}
        ).status_code
        == 422
    )
    report["events"][1]["id"] = report["events"][0]["id"]
    assert correct(report).status_code == 422
    report["events"].pop()
    report["events"][0]["reviews"] = [{"before": {}}] * 50
    assert correct(report).status_code == 422


def test_no_implicit_end_time_and_body_limit(report):
    result = correct(report, start="14:00").json()
    assert result["events"][-1]["precision"] == "point"
    assert result["events"][-1]["end"] is None
    assert (
        client.post(
            "/api/review",
            content=b"{}",
            headers={"content-length": str(4 * 1024 * 1024 + 1)},
        ).status_code
        == 413
    )


def test_merged_report_above_single_file_limit_can_be_reviewed(report):
    from datetime import date, timedelta

    base = report["events"][0]
    large = {**report, "events": [], "pending": [], "conflicts": []}
    for index in range(2001):
        event = {
            **base,
            "id": str(index),
            "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "title": "休息",
            "shift": "休息",
            "start": None,
            "end": None,
            "end_date": None,
            "precision": "date",
        }
        large["events"].append(event)
    response = correct(large, title="休息", shift="休息", date="2025-12-31")
    assert response.status_code == 200
    assert len(response.json()["events"]) == 2001

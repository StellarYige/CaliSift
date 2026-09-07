"""Apply personal corrections without changing source files or evidence."""

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from .aggregate import merge_reports
from .models import Report


def review_report(report: Report, edits: list[dict]) -> Report:
    result = deepcopy(report)
    records = result.events + result.pending
    by_id = {event.id: event for event in records}
    if len(by_id) != len(records):
        raise ValueError("记录标识重复，请重新整理后修正")
    requested = [edit["event_id"] for edit in edits]
    if len(set(requested)) != len(requested):
        raise ValueError("同一次请求不能重复修正一条记录")
    if any(key not in by_id for key in requested):
        raise ValueError("待修正记录已变化，请返回时间线重新选择")
    for edit in edits:
        event = by_id[edit["event_id"]]
        if len(event.reviews) >= 50:
            raise ValueError("该记录修正次数过多，请重新导入源表")
        before = asdict(event)
        before.pop("reviews")
        event.reviews.append(
            {"edited_at": datetime.now(timezone.utc).isoformat(), "before": before}
        )
        values = edit["values"]
        event.date = values["date"]
        event.title = values["title"].strip()
        event.shift = values.get("shift", "").strip()
        event.location = values.get("location", "").strip()
        event.notes = [note.strip() for note in values.get("notes", []) if note.strip()]
        event.start = values.get("start")
        event.end = values.get("end")
        event.end_date = (
            (
                date.fromisoformat(event.date)
                + timedelta(days=int(values.get("next_day", False)))
            ).isoformat()
            if event.end
            else None
        )
        event.precision = (
            "interval" if event.end else "point" if event.start else "date"
        )
        event.status = "confirmed"
        event.warnings = []  # Original warnings remain in reviews[].before.
    result.events = [event for event in records if event.status == "confirmed"]
    result.pending = [event for event in records if event.status == "pending"]
    return merge_reports([result])

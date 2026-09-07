from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .models import Event, Report, stable_id
from .parsing import REST


def _key(event: Event):
    return (
        event.date,
        event.start,
        event.end,
        event.end_date,
        event.precision,
        event.title.strip(),
        event.shift.strip(),
        event.location.strip(),
    )


def _unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def merge_reports(reports: list[Report]) -> Report:
    result = Report()
    events = {}
    pending = {}
    for report in reports:
        result.files.extend(deepcopy(report.files))
        result.warnings.extend(report.warnings)
        for original in report.events:
            event = deepcopy(original)
            key = _key(event)
            event.id = stable_id(key)
            if key in events:
                saved = events[key]
                saved.sources = _unique(saved.sources + event.sources)
                saved.notes = _unique(saved.notes + event.notes)
                saved.warnings = _unique(saved.warnings + event.warnings)
                saved.reviews = _unique(saved.reviews + event.reviews)
            else:
                events[key] = event
        for event in report.pending:
            pending.setdefault(event.id, deepcopy(event))
    result.events = sorted(
        events.values(),
        key=lambda e: (e.date or "9999", e.start is None, e.start or "", e.title, e.id),
    )
    result.pending = sorted(pending.values(), key=lambda e: (e.date or "9999", e.id))
    result.files = _unique(result.files)
    result.warnings = _unique(result.warnings)
    result.conflicts = detect_conflicts(result.events)
    return result


def detect_conflicts(events: list[Event]) -> list[dict]:
    conflicts = []
    eligible = sorted(
        [e for e in events if e.date and e.shift not in REST and e.title not in REST],
        key=lambda e: e.date,
    )
    for i, a in enumerate(eligible):
        for b in eligible[i + 1 :]:
            if b.date > (a.end_date or a.date):
                break
            if len(conflicts) >= 5000:
                return conflicts
            if a.precision == b.precision == "interval":
                a0 = datetime.fromisoformat(f"{a.date}T{a.start}")
                a1 = datetime.fromisoformat(f"{a.end_date or a.date}T{a.end}")
                b0 = datetime.fromisoformat(f"{b.date}T{b.start}")
                b1 = datetime.fromisoformat(f"{b.end_date or b.date}T{b.end}")
                overlap = max(a0, b0) < min(a1, b1)
                kind = "definite"
            else:
                a_last = a.end_date or a.date
                b_last = b.end_date or b.date
                overlap = max(a.date, b.date) <= min(a_last, b_last)
                kind = "possible"
            if overlap:
                conflicts.append(
                    {
                        "event_ids": [a.id, b.id],
                        "kind": kind,
                        "message": (
                            "时间冲突"
                            if kind == "definite"
                            else "可能重叠：有安排未注明完整时间"
                        ),
                    }
                )
    return conflicts

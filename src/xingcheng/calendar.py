"""Stateless personal calendar transactions. Content hashes are never event identities."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import re
from uuid import uuid4

from .aggregate import detect_conflicts
from .models import Event, Source, stable_id

FIELDS = (
    "date",
    "title",
    "shift",
    "start",
    "end",
    "end_date",
    "precision",
    "location",
    "status",
    "category",
    "all_day",
)
EDITABLE = set(FIELDS) | {"notes"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identity():
    return str(uuid4())


def empty_calendar(person_name):
    return dict(
        schema=2,
        version=0,
        personName=person_name,
        sources=[],
        events=[],
        settings={},
        undo=None,
    )


def normalized(value):
    from .contracts import EventInput

    value = deepcopy(value)
    extras = {
        k: value.pop(k) for k in ("category", "all_day", "field_basis") if k in value
    }
    value.setdefault(
        "precision",
        "interval" if value.get("end") else "point" if value.get("start") else "date",
    )
    value.setdefault("status", "confirmed" if value.get("date") else "pending")
    value.setdefault("sources", [])
    checked = EventInput.model_validate(value).model_dump()
    if not checked["title"].strip():
        raise ValueError("请填写事项名称")
    checked.update(extras)
    checked.setdefault("category", "其他")
    checked.setdefault("all_day", False)
    if (
        not isinstance(checked["all_day"], bool)
        or not isinstance(checked["category"], str)
        or len(checked["category"]) > 40
    ):
        raise ValueError("分类或全天设置无效")
    if checked["all_day"] and checked.get("start"):
        raise ValueError("全天安排不能同时填写时间")
    return checked


def effective(event):
    base = deepcopy(
        event["contributions"][0]["value"] if event["contributions"] else event["base"]
    )
    base.update(deepcopy(event.get("overrides", {})))
    base = normalized(base)
    base.update(id=event["id"], sequence=event["sequence"], hidden=event["hidden"])
    base["sources"] = []
    for contribution in event["contributions"]:
        for evidence in contribution["value"].get("sources", []):
            if evidence not in base["sources"]:
                base["sources"].append(deepcopy(evidence))
    base["field_basis"] = {
        k: (
            "手动修正"
            if k in event["overrides"]
            else base.get("field_basis", {}).get(k, "原表")
        )
        for k in FIELDS
    }
    base["reviews"] = deepcopy(event.get("history", []))
    return base


def content_key(value):
    return stable_id([value.get(k) for k in FIELDS] + [value.get("notes", [])])


def validate_calendar(calendar):
    if (
        calendar.get("schema") != 2
        or not isinstance(calendar.get("version"), int)
        or calendar["version"] < 0
    ):
        raise ValueError("日历版本无效")
    if (
        not isinstance(calendar.get("personName"), str)
        or not calendar["personName"].strip()
        or len(calendar["personName"]) > 80
    ):
        raise ValueError("请填写日历姓名")
    events, sources = calendar["events"], calendar["sources"]
    if sum(not e.get("archived", False) for e in events) > 5000 or len(sources) > 100:
        raise ValueError("本机上限为 5000 条安排、100 个来源，请先备份并清理")
    source_ids = {s["id"] for s in sources}
    if len(source_ids) != len(sources) or len({e["id"] for e in events}) != len(events):
        raise ValueError("日历存在重复身份")
    for source in sources:
        if not source.get("name") or len(source.get("revisions", [])) > 3:
            raise ValueError("来源名称或版本数量无效")
    for event in events:
        if (
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", event["id"])
            or not isinstance(event["sequence"], int)
            or event["sequence"] < 0
        ):
            raise ValueError("日程身份或修订序号无效")
        if set(event.get("overrides", {})) - EDITABLE:
            raise ValueError("个人修正包含不支持的字段")
        normalized(event["base"])
        seen = set()
        for contribution in event["contributions"]:
            if (
                contribution["source_id"] not in source_ids
                or contribution["source_id"] in seen
            ):
                raise ValueError("日程来源关联无效")
            seen.add(contribution["source_id"])
            normalized(contribution["value"])
        effective(event)
    return calendar


def report_for(calendar):
    values = [
        effective(e)
        for e in calendar["events"]
        if not e["hidden"] and not e.get("cancelled") and not e.get("archived")
    ]
    events = sorted(
        [e for e in values if e["status"] == "confirmed"],
        key=lambda e: (e["date"], e["start"] or "99", e["title"]),
    )
    pending = [e for e in values if e["status"] == "pending"]
    objects = [
        Event(
            **{
                k: v
                for k, v in e.items()
                if k in Event.__dataclass_fields__ and k != "sources"
            },
            sources=[Source(**s) for s in e["sources"]],
        )
        for e in events
    ]
    return dict(
        events=events,
        pending=pending,
        conflicts=detect_conflicts(objects),
        warnings=[],
        files=[
            f
            for s in calendar["sources"]
            for r in s["revisions"][-1:]
            for f in r["report"].get("files", [])
        ],
    )


def new_event(value, contribution=None, rules=None):
    history = deepcopy(value.get("reviews", []))
    original = normalized(history[0]["before"]) if history else deepcopy(value)
    overrides = (
        {
            k: deepcopy(value[k])
            for k in EDITABLE
            if k in value and value.get(k) != original.get(k)
        }
        if history
        else {}
    )
    if contribution and history:
        contribution["raw"] = deepcopy(original)
        from .rules import apply_rules

        contribution["value"] = apply_rules(original, rules or {})
        manual_value = normalized(value["reviews"][-1].get("after", value))
        overrides = {
            k: deepcopy(manual_value[k])
            for k in EDITABLE
            if k in manual_value and manual_value.get(k) != contribution["value"].get(k)
        }
    return dict(
        id=identity(),
        sequence=len(history),
        base=original,
        contributions=[contribution] if contribution else [],
        overrides=overrides,
        hidden=False,
        cancelled=False,
        history=history,
        modified_at=now(),
    )


def _changes(before, after):
    labels = {
        "date": "改日期",
        "start": "改时间",
        "end": "改时间",
        "end_date": "改时间",
        "location": "改地点",
        "title": "改事项",
    }
    return list(
        dict.fromkeys(
            labels.get(k, "字段变化") for k in FIELDS if before.get(k) != after.get(k)
        )
    )


def transform(current, expected_version, operation):
    validate_calendar(current)
    if current["version"] != expected_version:
        raise ValueError("日历已变化，请重新预览")
    candidate = deepcopy(current)
    summary = dict(
        added=[],
        cancelled=[],
        changed=[],
        duplicates=0,
        unresolved=[],
        correction_conflicts=[],
        warnings=[],
    )
    kind = operation["type"]
    if kind in ("append", "update"):
        _import(candidate, operation, summary)
    elif kind in ("edit", "hide", "restore"):
        ids = operation.get("event_ids") or [operation.get("event_id")]
        if len(ids) > 5000 or len(ids) != len(set(ids)):
            raise ValueError("请选择有效的安排")
        selected = [e for e in candidate["events"] if e["id"] in ids]
        if len(selected) != len(ids):
            raise ValueError("安排已变化，请重新选择")
        for event in selected:
            before = effective(event)
            if kind == "edit":
                values = operation["values"]
                if set(values) - EDITABLE:
                    raise ValueError("修正字段无效")
                event["overrides"].update(values)
                effective(event)
                event["history"] = (
                    event["history"]
                    + [
                        dict(
                            before={k: v for k, v in before.items() if k != "reviews"},
                            edited_at=now(),
                        )
                    ]
                )[-50:]
            else:
                event["hidden"] = kind == "hide"
            event["sequence"] += 1
            event["modified_at"] = now()
            summary["changed"].append(
                dict(id=event["id"], before=before, after=effective(event))
            )
    elif kind == "manual":
        value = normalized(operation["values"])
        event = new_event(value)
        event["overrides"] = {k: value[k] for k in EDITABLE if k in value}
        candidate["events"].append(event)
        summary["added"].append(effective(event))
    elif kind == "settings":
        candidate["settings"] = deepcopy(operation["settings"])
    elif kind == "source_config":
        source = next(
            (s for s in candidate["sources"] if s["id"] == operation["source_id"]), None
        )
        if not source:
            raise ValueError("请选择来源")
        from .rules import validate_rules, apply_rules

        rules = validate_rules(operation.get("rules", {}))
        source["rules"] = rules
        if operation.get("name"):
            source["name"] = operation["name"][:100]
        if operation.get("apply"):
            for event in list(candidate["events"]):
                before = effective(event)
                contribution = next(
                    (
                        c
                        for c in event["contributions"]
                        if c["source_id"] == source["id"]
                    ),
                    None,
                )
                if contribution and len(event["contributions"]) > 1:
                    next_value = apply_rules(
                        contribution.get("raw", contribution["value"]), rules
                    )
                    if any(
                        content_key(c["value"]) != content_key(next_value)
                        for c in event["contributions"]
                        if c["source_id"] != source["id"]
                    ):
                        branch = deepcopy(event)
                        branch.update(
                            id=identity(),
                            sequence=0,
                            contributions=[deepcopy(contribution)],
                        )
                        event["contributions"] = [
                            c
                            for c in event["contributions"]
                            if c["source_id"] != source["id"]
                        ]
                        candidate["events"].append(branch)
                        event = branch
                for c in event["contributions"]:
                    if c["source_id"] == source["id"]:
                        c["value"] = apply_rules(c.get("raw", c["value"]), rules)
                after = effective(event)
                if content_key(before) != content_key(after):
                    event["sequence"] += 1
                    summary["changed"].append(
                        dict(id=event["id"], before=before, after=after)
                    )
    elif kind == "undo":
        undo = candidate.get("undo")
        if not undo:
            raise ValueError("没有可撤销的来源更新")
        sid = undo["source_id"]
        source = next(s for s in candidate["sources"] if s["id"] == sid)
        if source["revisions"][-1]["id"] != undo["revision_id"]:
            raise ValueError("该来源又有新导入，无法撤销旧更新，请核对来源版本")
        prior = {e["id"]: e for e in undo["before"]["events"]}
        after = undo.get("after_overrides", {})
        for e in candidate["events"]:
            old = prior.get(e["id"])
            old_contributions = (
                [c for c in old["contributions"] if c["source_id"] == sid]
                if old
                else []
            )
            current_contributions = [
                c for c in e["contributions"] if c["source_id"] == sid
            ]
            if not old_contributions and not current_contributions:
                continue
            e["contributions"] = [
                c for c in e["contributions"] if c["source_id"] != sid
            ] + deepcopy(old_contributions)
            e["cancelled"] = not e["contributions"]
            if old and e["overrides"] == after.get(e["id"]):
                e["overrides"] = deepcopy(old["overrides"])
            e["sequence"] += 1
        source["revisions"] = deepcopy(
            next(s for s in undo["before"]["sources"] if s["id"] == sid)["revisions"]
        )
        candidate["undo"] = None
        summary["warnings"].append("已撤销最近一次来源更新")
    else:
        raise ValueError("不支持的日历操作")
    candidate["version"] = current["version"] + 1
    if kind == "update" and candidate.get("undo"):
        candidate["undo"]["after_overrides"] = {
            e["id"]: deepcopy(e["overrides"]) for e in candidate["events"]
        }
    validate_calendar(candidate)
    return dict(
        base_version=current["version"],
        calendar=candidate,
        summary=summary,
        report=report_for(candidate),
    )


def _import(calendar, op, summary):
    from .rules import apply_rules

    incoming = op["report"]
    raw_values = incoming.get("events", []) + incoming.get("pending", [])
    if len(raw_values) > 5000 or len(incoming.get("files", [])) > 10:
        raise ValueError("单批最多 10 份文件、5000 项安排")
    source = next(
        (s for s in calendar["sources"] if s["id"] == op.get("source_id")), None
    )
    updating = op["type"] == "update"
    if updating and not source:
        raise ValueError("更新时必须选择已有来源")
    if not source:
        from .rules import validate_rules

        source = dict(
            id=identity(),
            name=(op.get("source_name") or "新来源")[:100],
            revisions=[],
            rules=validate_rules(op.get("rules", {})),
        )
        calendar["sources"].append(source)
    source_id = source["id"]
    revision_id = identity()
    values = [apply_rules(normalized(v), source.get("rules", {})) for v in raw_values]
    old = [
        e
        for e in calendar["events"]
        if any(c["source_id"] == source_id for c in e["contributions"])
    ]
    old_by_id = {e["id"]: e for e in old}
    mappings = op.get(
        "mappings", {}
    )  # draft index -> stable event ID; user-confirmed only
    if len(set(mappings.values())) != len(mappings):
        raise ValueError("同一旧安排不能对应多条新版记录")
    coverage = op.get("coverage")
    if updating:
        if (
            not coverage
            or len(coverage) != 2
            or date.fromisoformat(coverage[0]) > date.fromisoformat(coverage[1])
        ):
            raise ValueError("更新前请明确覆盖日期范围")
        for value in values:
            if value["date"] and not coverage[0] <= value["date"] <= coverage[1]:
                raise ValueError("新安排超出覆盖日期范围，请扩大范围或改为追加")
        before = deepcopy(calendar)
        before["undo"] = None
        calendar["undo"] = dict(
            version=calendar["version"] + 1,
            before=before,
            source_id=source_id,
            revision_id=revision_id,
        )
    matched = set()
    old_by_key = {}
    current_by_key = {}
    for event in old:
        for contribution in event["contributions"]:
            if contribution["source_id"] == source_id:
                old_by_key.setdefault(content_key(contribution["value"]), []).append(
                    event
                )
    for event in calendar["events"]:
        if not event.get("cancelled"):
            current_by_key.setdefault(content_key(effective(event)), []).append(event)
    for index, value in enumerate(values):
        value_key = content_key(value)
        target = None
        if str(index) in mappings:
            target = old_by_id.get(mappings[str(index)])
            if not target or (
                updating
                and not coverage[0]
                <= (
                    next(
                        c["value"]
                        for c in target["contributions"]
                        if c["source_id"] == source_id
                    ).get("date")
                    or ""
                )
                <= coverage[1]
            ):
                raise ValueError("变更对应关系无效或超出范围")
        else:
            target = next(
                (e for e in old_by_key.get(value_key, []) if e["id"] not in matched),
                None,
            )
        if target is None:
            target = next(
                (
                    e
                    for e in current_by_key.get(value_key, [])
                    if not e.get("cancelled")
                ),
                None,
            )
        contribution = dict(
            source_id=source_id,
            revision_id=revision_id,
            value=deepcopy(value),
            raw=normalized(raw_values[index]),
        )
        if target:
            before_value = effective(target)
            correction_id = target["id"]
            previous_contribution = next(
                (c for c in target["contributions"] if c["source_id"] == source_id),
                None,
            )
            changed = previous_contribution and content_key(
                previous_contribution["value"]
            ) != content_key(value)
            if changed and any(
                c["source_id"] != source_id
                and content_key(c["value"]) != content_key(value)
                for c in target["contributions"]
            ):
                # Divergent contributions become separate events: the other source still supports the old arrangement.
                original = target
                target = deepcopy(original)
                target.update(
                    id=identity(),
                    sequence=0,
                    contributions=[deepcopy(previous_contribution)],
                )
                original["contributions"] = [
                    c for c in original["contributions"] if c["source_id"] != source_id
                ]
                matched.add(original["id"])
                calendar["events"].append(target)
            conflicts = [
                k
                for k in target["overrides"]
                if previous_contribution
                and previous_contribution["value"].get(k) != value.get(k)
                and target["overrides"][k] != value.get(k)
            ]
            if conflicts:
                summary["correction_conflicts"].append(
                    dict(id=correction_id, fields=conflicts)
                )
                choice = op.get("correction_choices", {}).get(correction_id)
                if choice == "new":
                    for field in conflicts:
                        target["overrides"].pop(field, None)
                elif choice != "keep":
                    summary["unresolved"].append(
                        dict(id=correction_id, reason="请选择保留个人修正或采用新版")
                    )
            target["contributions"] = [
                c for c in target["contributions"] if c["source_id"] != source_id
            ] + [contribution]
            target["cancelled"] = False
            matched.add(target["id"])
            after_value = effective(target)
            old_key, next_key = content_key(before_value), content_key(after_value)
            if old_key != next_key:
                current_by_key[old_key] = [
                    e
                    for e in current_by_key.get(old_key, [])
                    if e["id"] != target["id"]
                ]
            current_by_key.setdefault(next_key, []).append(target)
            if changed or content_key(before_value) != content_key(after_value):
                target["sequence"] += 1
                summary["changed"].append(
                    dict(
                        id=target["id"],
                        before=before_value,
                        after=after_value,
                        kinds=_changes(before_value, after_value),
                    )
                )
            else:
                summary["duplicates"] += 1
        else:
            target = new_event(value, contribution, source.get("rules", {}))
            calendar["events"].append(target)
            matched.add(target["id"])
            summary["added"].append(dict(**effective(target), draft_index=index))
            current_by_key.setdefault(content_key(effective(target)), []).append(target)
    if updating:
        complete = (
            bool(values)
            and not incoming.get("pending")
            and all(f.get("status") == "ok" for f in incoming.get("files", []))
        )
        complete = complete and any(
            s.get("name_matches", 0) > 0
            for f in incoming.get("files", [])
            for s in f.get("sheets", [])
        )
        complete = (
            complete
            and not incoming.get("warnings")
            and all(
                not s.get("pending") and not s.get("warnings")
                for f in incoming.get("files", [])
                for s in f.get("sheets", [])
            )
        )
        missing = [
            e
            for e in old
            if e["id"] not in matched
            and any(
                c["source_id"] == source_id
                and coverage[0] <= (c["value"].get("date") or "") <= coverage[1]
                for c in e["contributions"]
            )
        ]
        if missing and not complete:
            summary["warnings"].append(
                "新版为空、未匹配姓名或解析不完整，已保留旧安排，不自动取消"
            )
        elif missing:
            for event in missing:
                previous = effective(event)
                summary["cancelled"].append(previous)
                # Every unmatched old record must be explicitly acknowledged as a cancellation.
                if event["id"] not in op.get("cancel_ids", []):
                    summary["unresolved"].append(
                        dict(
                            id=event["id"], reason="无法可靠关联，请对应新版或确认取消"
                        )
                    )
                event["contributions"] = [
                    c for c in event["contributions"] if c["source_id"] != source_id
                ]
                event["cancelled"] = not event["contributions"]
                event["sequence"] += 1
    source["revisions"] = (
        source["revisions"]
        + [
            dict(
                id=revision_id,
                imported_at=now(),
                coverage=coverage,
                report=deepcopy(incoming),
            )
        ]
    )[-3:]


def export_ics(calendar, options):
    validate_calendar(calendar)
    alarm = options.get("alarm", 0)
    for key in ("from", "to"):
        if options.get(key):
            date.fromisoformat(options[key])
    if options.get("from") and options.get("to") and options["from"] > options["to"]:
        raise ValueError("导出开始日期不能晚于结束日期")
    if alarm not in (0, 15, 30, 60, 1440):
        raise ValueError("提醒时间无效")

    def escape(value):
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CaliSift//Personal Calendar 0.3//ZH",
        "CALSCALE:GREGORIAN",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for record in calendar["events"]:
        e = effective(record)
        if (
            record["hidden"]
            or record.get("cancelled")
            or record.get("archived")
            or e["status"] != "confirmed"
        ):
            continue
        if (
            options.get("from")
            and e["date"] < options["from"]
            or options.get("to")
            and e["date"] > options["to"]
        ):
            continue
        if options.get("category") and e["category"] != options["category"]:
            continue
        if options.get("source_id") and not any(
            c["source_id"] == options["source_id"] for c in record["contributions"]
        ):
            continue
        if not e["start"] and not e["all_day"]:
            raise ValueError(f"{e['date']} {e['title']}：请补全时间或明确设为全天")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@xingcheng.local",
            f"SEQUENCE:{e['sequence']}",
            f"DTSTAMP:{stamp}",
        ]
        day = e["date"].replace("-", "")
        if e["all_day"]:
            end = (date.fromisoformat(e["date"]) + timedelta(days=1)).strftime("%Y%m%d")
            lines += [f"DTSTART;VALUE=DATE:{day}", f"DTEND;VALUE=DATE:{end}"]
        else:
            lines += [
                f"DTSTART;TZID=Asia/Shanghai:{day}T{e['start'].replace(':', '')}00"
            ]
            if e["end"]:
                lines += [
                    f"DTEND;TZID=Asia/Shanghai:{(e['end_date'] or e['date']).replace('-', '')}T{e['end'].replace(':', '')}00"
                ]
        sources = "、".join(
            s["name"]
            for s in calendar["sources"]
            if any(c["source_id"] == s["id"] for c in record["contributions"])
        )
        description = "\n".join(e["notes"] + ["来源：" + (sources or "手动新增")])
        lines += [
            f"SUMMARY:{escape(e['title'])}",
            f"LOCATION:{escape(e['location'])}",
            f"DESCRIPTION:{escape(description)}",
            f"CATEGORIES:{escape(e['category'])}",
        ]
        if alarm:
            lines += [
                "BEGIN:VALARM",
                f"TRIGGER:-PT{alarm}M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape(e['title'])}",
                "END:VALARM",
            ]
        lines += ["END:VEVENT"]
    lines += ["END:VCALENDAR"]
    folded = []
    for line in lines:
        chunk = ""
        for char in line:
            if len((chunk + char).encode("utf-8")) > 75:
                folded.append(chunk)
                chunk = " "
            chunk += char
        folded.append(chunk)
    return "\r\n".join(folded) + "\r\n"

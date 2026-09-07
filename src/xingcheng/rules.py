"""Explicit source-scoped rules and semester expansion; never infer holidays."""

from copy import deepcopy
from datetime import date, timedelta
import re


def clock(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", value
    ):
        raise ValueError("时间应为 HH:MM")
    return value


def validate_rules(rules):
    if not isinstance(rules, dict) or set(rules) - {"shifts", "semester", "template"}:
        raise ValueError("规则配置无效")
    shifts = rules.get("shifts", [])
    if not isinstance(shifts, list) or len(shifts) > 100:
        raise ValueError("最多配置 100 个班次")
    aliases = set()
    for shift in shifts:
        if not isinstance(shift, dict) or set(shift) - {
            "name",
            "aliases",
            "start",
            "end",
            "next_day",
        }:
            raise ValueError("班次模板包含不支持的字段")
        if (
            not isinstance(shift.get("name"), str)
            or len(shift["name"]) > 100
            or not isinstance(shift.get("aliases"), list)
            or len(shift["aliases"]) > 100
        ):
            raise ValueError("请填写有效的班次名称和符号列表")
        if "next_day" in shift and not isinstance(shift["next_day"], bool):
            raise ValueError("次日结束应为明确的开关设置")
        if not shift.get("name") or not shift.get("aliases"):
            raise ValueError("请填写班次名称和符号")
        for alias in shift["aliases"]:
            if (
                not isinstance(alias, str)
                or not alias.strip()
                or len(alias) > 100
                or alias in aliases
            ):
                raise ValueError("班次符号重复或为空")
            aliases.add(alias)
        clock(shift["start"])
        clock(shift["end"])
        if not shift.get("next_day") and shift["end"] <= shift["start"]:
            raise ValueError("跨夜班次请设置次日结束")
    semester = rules.get("semester")
    if semester:
        if (
            not isinstance(semester, dict)
            or set(semester) - {"monday", "weeks", "periods"}
            or not isinstance(semester.get("periods"), list)
        ):
            raise ValueError("学期模板格式无效")
        if date.fromisoformat(semester["monday"]).weekday() != 0:
            raise ValueError("第一教学周必须选择周一")
        if not isinstance(semester["weeks"], int) or not 1 <= semester["weeks"] <= 60:
            raise ValueError("学期周数应在 1–60 之间")
        for slot in semester["periods"]:
            if not isinstance(slot, dict) or set(slot) != {"start", "end"}:
                raise ValueError("节次仅包含开始和结束时间")
            clock(slot["start"])
            clock(slot["end"])
            if slot["end"] <= slot["start"]:
                raise ValueError("节次结束时间必须晚于开始时间")
        if not 1 <= len(semester["periods"]) <= 30:
            raise ValueError("请设置 1–30 个节次")
        if any(
            b["start"] < a["end"]
            for a, b in zip(semester["periods"], semester["periods"][1:])
        ):
            raise ValueError("节次必须按时间排序且不重叠")
    template = rules.get("template")
    if template:
        if not isinstance(template, dict) or set(template) - {
            "layout",
            "sheet",
            "header_row",
            "headers",
            "mapping",
        }:
            raise ValueError("表格模板包含不支持的字段")
        if template.get("layout") not in ("records", "names_rows", "names_columns"):
            raise ValueError("模板布局无效")
        if (
            not isinstance(template.get("header_row"), int)
            or template["header_row"] < 0
        ):
            raise ValueError("请指定表头行")
        if not template.get("headers") or not isinstance(template.get("mapping"), dict):
            raise ValueError("请保存表头特征和字段映射")
        if not isinstance(template["headers"], list) or any(
            not isinstance(h, str) for h in template["headers"]
        ):
            raise ValueError("表头必须是文字列表")
        fields = {
            "name",
            "date",
            "title",
            "shift",
            "start",
            "end",
            "time",
            "location",
            "note",
        }
        if set(template["mapping"]) - fields or any(
            not isinstance(v, int) or v < 0 for v in template["mapping"].values()
        ):
            raise ValueError("字段映射必须使用有效的行列位置")
    return deepcopy(rules)


def apply_rules(value, rules):
    validate_rules(rules)
    result = deepcopy(value)
    # Original times always take precedence, including an explicit start-only time.
    if result.get("start") or not result.get("date"):
        return result
    alias = result.get("shift") or result.get("title")
    rule = next((s for s in rules.get("shifts", []) if alias in s["aliases"]), None)
    if rule:
        result.update(
            start=rule["start"],
            end=rule["end"],
            precision="interval",
            end_date=(
                date.fromisoformat(result["date"])
                + timedelta(days=int(bool(rule.get("next_day"))))
            ).isoformat(),
        )
        result.setdefault("field_basis", {}).update(
            {k: "个人规则：" + rule["name"] for k in ("start", "end", "end_date")}
        )
    return result


def expand_course(course, semester):
    validate_rules({"semester": semester})
    weekday = course["weekday"]
    periods = course["periods"]
    if (
        not isinstance(weekday, int)
        or not 1 <= weekday <= 7
        or not periods
        or periods != list(range(min(periods), max(periods) + 1))
    ):
        raise ValueError("请选择星期和连续节次")
    if min(periods) < 1 or max(periods) > len(semester["periods"]):
        raise ValueError("节次超出配置范围")
    weeks = course.get("weeks") or list(
        range(course.get("week_from", 1), course.get("week_to", semester["weeks"]) + 1)
    )
    if (
        not weeks
        or not isinstance(course.get("title"), str)
        or not course["title"].strip()
    ):
        raise ValueError("请填写课程名称和有效周次")
    if any(not isinstance(w, int) or not 1 <= w <= semester["weeks"] for w in weeks):
        raise ValueError("周次超出学期范围")
    parity = course.get("parity", "all")
    if parity not in ("all", "odd", "even"):
        raise ValueError("单双周设置无效")
    from .calendar import normalized

    events = []
    for week in sorted(set(weeks)):
        if parity == "odd" and week % 2 == 0 or parity == "even" and week % 2 == 1:
            continue
        day = (
            date.fromisoformat(semester["monday"])
            + timedelta(weeks=week - 1, days=weekday - 1)
        ).isoformat()
        events.append(
            normalized(
                dict(
                    date=day,
                    title=course["title"],
                    location=course.get("location", ""),
                    category="学习",
                    start=semester["periods"][min(periods) - 1]["start"],
                    end=semester["periods"][max(periods) - 1]["end"],
                    end_date=day,
                    sources=course.get("sources", []),
                    notes=[f"第 {week} 教学周"],
                    field_basis={k: "个人课程规则" for k in ("date", "start", "end")},
                )
            )
        )
    return dict(events=events, pending=[], files=[], warnings=[], conflicts=[])

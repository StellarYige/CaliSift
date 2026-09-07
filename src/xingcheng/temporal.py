from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from .readers import text

CN = "零〇一二三四五六七八九十两"


def chinese_number(value: str) -> int:
    digits = {char: n for n, char in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if value.isdigit():
        return int(value)
    if "十" in value:
        left, right = value.split("十", 1)
        return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
    return int("".join(str(digits[x]) for x in value))


def numeric_chinese(value: str) -> str:
    return re.sub(
        rf"([{CN}]+)(?=[年月日号点时])", lambda m: str(chinese_number(m[1])), value
    )


@dataclass
class Context:
    year: int
    month: int | None = None
    year_explicit: bool = False
    ambiguous: bool = False


def infer_context(labels: list[str], reference_year: int) -> Context:
    """Labels ordered from closest (table title) to farthest (file name)."""
    year, month = None, None
    for label in labels:
        value = numeric_chinese(text(label))
        years = set(
            int(x)
            for x in re.findall(r"(?<!\d)((?:19|20|21)\d{2})(?:年|[-/.]|\b)", value)
        )
        months = set(int(x) for x in re.findall(r"(?<!\d)(1[0-2]|0?[1-9])月", value))
        ym = re.search(r"(?:19|20|21)\d{2}[-/.](1[0-2]|0?[1-9])(?:[-/.]|\b)", value)
        if ym:
            months.add(int(ym[1]))
        if (year is None and len(years) > 1) or (month is None and len(months) > 1):
            return Context(year or reference_year, month, year is not None, True)
        if year is None and years:
            year = years.pop()
        if month is None and months:
            month = months.pop()
    return Context(year or reference_year, month, year is not None)


def parse_date(
    value, context: Context, allow_day: bool = False
) -> tuple[date | None, list[str]]:
    if isinstance(value, datetime):
        return value.date(), []
    if isinstance(value, date):
        return value, []
    s = numeric_chinese(text(value))
    if not s:
        return None, []
    date_mentions = re.findall(r"(?:\d{4}[年/.-])?\d{1,2}[月/.-]\d{1,2}(?:日|号)?", s)
    if len(set(date_mentions)) > 1:
        return None, ["一个单元格包含多个日期，需确认"]
    y, m, d = None, None, None
    full = re.search(
        r"(?<!\d)((?:19|20|21)\d{2})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})(?:日|号)?(?!\d)",
        s,
    )
    md = re.search(r"(?<![\d/.-])(\d{1,2})\s*[月/.-]\s*(\d{1,2})(?:日|号)?(?!\d)", s)
    day_only = re.fullmatch(
        r"(\d{1,2})(?:日|号)?(?:\s*[（(]?(?:周|星期)[一二三四五六日天][）)]?)?", s
    )
    if full:
        y, m, d = map(int, full.groups())
    elif md:
        m, d = map(int, md.groups())
    elif allow_day and day_only:
        d = int(day_only[1])
        m = context.month
    else:
        return None, []
    if context.ambiguous and y is None:
        return None, ["日期上下文存在多个年份或月份"]
    if m is None:
        return None, ["日期缺少月份"]
    warnings = []
    if y is None:
        y = context.year
        if not context.year_explicit:
            warnings.append(f"年份按补全年份 {y} 填入")
    try:
        return date(y, m, d), warnings
    except ValueError:
        return None, [f"无效日期：{s}"]


@dataclass
class TimeValue:
    start: str | None = None
    end: str | None = None
    next_day: bool = False
    warning: str | None = None


def parse_time(value) -> TimeValue:
    if isinstance(value, datetime):
        # Excel date-only cells are datetime at midnight: do not fabricate 00:00.
        return (
            TimeValue(value.strftime("%H:%M"))
            if value.time() != time()
            else TimeValue()
        )
    if isinstance(value, time):
        return TimeValue(value.strftime("%H:%M"))
    if (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and 0 <= value < 1
    ):
        minutes = round(value * 24 * 60)
        return TimeValue(f"{minutes // 60:02}:{minutes % 60:02}")
    s = numeric_chinese(text(value)).replace("：", ":")
    if not s:
        return TimeValue()
    pattern = r"(上午|下午|晚上|中午|凌晨)?\s*(\d{1,2})(?::(\d{1,2})|[点时](?:(\d{1,2})分?|(半))?)"
    matches = list(re.finditer(pattern, s))
    if not matches:
        # Bare hours accepted only as an explicit hour range, never as dates.
        m = re.fullmatch(r"\s*(\d{1,2})\s*[-—–~～至到]\s*(\d{1,2})\s*(?:时|点)?\s*", s)
        if m:
            h1, h2 = map(int, m.groups())
            if h1 < 24 and h2 <= 24:
                end = "00:00" if h2 == 24 else f"{h2:02}:00"
                return TimeValue(f"{h1:02}:00", end, h2 == 24 or h2 < h1)
        return TimeValue()
    if len(matches) > 2:
        return TimeValue(warning="一个单元格包含多个时间段，需确认")
    times = []
    previous_period = None
    midnight_end = False
    for i, match in enumerate(matches):
        period, hour, minute, chinese_minute, half = match.groups()
        h, mins = int(hour), int(minute or chinese_minute or (30 if half else 0))
        period = period or previous_period
        previous_period = period
        if period in ("下午", "晚上", "中午") and h < 12:
            h += 12
        elif period in ("上午", "凌晨") and h == 12:
            h = 0
        if h == 24 and mins == 0 and i == 1:
            h, midnight_end = 0, True
        if not 0 <= h < 24 or not 0 <= mins < 60:
            return TimeValue(warning="时间超出有效范围")
        times.append(f"{h:02}:{mins:02}")
    if len(times) == 1:
        return TimeValue(times[0])
    between = s[matches[0].end() : matches[1].start()]
    if not re.search(r"[-—–~～至到]", between):
        return TimeValue(warning="时间之间缺少明确区间关系")
    if times[0] == times[1] and not midnight_end and "次日" not in between:
        return TimeValue(warning="起止时间相同，区间关系需确认")
    return TimeValue(
        times[0], times[1], midnight_end or "次日" in between or times[1] < times[0]
    )

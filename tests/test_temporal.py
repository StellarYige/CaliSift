from datetime import time
import pytest
from xingcheng.temporal import Context, infer_context, parse_date, parse_time


@pytest.mark.parametrize(
    "value,start,end,next_day",
    [
        ("08:00–16:00", "08:00", "16:00", False),
        ("22:00-次日06:00", "22:00", "06:00", True),
        ("晚上十点至次日凌晨六点", "22:00", "06:00", True),
        ("下午2点半", "14:30", None, False),
        ("上午12点", "00:00", None, False),
        ("8-16", "08:00", "16:00", False),
        ("16:00-24:00", "16:00", "00:00", True),
        ("8-24", "08:00", "00:00", True),
        ("14:00", "14:00", None, False),
        (0.5, "12:00", None, False),
        (time(0), "00:00", None, False),
        ("夜班", None, None, False),
    ],
)
def test_time(value, start, end, next_day):
    parsed = parse_time(value)
    assert (parsed.start, parsed.end, parsed.next_day) == (start, end, next_day)


@pytest.mark.parametrize(
    "value", ["25:00", "12:75", "08:00、10:00", "08:00-10:00 / 14:00-16:00"]
)
def test_invalid_times(value):
    assert parse_time(value).warning


def test_context_priority():
    c = infer_context(["2027年10月安排", "2026年9月.xlsx"], 2025)
    assert (c.year, c.month, c.year_explicit) == (2027, 10, True)


def test_ambiguous_context():
    c = infer_context(["2026年9月及10月安排"], 2026)
    assert c.ambiguous
    assert parse_date("7日", c, True)[0] is None

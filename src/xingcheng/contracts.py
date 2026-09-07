"""Shared contracts. Importable without the HTTP adapter or desktop runtime."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .models import Event, Report, Source


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInput(StrictModel):
    file_id: str = Field(max_length=100)
    filename: str = Field(max_length=255)
    sheet: str = Field(max_length=100)
    name_cell: str = Field(max_length=30)
    evidence: dict[str, str] = Field(default_factory=dict, max_length=20)
    excerpt: str = Field(default="", max_length=2000)
    hidden: bool = False


class EventInput(StrictModel):
    id: str = Field(default="", max_length=100)
    date: str | None
    title: str = Field(max_length=2000)
    shift: str = Field(default="", max_length=1000)
    start: str | None = None
    end: str | None = None
    end_date: str | None = None
    precision: Literal["date", "point", "interval"]
    location: str = Field(default="", max_length=2000)
    notes: list[str] = Field(default_factory=list, max_length=100)
    sources: list[SourceInput] = Field(max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["confirmed", "pending"]
    reviews: list[dict] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_time(self):
        for value in (self.date, self.end_date):
            if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("日期格式应为 YYYY-MM-DD")
            if value:
                date.fromisoformat(value)
        for value in (self.start, self.end):
            if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError("时间格式应为 HH:MM")
        if self.status == "confirmed" and not self.date:
            raise ValueError("确定日程必须有日期")
        if self.precision == "interval":
            if not self.start or not self.end:
                raise ValueError("区间必须包含开始和结束时间")
            if self.date:
                start = datetime.fromisoformat(f"{self.date}T{self.start}")
                end = datetime.fromisoformat(f"{self.end_date or self.date}T{self.end}")
                if end <= start:
                    raise ValueError("结束时间必须晚于开始时间")
        elif self.precision == "point":
            if not self.start or self.end or self.end_date:
                raise ValueError("单点时间字段不一致")
        elif self.start or self.end or self.end_date:
            raise ValueError("仅日期记录不能带有时间")
        return self

    def event(self):
        value = self.model_dump()
        value["sources"] = [Source(**s) for s in value["sources"]]
        value["id"] = ""  # Recompute IDs; client identifiers are not authoritative.
        return Event(**value)


class ReportInput(StrictModel):
    events: list[EventInput] = Field(default_factory=list, max_length=5000)
    pending: list[EventInput] = Field(default_factory=list, max_length=5000)
    files: list[dict] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=500)
    conflicts: list[dict] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def statuses(self):
        if len(self.events) + len(self.pending) > 5000:
            raise ValueError("每批最多 5000 条安排")
        if any(e.status != "confirmed" for e in self.events) or any(
            e.status != "pending" for e in self.pending
        ):
            raise ValueError("记录状态与结果分组不一致")
        return self

    def report(self):
        return Report(
            [e.event() for e in self.events],
            [e.event() for e in self.pending],
            self.files,
            self.warnings,
        )


class MergeInput(StrictModel):
    reports: list[ReportInput] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def total_limit(self):
        if sum(len(r.events) + len(r.pending) for r in self.reports) > 5000:
            raise ValueError("每批最多合并 5000 条安排")
        if sum(len(r.files) for r in self.reports) > 10:
            raise ValueError("每批最多 10 个文件")
        return self


class ReviewValues(StrictModel):
    date: str
    title: str = Field(min_length=1, max_length=2000)
    shift: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=2000)
    notes: list[Annotated[str, Field(max_length=2000)]] = Field(
        default_factory=list, max_length=100
    )
    start: str | None = None
    end: str | None = None
    next_day: bool = False

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        if not value.strip():
            raise ValueError("请填写事项")
        return value.strip()

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("请选择有效日期")
        date.fromisoformat(value)
        return value

    @field_validator("start", "end")
    @classmethod
    def valid_clock(cls, value):
        if value is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间格式应为 HH:MM")
        return value

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end and not self.start:
            raise ValueError("填写结束时间前，请先填写开始时间")
        if self.next_day and not self.end:
            raise ValueError("选择次日时必须填写结束时间")
        if self.end and not self.next_day and self.end <= self.start:
            raise ValueError("结束时间应晚于开始时间；跨夜安排请选择次日结束")
        # Verify that next-day arithmetic remains representable.
        if self.next_day:
            from datetime import timedelta

            try:
                date.fromisoformat(self.date) + timedelta(days=1)
            except OverflowError as exc:
                raise ValueError("结束日期超出有效范围") from exc
        return self


class ReviewEdit(StrictModel):
    event_id: str = Field(min_length=1, max_length=100)
    values: ReviewValues


class ReviewInput(StrictModel):
    report: ReportInput
    edits: list[ReviewEdit] = Field(min_length=1, max_length=50)

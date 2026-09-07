from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib
import json


def stable_id(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:20]


@dataclass
class Source:
    file_id: str
    filename: str
    sheet: str
    name_cell: str
    evidence: dict[str, str] = field(default_factory=dict)
    excerpt: str = ""
    hidden: bool = False


@dataclass
class Event:
    date: str | None
    title: str
    shift: str = ""
    start: str | None = None
    end: str | None = None
    end_date: str | None = None
    precision: str = "date"
    location: str = ""
    notes: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "confirmed"
    id: str = ""
    reviews: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = stable_id(
                [
                    self.date,
                    self.start,
                    self.end,
                    self.end_date,
                    self.precision,
                    self.title,
                    self.shift,
                    self.location,
                    [asdict(s) for s in self.sources] if not self.date else [],
                ]
            )


@dataclass
class Report:
    events: list[Event] = field(default_factory=list)
    pending: list[Event] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

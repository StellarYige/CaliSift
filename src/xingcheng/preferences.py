"""Display preferences have an independent revision from calendar content."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

CATEGORIES = ["工作", "学习", "培训", "考试", "休息", "其他"]
COLORS = ["#8876c6", "#5d96a5", "#c69553", "#d37f87", "#8b9b88", "#9893a0"]


class Category(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("分类名称不能包含首尾空格或控制字符")
        return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"] = "system"
    font_size: Literal[14, 17, 20] = 14
    density: Literal["comfortable", "compact"] = "comfortable"
    week_start: Literal[0, 1] = 1
    scenario: Literal["general", "work", "study"] = "general"
    hide_rest: bool = False
    categories: list[Category] = Field(
        default_factory=lambda: [
            Category(name=n, color=c) for n, c in zip(CATEGORIES, COLORS)
        ],
        min_length=1,
        max_length=60,
    )

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, values):
        if len({c.name for c in values}) != len(values):
            raise ValueError("分类名称不能重复")
        if not set(CATEGORIES).issubset(c.name for c in values):
            raise ValueError("请保留内置分类；不使用时可以停用")
        return values


class DevicePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_workspace: str = Field(default="", max_length=80)
    width: int = Field(default=1280, ge=640, le=7680)
    height: int = Field(default=860, ge=420, le=4320)
    panel_ratio: int = Field(default=50, ge=30, le=70)


def from_legacy(settings):
    prefs = Preferences(
        theme="light",
        font_size=17 if settings.get("large_text") else 14,
        hide_rest=bool(settings.get("hide_rest")),
    )
    for category in prefs.categories:
        color = settings.get("colors", {}).get(category.name)
        if isinstance(color, str):
            try:
                category.color = Category(name=category.name, color=color).color
            except ValueError:
                pass
    return prefs.model_dump()

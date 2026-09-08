"""Typed native requests, independent of FastAPI. Domain validation stays shared."""

from typing import Annotated
from pydantic import Field, model_validator
from .contracts import StrictModel
from .preferences import Preferences

Identifier = Annotated[str, Field(min_length=1, max_length=100)]


class WorkspaceRequest(StrictModel):
    workspace_id: Identifier


class JobRequest(StrictModel):
    job_id: Identifier


class PreferenceRequest(WorkspaceRequest):
    expected_revision: int = Field(ge=0, strict=True)
    values: Preferences


class DevicePatch(StrictModel):
    last_workspace: str = Field(default="", max_length=100)
    width: int = Field(default=1280, ge=640, le=7680, strict=True)
    height: int = Field(default=860, ge=420, le=4320, strict=True)
    panel_ratio: int = Field(default=50, ge=30, le=70, strict=True)


class DeviceRequest(StrictModel):
    values: DevicePatch | None = None


class TemplateRequest(StrictModel):
    template_id: Identifier


class CourseRequest(WorkspaceRequest):
    course: dict | None = None
    courses: list[dict] | None = Field(default=None, min_length=1, max_length=100)
    semester: dict

    @model_validator(mode="after")
    def one_shape(self):
        if (self.course is None) == (self.courses is None):
            raise ValueError("请选择单课程或批量课程输入")
        return self


REQUESTS = {
    "get_preferences": WorkspaceRequest,
    "save_preferences": PreferenceRequest,
    "device_preferences": DeviceRequest,
    "delete_template": TemplateRequest,
    "last_semester": WorkspaceRequest,
    "course_draft": CourseRequest,
    "get_job": JobRequest,
    "list_jobs": WorkspaceRequest,
}


def validate_request(method: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请求参数必须是对象")
    contract = REQUESTS.get(method)
    if contract is None:
        return payload
    # Preserve omitted patch fields: defaults must not reset device preferences.
    return contract.model_validate(payload).model_dump(exclude_unset=True)

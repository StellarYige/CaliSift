from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import __version__
from .aggregate import merge_reports
from .models import Event, Report, Source
from .readers import MAX_FILE_BYTES, text
from .review import review_report

MAX_BATCH_BYTES = 30 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_BATCH_BYTES + 1024 * 1024
PARSER_TIMEOUT = 20


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        limit = (
            4 * 1024 * 1024
            if scope["path"] in ("/api/merge", "/api/review")
            else MAX_REQUEST_BYTES
        )
        if scope["path"].startswith("/api/calendar/"):
            limit = 42 * 1024 * 1024
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit:
            return await JSONResponse(
                {"detail": "请求内容超过大小上限"}, status_code=413
            )(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "请求内容超过大小上限")
            return message

        await self.app(scope, limited_receive, send)


from .contracts import (
    StrictModel,
    SourceInput,
    EventInput,
    ReportInput,
    MergeInput,
    ReviewValues,
    ReviewEdit,
    ReviewInput,
)


app = FastAPI(
    title="星程 API",
    version=__version__,
    description="把表格交给星程，只看属于你的安排。",
)
app.add_middleware(BodyLimitMiddleware)


@app.get("/health")
def health():
    from .ocr import readiness

    return {
        "status": "ok",
        "name": "星程",
        "version": __version__,
        "capabilities": {"excel": True, "ocr": readiness()},
    }


def parse_isolated(data, filename, name, reference_year, rules=None, layout_hint=None):
    with tempfile.TemporaryDirectory(prefix="xingcheng-") as temp:
        path = Path(temp) / ("input" + Path(filename).suffix.lower())
        path.write_bytes(data)
        try:
            process = subprocess.run(
                [sys.executable, "-m", "xingcheng.worker", str(path)],
                input=json.dumps(
                    {
                        "filename": filename,
                        "name": name,
                        "reference_year": reference_year,
                        "rules": rules,
                        "layout_hint": layout_hint,
                    }
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=PARSER_TIMEOUT,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if process.returncode:
                raise ValueError("解析失败，请检查表格内容或另存后重试")
            parsed = ReportInput.model_validate_json(process.stdout)
            if len(parsed.events) > 2000 or len(parsed.pending) > 2000:
                raise ValueError("单文件结果过多")
            return parsed.report()
        except subprocess.TimeoutExpired:
            return Report(
                files=[
                    {
                        "filename": filename,
                        "status": "error",
                        "error": "解析超过 20 秒，请拆分文件后重试",
                        "sheets": [],
                    }
                ]
            )
        except (ValueError, OSError):
            return Report(
                files=[
                    {
                        "filename": filename,
                        "status": "error",
                        "error": "解析失败或结果过多，请检查或拆分表格后重试",
                        "sheets": [],
                    }
                ]
            )


@app.post("/api/parse")
def parse_endpoint(
    files: Annotated[list[UploadFile], File()],
    name: Annotated[str, Form(min_length=1, max_length=80)],
    reference_year: Annotated[int, Form(ge=1900, le=2199)],
    original_filename: Annotated[str | None, Form(max_length=255)] = None,
    rules: Annotated[str | None, Form(max_length=50000)] = None,
    layout_hint: Annotated[str | None, Form(max_length=50000)] = None,
):
    name = text(name)
    try:
        try:
            rules_config = json.loads(rules) if rules else None
            layout_config = json.loads(layout_hint) if layout_hint else None
            if rules_config:
                from .rules import validate_rules

                validate_rules(rules_config)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, "规则或布局配置无效") from exc
        if not name or re.search(r"[\s、,;；，/|]", name):
            raise HTTPException(422, "请输入一个完整姓名（不含分隔符）")
        if not 1 <= len(files) <= 10:
            raise HTTPException(422, "每批请选择 1–10 个文件")
        reports, total = [], 0
        for upload in files:
            incoming_name = (
                original_filename
                if original_filename and len(files) == 1
                else upload.filename
            )
            filename = (
                (incoming_name or "未命名文件")
                .replace("\\", "/")
                .rsplit("/", 1)[-1][:255]
            )
            data = upload.file.read(MAX_FILE_BYTES + 1)
            total += len(data)
            if total > MAX_BATCH_BYTES:
                raise HTTPException(413, "每批文件合计不能超过 30 MiB")
            if len(data) > MAX_FILE_BYTES:
                reports.append(
                    Report(
                        files=[
                            {
                                "filename": filename,
                                "status": "error",
                                "error": "单个文件不能超过 10 MiB",
                                "sheets": [],
                            }
                        ]
                    )
                )
            else:
                reports.append(
                    parse_isolated(
                        data,
                        filename,
                        name,
                        reference_year,
                        rules_config,
                        layout_config,
                    )
                    if rules_config or layout_config
                    else parse_isolated(data, filename, name, reference_year)
                )
        return merge_reports(reports).to_dict()
    finally:
        for upload in files:
            upload.file.close()


@app.post("/api/merge")
def merge_endpoint(payload: MergeInput):
    return merge_reports([report.report() for report in payload.reports]).to_dict()


@app.post("/api/review")
def review_endpoint(payload: ReviewInput):
    report = payload.report.report()
    # Select records using IDs from the current view; aggregation recomputes
    # canonical IDs after changes, including when two records become duplicates.
    for event, incoming in zip(
        report.events + report.pending, payload.report.events + payload.report.pending
    ):
        event.id = incoming.id
    try:
        return review_report(
            report, [edit.model_dump() for edit in payload.edits]
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class TransformInput(StrictModel):
    calendar: dict
    expected_version: int = Field(ge=0)
    operation: dict


@app.post("/api/calendar/transform")
def calendar_transform(payload: TransformInput):
    from .calendar import transform

    try:
        return transform(payload.calendar, payload.expected_version, payload.operation)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


class ExportInput(StrictModel):
    calendar: dict
    options: dict = Field(default_factory=dict)


@app.post("/api/calendar/export")
def calendar_export(payload: ExportInput):
    from .calendar import export_ics

    try:
        return Response(
            export_ics(payload.calendar, payload.options),
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="xingcheng.ics"'},
        )
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


class CourseInput(StrictModel):
    course: dict
    semester: dict


@app.post("/api/calendar/course")
def calendar_course(payload: CourseInput):
    from .rules import expand_course

    try:
        return expand_course(payload.course, payload.semester)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/ocr")
def ocr_endpoint(
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=80)],
    reference_year: Annotated[int, Form(ge=1900, le=2199)],
    original_filename: Annotated[str, Form(max_length=255)] = "image.png",
    options: Annotated[str, Form(max_length=50000)] = "{}",
):
    from .ocr import recognize_isolated

    try:
        name = text(name)
        if not name or re.search(r"[\s、,;；，/|]", name):
            raise ValueError("请输入一个完整姓名")
        data = file.file.read(MAX_FILE_BYTES + 1)
        return recognize_isolated(
            data, original_filename, name, reference_year, json.loads(options)
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        file.file.close()

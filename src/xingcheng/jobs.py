"""Browser drafts; execution and cancellation are owned by a Web Worker controller."""

import base64
from copy import deepcopy
from datetime import date
from .aggregate import merge_reports
from .calendar import identity, now
from .contracts import ReportInput
from .localstore import LocalError
from .rules import validate_rules
from .processing import execute, apply_report_rules

IMAGES = {".png", ".jpg", ".jpeg"}
EXTENSIONS = IMAGES | {".csv", ".xlsx", ".xls"}


class JobManager:
    def __init__(self, store):
        self.store = store
        self.lock = store.lock

    @staticmethod
    def file_data(file):
        if not file.get("data"):
            raise LocalError("NOT_FOUND", "原文件已清理，请重新选择文件")
        return base64.b64decode(file["data"], validate=True)

    def stage(self, wid, files):
        self.store.workspace(wid)
        if not isinstance(files, list) or not 1 <= len(files) <= 10:
            raise ValueError("每批请选择 1–10 个文件")
        result, total, images = [], 0, 0
        for file in files:
            filename = file["filename"]
            suffix = "." + filename.rsplit(".", 1)[-1].lower()
            if suffix not in EXTENSIONS or len(filename) > 240:
                raise ValueError("请选择 Excel、CSV、PNG 或 JPEG 文件")
            data = self.file_data(file)
            if not 0 < len(data) <= 10 * 1024 * 1024:
                raise ValueError("单文件必须为 1 字节至 10 MiB")
            total += len(data)
            if suffix in IMAGES:
                from PIL import Image
                import io

                with Image.open(io.BytesIO(data)) as picture:
                    if (
                        picture.format not in ("PNG", "JPEG")
                        or picture.width * picture.height > 12000000
                    ):
                        raise ValueError("图片需为 PNG/JPEG，且不超过 1200 万像素")
                images += 1
            result.append(
                dict(
                    id=identity(),
                    filename=filename,
                    suffix=suffix,
                    size=len(data),
                    data=file["data"],
                    status="ready",
                    options={},
                    error="",
                    report=None,
                )
            )
        if total > 30 * 1024 * 1024 or images > 5:
            raise ValueError("每批最多 5 张图片，总大小不能超过 30 MiB")
        jid = identity()
        job = dict(
            id=jid,
            workspace_id=wid,
            status="ready",
            created_at=now(),
            files=result,
            generation=0,
            year=date.today().year,
            source_id="",
            rules={},
            report=None,
        )
        self.store.put("job", jid, wid, job)
        return self.public(self.store.document("job", jid))

    @staticmethod
    def public(job):
        result = deepcopy(job)
        for file in result["files"]:
            file.pop("data", None)
            report = file.pop("report", None)
            if report:
                file.update(
                    source_file_ids=list(
                        dict.fromkeys(
                            f["file_id"]
                            for f in report.get("files", [])
                            if f.get("file_id")
                        )
                    ),
                    count=len(report["events"]) + len(report["pending"]),
                    diagnostics=report.get("warnings", []),
                )
        return result

    def start(
        self,
        job_id,
        year,
        rules=None,
        source_id="",
        retry_ids=None,
        options=None,
        expected_revision=None,
    ):
        job = self.store.document("job", job_id)
        if expected_revision is not None and job.get("revision") != expected_revision:
            raise LocalError("VERSION_CONFLICT", "任务已变化，请重新打开后重试")
        if job["status"] in ("running", "queued", "committed", "discarded"):
            raise ValueError("任务正在运行或已完成，请新建导入任务")
        if not isinstance(year, int) or not 1900 <= year <= 2199:
            raise ValueError("年份应在 1900–2199 之间")
        rules = validate_rules(rules or {})
        if source_id and not any(
            s["id"] == source_id
            for s in self.store.workspace(job["workspace_id"])["calendar"]["sources"]
        ):
            raise ValueError("来源不属于此工作区")
        if retry_ids and (
            year != job["year"]
            or rules != job["rules"]
            or source_id != job["source_id"]
        ):
            raise ValueError("年份或规则已变化，请重新识别全部文件")
        selected = set(retry_ids or [f["id"] for f in job["files"]])
        if not selected.issubset({f["id"] for f in job["files"]}):
            raise ValueError("重试文件无效")
        job.update(
            year=year,
            rules=rules,
            source_id=source_id,
            status="queued",
            generation=job["generation"] + 1,
            report=None,
        )
        for file in job["files"]:
            if file["id"] in selected:
                self.file_data(file)
                file.update(
                    status="queued",
                    report=None,
                    error="",
                    options=deepcopy(
                        (options or {}).get(file["id"], file.get("options", {}))
                    ),
                )
        self.store.put("job", job_id, job["workspace_id"], job)
        return self.public(self.store.document("job", job_id))

    @staticmethod
    def merge(job):
        reports = [
            ReportInput.model_validate(f["report"]).report()
            for f in job["files"]
            if f.get("report")
        ]
        job["report"] = merge_reports(reports).to_dict() if reports else None
        if job["report"]:
            job["report"]["files"] += [
                dict(
                    filename=f["filename"], status="error", error=f["error"], sheets=[]
                )
                for f in job["files"]
                if f["status"] in ("error", "cancelled", "paused")
            ]

    def finish(self, job_id, file_id, generation, report=None, error=""):
        job = self.store.document("job", job_id)
        if job["generation"] != generation or job["status"] not in (
            "queued",
            "running",
        ):
            raise LocalError("VERSION_CONFLICT", "任务已变化，识别结果未保存")
        if report:
            ReportInput.model_validate(report)
            report = self.store.externalize(report)
        file = next(f for f in job["files"] if f["id"] == file_id)
        file.update(status="error" if error else "done", error=error, report=report)
        job["status"] = (
            "running"
            if any(f["status"] == "queued" for f in job["files"])
            else ("review" if any(f.get("report") for f in job["files"]) else "error")
        )
        self.merge(job)
        self.store.put("job", job_id, job["workspace_id"], job)
        return self.public(self.store.document("job", job_id))

    def cancel(self, job_id):
        job = self.store.document("job", job_id)
        if job["status"] in ("committed", "discarded"):
            return self.public(job)
        for f in job["files"]:
            if f["status"] in ("queued", "running"):
                f.update(status="cancelled", error="已取消，可单独重试")
        job.update(
            status=(
                "review" if any(f.get("report") for f in job["files"]) else "cancelled"
            ),
            generation=job["generation"] + 1,
        )
        self.merge(job)
        self.store.put("job", job_id, job["workspace_id"], job)
        return self.public(self.store.document("job", job_id))

    def clean(self, job_id):
        job = self.store.document("job", job_id)
        if job["status"] != "committed":
            self.cancel(job_id)
            job = self.store.document("job", job_id)
            job["status"] = "discarded"
        for f in job["files"]:
            f.pop("data", None)
            f.pop("report", None)
            f["options"] = {}
        job["report"] = None
        self.store.put("job", job_id, job["workspace_id"], job)
        self.store.collect_evidence()

    def table(self, job_id, file_id, **options):
        job = self.store.document("job", job_id)
        file = next((f for f in job["files"] if f["id"] == file_id), None)
        if file is None:
            raise LocalError("NOT_FOUND", "文件不存在")
        return execute(
            dict(
                kind="table",
                filename=file["filename"],
                templates=self.store.documents("template"),
                **options,
            ),
            self.file_data(file),
        )

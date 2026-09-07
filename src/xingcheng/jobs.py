"""Persisted import drafts with bounded, cancellable native worker processes."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from .aggregate import merge_reports
from .calendar import identity, normalized, now
from .contracts import ReportInput
from .localstore import LocalError, atomic_write
from .readers import MAX_FILE_BYTES
from .rules import validate_rules

EXTENSIONS = {".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg"}
IMAGES = {".png", ".jpg", ".jpeg"}


class JobManager:
    def __init__(self, store):
        self.store = store
        self.executor = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="calisift-import"
        )
        self.gates = {
            "ocr": threading.BoundedSemaphore(1),
            "parse": threading.BoundedSemaphore(2),
        }
        self.lock = threading.RLock()
        self.cancelled = set()
        self.processes = {}
        self.closing = False
        for job in store.documents("job"):
            if job["status"] in ("running", "queued"):
                job["status"] = "paused"
                for file in job["files"]:
                    if file["status"] in ("running", "queued"):
                        file["status"] = "paused"
                store.put("job", job["id"], job["workspace_id"], job)

    def stage(self, wid, paths):
        self.store.workspace(wid)
        if not isinstance(paths, list) or not 1 <= len(paths) <= 10:
            raise LocalError("INVALID_INPUT", "每批请选择 1–10 个文件")
        paths = [Path(path).resolve() for path in paths]
        if sum(p.suffix.lower() in IMAGES for p in paths) > 5:
            raise LocalError("INVALID_INPUT", "每批最多 5 张图片")
        total = 0
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                raise LocalError(
                    "UNSUPPORTED_INPUT", "请选择 Excel、CSV、PNG 或 JPEG 文件"
                )
            size = path.stat().st_size
            if not 0 < size <= MAX_FILE_BYTES:
                raise LocalError("INVALID_INPUT", "单文件必须为 1 字节至 10 MiB")
            if path.suffix.lower() in IMAGES:
                from PIL import Image

                with Image.open(path) as picture:
                    if (
                        picture.format not in ("PNG", "JPEG")
                        or picture.width * picture.height > 12_000_000
                    ):
                        raise LocalError(
                            "INVALID_INPUT", "图片需为 PNG/JPEG，且不超过 1200 万像素"
                        )
            total += size
        if total > 30 * 1024 * 1024:
            raise LocalError("INVALID_INPUT", "每批总大小不能超过 30 MiB")
        jid = identity()
        folder = self.store.jobs_dir / jid
        folder.mkdir()
        files = []
        try:
            for path in paths:
                fid = identity()
                target = folder / (fid + path.suffix.lower())
                atomic_write(target, path.read_bytes())
                files.append(
                    dict(
                        id=fid,
                        filename=path.name,
                        suffix=path.suffix.lower(),
                        size=target.stat().st_size,
                        status="ready",
                        error="",
                        report=None,
                        options={},
                    )
                )
            job = dict(
                id=jid,
                workspace_id=wid,
                status="ready",
                created_at=now(),
                files=files,
                generation=0,
                year=date.today().year,
                source_id="",
                rules={},
                report=None,
            )
            self.store.put("job", jid, wid, job)
            return self.public(job)
        except Exception:
            for child in folder.iterdir():
                if child.is_file():
                    child.unlink()
            folder.rmdir()
            raise

    def file_path(self, job, file):
        return self.store.jobs_dir / job["id"] / (file["id"] + file["suffix"])

    @staticmethod
    def public(job):
        result = deepcopy(job)
        for file in result["files"]:
            report = file.get("report")
            if report:
                file["count"] = len(report.get("events", [])) + len(
                    report.get("pending", [])
                )
                file["diagnostics"] = report.get("warnings", [])
                file.pop("report", None)
        return result

    def start(self, jid, year, rules=None, source_id="", retry_ids=None, options=None):
        with self.lock:
            job = self.store.document("job", jid)
            if job["status"] in ("running", "queued", "committed", "discarded"):
                raise LocalError(
                    "INVALID_INPUT", "任务正在运行或已完成，请新建导入任务"
                )
            if not isinstance(year, int) or not 1900 <= year <= 2199:
                raise LocalError("INVALID_INPUT", "年份应在 1900–2199 之间")
            rules = validate_rules(rules or {})
            if retry_ids and (
                year != job["year"]
                or rules != job["rules"]
                or source_id != job["source_id"]
            ):
                raise LocalError(
                    "INVALID_INPUT", "年份或规则已变化，请重新识别全部文件"
                )
            selected = set(retry_ids or [f["id"] for f in job["files"]])
            if not selected.issubset({f["id"] for f in job["files"]}):
                raise LocalError("INVALID_INPUT", "重试文件无效")
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
                    if not self.file_path(job, file).is_file():
                        raise LocalError("NOT_FOUND", "原文件已清理，请重新选择文件")
                    file.update(status="queued", error="", report=None)
                    file["options"] = deepcopy(
                        (options or {}).get(file["id"], file.get("options", {}))
                    )
            self.cancelled.discard(jid)
            self.store.put("job", jid, job["workspace_id"], job)
            for file in job["files"]:
                if file["id"] in selected:
                    self.executor.submit(
                        self._process, jid, file["id"], job["generation"]
                    )
            return self.public(job)

    def run_worker(self, request, cancel_key=None, timeout=None):
        kind = request["kind"]
        timeout = timeout or (90 if kind == "ocr" else 20)
        if getattr(sys, "frozen", False):
            command = [str(Path(sys.executable).parent / "calisift-worker.exe")]
        else:
            command = [sys.executable, "-m", "xingcheng.desktop_worker"]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        token = identity()
        with self.lock:
            self.processes[token] = (cancel_key, process)
            if self.closing or cancel_key in self.cancelled:
                process.kill()
        try:
            output, _ = process.communicate(
                json.dumps(request, ensure_ascii=False), timeout=timeout
            )
            if self.closing or cancel_key in self.cancelled:
                raise LocalError("JOB_CANCELLED", "任务已取消，已保存日历保持原样")
            if process.returncode or not output:
                raise LocalError("WORKER_FAILED", "识别进程未完成，请单独重试此文件")
            if len(output.encode("utf-8")) > 48 * 1024 * 1024:
                raise LocalError("INVALID_INPUT", "识别结果过大，请拆分文件后重试")
            result = json.loads(output)
            if "error" in result:
                raise LocalError("PROCESSING_FAILED", result["error"])
            return result
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise LocalError(
                "JOB_TIMEOUT", f"处理超过 {timeout} 秒，请缩小范围后重试"
            ) from exc
        finally:
            with self.lock:
                self.processes.pop(token, None)

    def _process(self, jid, fid, generation):
        job = self.store.document("job", jid)
        file = next(f for f in job["files"] if f["id"] == fid)
        kind = "ocr" if file["suffix"] in IMAGES else "parse"
        with self.gates[kind]:
            with self.lock:
                job = self.store.document("job", jid)
                if (
                    self.closing
                    or jid in self.cancelled
                    or job["generation"] != generation
                ):
                    return
                file = next(f for f in job["files"] if f["id"] == fid)
                file["status"] = "running"
                job["status"] = "running"
                self.store.put("job", jid, job["workspace_id"], job)
            try:
                request = dict(
                    kind=kind,
                    path=str(self.file_path(job, file)),
                    filename=file["filename"],
                    name=self.store.workspace(job["workspace_id"])["name"],
                    year=job["year"],
                    rules=job["rules"],
                    layout_hint=job["rules"].get("template"),
                    options={
                        **file.get("options", {}),
                        "layout_hint": job["rules"].get("template"),
                    },
                )
                output = self.run_worker(request, jid)
                report = self.store.externalize(output["report"])
                failures = [
                    f for f in report.get("files", []) if f.get("status") == "error"
                ]
                if failures:
                    raise LocalError(
                        "PROCESSING_FAILED",
                        failures[0].get("error") or "文件未能识别，请检查后重试",
                    )
                ReportInput.model_validate(report)
                error = ""
            except Exception as exc:
                report = None
                error = (
                    str(exc)
                    if isinstance(exc, (ValueError, OSError))
                    else "处理失败，请重试此文件"
                )
            with self.lock:
                latest = self.store.document("job", jid)
                if (
                    self.closing
                    or jid in self.cancelled
                    or latest["generation"] != generation
                ):
                    return
                target = next(f for f in latest["files"] if f["id"] == fid)
                target.update(
                    report=report, status="error" if error else "done", error=error
                )
                if all(
                    f["status"] not in ("queued", "running") for f in latest["files"]
                ):
                    latest["status"] = (
                        "review"
                        if any(f.get("report") for f in latest["files"])
                        else "error"
                    )
                    self._merge(latest)
                self.store.put("job", jid, latest["workspace_id"], latest)

    @staticmethod
    def _merge(job):
        reports = [
            ReportInput.model_validate(f["report"]).report()
            for f in job["files"]
            if f.get("report")
        ]
        if reports:
            job["report"] = merge_reports(reports).to_dict()
            for file in job["files"]:
                if file["status"] in ("error", "cancelled", "paused"):
                    job["report"]["files"].append(
                        dict(
                            filename=file["filename"],
                            status="error",
                            error=file["error"],
                            sheets=[],
                        )
                    )
        else:
            job["report"] = None

    def cancel(self, jid):
        with self.lock:
            job = self.store.document("job", jid)
            if job["status"] in ("committed", "discarded"):
                return self.public(job)
            self.cancelled.add(jid)
            for key, process in self.processes.values():
                if key == jid:
                    process.kill()
            for file in job["files"]:
                if file["status"] in ("running", "queued"):
                    file.update(status="cancelled", error="已取消，可单独重试")
            job.update(
                status=(
                    "review"
                    if any(f.get("report") for f in job["files"])
                    else "cancelled"
                ),
                generation=job["generation"] + 1,
            )
            self._merge(job)
            self.store.put("job", jid, job["workspace_id"], job)
            return self.public(job)

    def clean(self, jid):
        with self.lock:
            job = self.store.document("job", jid)
            if job["status"] != "committed":
                self.cancel(jid)
                job = self.store.document("job", jid)
                job["status"] = "discarded"
            for file in job["files"]:
                self.file_path(job, file).unlink(missing_ok=True)
                file.pop("report", None)
                file["options"] = {}
            job["report"] = None
            self.store.put("job", jid, job["workspace_id"], job)
            folder = self.store.jobs_dir / jid
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()

    def table(self, jid, fid, **options):
        job = self.store.document("job", jid)
        file = next((f for f in job["files"] if f["id"] == fid), None)
        if file is None:
            raise LocalError("NOT_FOUND", "文件不存在")
        return self.run_worker(
            dict(
                kind="table",
                path=str(self.file_path(job, file)),
                filename=file["filename"],
                templates=self.store.documents("template"),
                **options,
            ),
            jid,
        )

    def close(self):
        with self.lock:
            self.closing = True
            for _, process in self.processes.values():
                if process.poll() is None:
                    process.kill()
        self.executor.shutdown(wait=True, cancel_futures=True)

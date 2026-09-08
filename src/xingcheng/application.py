"""Local application commands, shared by the desktop bridge and CLI."""

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

from . import __version__
from .aggregate import detect_conflicts
from .backup import pack_backup, unpack_backup
from .calendar import (
    effective,
    export_ics,
    identity,
    normalized,
    now,
    report_for,
    transform,
    validate_calendar,
)
from .jobs import JobManager, IMAGES
from .instance import InstanceLock
from .localstore import LocalError, LocalStore, atomic_write, digest, encode
from .rules import expand_course, validate_rules


class Application:
    def __init__(self, root):
        self.instance = InstanceLock(root)
        try:
            self.store = LocalStore(root)
            self.jobs = JobManager(self.store)
        except Exception:
            self.instance.close()
            raise
        self.restore_tokens = {}
        self._views = {}

    def capabilities(self):
        from .ocr import readiness

        return dict(
            name="CaliSift · 星程",
            version=__version__,
            ocr=readiness(),
            timezone="Asia/Shanghai",
            workspaces=self.store.workspaces(),
            data_path=str(self.store.root),
            device=self.store.device_preferences(),
            limits=dict(
                files=10, images=5, file_mib=10, batch_mib=30, pixels=12_000_000
            ),
        )

    def workspace(self, workspace_id):
        workspace = self.store.workspace(workspace_id)
        calendar = workspace.pop("calendar")
        workspace["sources"] = [
            dict(
                id=s["id"],
                name=s["name"],
                rules=s.get("rules", {}),
                revisions=[
                    dict(
                        id=r["id"],
                        imported_at=r["imported_at"],
                        coverage=r.get("coverage"),
                        count=len(r["report"]["events"]) + len(r["report"]["pending"]),
                    )
                    for r in s["revisions"]
                ],
            )
            for s in calendar["sources"]
        ]
        prefs = self.store.preferences(workspace_id)
        workspace["preferences"] = prefs
        workspace["settings"] = {
            **prefs["values"],
            "large_text": prefs["values"]["font_size"] > 14,
            "colors": {c["name"]: c["color"] for c in prefs["values"]["categories"]},
        }
        workspace["can_undo"] = bool(calendar.get("undo"))
        workspace["count"] = len(calendar["events"])
        workspace["active_count"] = sum(
            not e.get("archived") for e in calendar["events"]
        )
        return workspace

    def create_workspace(self, name):
        return self.workspace(self.store.create_workspace(name)["id"])

    def list_jobs(self, workspace_id):
        return [
            dict(
                id=j["id"],
                status=j["status"],
                created_at=j["created_at"],
                filenames=[f["filename"] for f in j["files"]],
                size=sum(f["size"] for f in j["files"]),
            )
            for j in self.store.documents("job", workspace_id)
            if j["status"] != "discarded"
        ]

    def get_job(self, job_id):
        job = self.store.document("job", job_id)
        return self.jobs.public(job)

    def job_file(self, job_id, file_id):
        job = self.store.document("job", job_id)
        file = next((f for f in job["files"] if f["id"] == file_id), None)
        if file is None:
            raise LocalError("NOT_FOUND", "文件不存在")
        return job, file

    def image_preview(self, job_id, file_id):
        import base64
        import io
        from PIL import Image, ImageOps

        job, file = self.job_file(job_id, file_id)
        if file["suffix"] not in IMAGES:
            raise LocalError("INVALID_INPUT", "请选择图片")
        with Image.open(self.jobs.file_path(job, file)) as original:
            picture = ImageOps.exif_transpose(original).convert("RGB")
            picture.thumbnail((1800, 1800))
            stream = io.BytesIO()
            picture.save(stream, format="JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode(
            "ascii"
        )

    def ocr_details(self, job_id, file_id):
        _, file = self.job_file(job_id, file_id)
        report = file.get("report") or {}
        return next((f["ocr"] for f in report.get("files", []) if "ocr" in f), {})

    def edit_draft(self, job_id, edits):
        with self.jobs.lock:
            job = self.store.document("job", job_id)
            if job["status"] != "review" or not job.get("report"):
                raise LocalError("INVALID_INPUT", "请先完成识别")
            if not isinstance(edits, list) or not 1 <= len(edits) <= 5000:
                raise LocalError("INVALID_INPUT", "请选择要修改的草稿")
            values = job["report"]["events"] + job["report"]["pending"]
            indexes = set()
            for edit in edits:
                index = edit["index"]
                if (
                    not isinstance(index, int)
                    or not 0 <= index < len(values)
                    or index in indexes
                ):
                    raise LocalError("INVALID_INPUT", "草稿位置已变化，请重新选择")
                indexes.add(index)
                before = deepcopy(values[index])
                candidate = normalized({**before, **edit["values"]})
                candidate["reviews"] = (
                    before.get("reviews", [])
                    + [
                        dict(
                            before={k: v for k, v in before.items() if k != "reviews"},
                            after={
                                k: v for k, v in candidate.items() if k != "reviews"
                            },
                            edited_at=now(),
                        )
                    ]
                )[-50:]
                values[index] = candidate
            job["report"]["events"] = [e for e in values if e["status"] == "confirmed"]
            job["report"]["pending"] = [e for e in values if e["status"] == "pending"]
            self.store.put("job", job_id, job["workspace_id"], job)
            return self.jobs.public(job)

    def course_draft(self, workspace_id, course=None, semester=None, courses=None):
        self.store.workspace(workspace_id)
        if courses is not None and course is not None:
            raise ValueError("请使用单课程或批量课程中的一种输入")
        selected = courses if courses is not None else [course]
        if not isinstance(selected, list) or not 1 <= len(selected) <= 100:
            raise ValueError("每次请填写 1–100 门课程")
        reports = [expand_course(item, semester) for item in selected]
        report = dict(
            events=[e for r in reports for e in r["events"]],
            pending=[],
            files=[],
            warnings=[],
            conflicts=[],
        )
        if len(report["events"]) > 5000:
            raise ValueError("展开结果超过 5000 条，请缩小课程范围")
        jid = identity()
        job = dict(
            id=jid,
            workspace_id=workspace_id,
            status="review",
            created_at=now(),
            files=[],
            generation=0,
            year=date.fromisoformat(semester["monday"]).year,
            source_id="",
            rules={"semester": semester},
            report=report,
        )
        with self.store.connection(True) as db:
            self.store._put(db, "job", jid, workspace_id, job)
            self.store._put(db, "semester", workspace_id, workspace_id, semester)
        return self.jobs.public(job)

    def get_preferences(self, workspace_id):
        return self.store.preferences(workspace_id)

    def save_preferences(self, workspace_id, expected_revision, values):
        return self.store.save_preferences(workspace_id, expected_revision, values)

    def device_preferences(self, values=None):
        return (
            self.store.save_device_preferences(values)
            if values is not None
            else self.store.device_preferences()
        )

    def last_semester(self, workspace_id):
        self.store.workspace(workspace_id)
        values = self.store.documents("semester", workspace_id)
        return values[0] if values else None

    def delete_template(self, template_id):
        self.store.document("template", template_id)
        self.store.delete("template", template_id)
        return True

    def diagnostics(self):
        import platform
        from .ocr import readiness

        result = readiness()
        return dict(
            version=__version__,
            system=platform.system(),
            release=platform.release(),
            architecture=platform.machine(),
            python=platform.python_version(),
            database_schema=2,
            ocr_ready=result["ready"],
        )

    @staticmethod
    def _calendar_report(report):
        result = deepcopy(report)
        # Keep only relevant evidence; discard the full source view after confirmation.
        for file in result.get("files", []):
            if file.get("ocr"):
                file["ocr"].pop("preview_image", None)
                file["ocr"].pop("blocks", None)
            for sheet in file.get("sheets", []):
                sheet.pop("preview", None)
        return result

    def preview_change(self, workspace_id, expected_version, operation, job_id=None):
        current = self.store.workspace(workspace_id)["calendar"]
        if current["version"] != expected_version:
            raise LocalError("VERSION_CONFLICT", "日历已变化，请刷新后重新预览")
        operation = deepcopy(operation)
        dependency = None
        if job_id:
            job = self.store.document("job", job_id)
            if (
                job["workspace_id"] != workspace_id
                or job["status"] != "review"
                or not job.get("report")
            ):
                raise LocalError("INVALID_INPUT", "请选择当前工作区内已识别的草稿")
            if operation["type"] not in ("append", "update"):
                raise LocalError("INVALID_INPUT", "草稿只能追加或更新来源")
            operation["report"] = self._calendar_report(job["report"])
            if not operation.get("source_id") and job.get("rules"):
                operation["rules"] = job["rules"]
            dependency = dict(kind="job", id=job_id, digest=digest(job))
        elif operation["type"] in ("append", "update"):
            raise LocalError("INVALID_INPUT", "请先建立并核对导入草稿")
        if operation["type"] == "archive":
            candidate = deepcopy(current)
            before = operation.get("before")
            if before:
                date.fromisoformat(before)
            ids = operation.get("event_ids")
            if not ids and not before:
                raise LocalError("INVALID_INPUT", "请选择日期或要恢复的归档安排")
            changed = []
            for record in candidate["events"]:
                event = effective(record)
                selected = (
                    record["id"] in ids
                    if ids
                    else bool(
                        event["date"] and (event["end_date"] or event["date"]) < before
                    )
                )
                target = not bool(operation.get("restore"))
                if selected and bool(record.get("archived")) != target:
                    record["archived"] = target
                    changed.append(
                        dict(
                            id=record["id"],
                            before=event,
                            after={**event, "archived": target},
                        )
                    )
            candidate["version"] += 1
            validate_calendar(candidate)
            result = dict(
                base_version=expected_version,
                calendar=candidate,
                summary=dict(
                    added=[],
                    changed=changed,
                    cancelled=[],
                    duplicates=0,
                    unresolved=[],
                    correction_conflicts=[],
                    warnings=[],
                ),
            )
        else:
            result = transform(current, expected_version, operation)
        result.pop("report", None)
        preview = self.store.preview(workspace_id, result, dependency)
        if operation["type"] == "update":
            preview["old_candidates"] = [
                dict(
                    id=e["id"],
                    **{
                        k: effective(e)[k]
                        for k in ("date", "title", "start", "end", "location")
                    },
                )
                for e in current["events"]
                if any(
                    c["source_id"] == operation["source_id"] for c in e["contributions"]
                )
            ]
        return preview

    def commit_change(self, preview_id, expected_version):
        result = self.store.commit(preview_id, expected_version)
        warning = ""
        try:
            if result.get("job_id"):
                self.jobs.clean(result["job_id"])
            self.store.safety_backup()
        except OSError:
            warning = "安排已保存，但临时文件清理或自动恢复点失败，请检查空间并手动备份"
        return {
            **result,
            "warning": warning,
            "workspace": self.workspace(result["workspace_id"]),
        }

    def _event_view(self, workspace_id):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT version FROM workspaces WHERE id=?", (workspace_id,)
            ).fetchone()
            if row is None:
                raise LocalError("NOT_FOUND", "工作区不存在，请重新选择")
            cached = self._views.get(workspace_id)
            if cached is not None and cached["calendar"]["version"] == row[0]:
                return cached
            calendar = self.store.workspace(workspace_id)["calendar"]
            values = [(record, effective(record)) for record in calendar["events"]]
            visible = [
                SimpleNamespace(**value)
                for record, value in values
                if not record["hidden"]
                and not record.get("cancelled")
                and not record.get("archived")
                and value["status"] == "confirmed"
            ]
            result = dict(
                calendar=calendar, values=values, conflicts=detect_conflicts(visible)
            )
            self._views.pop(workspace_id, None)
            self._views[workspace_id] = result
            if len(self._views) > 3:
                self._views.pop(next(iter(self._views)))
            return result

    def events(
        self,
        workspace_id,
        query="",
        source_id="",
        category="",
        date_from="",
        date_to="",
        view="active",
        page=0,
    ):
        snapshot = self._event_view(workspace_id)
        calendar = snapshot["calendar"]
        preferences = self.store.preferences(workspace_id)["values"]
        sources = {s["id"]: s["name"] for s in calendar["sources"]}
        matches = []
        conflicts = snapshot["conflicts"]
        conflicting = {eid for conflict in conflicts for eid in conflict["event_ids"]}
        for record, event in snapshot["values"]:
            if (
                view == "archived"
                and not record.get("archived")
                or view != "archived"
                and record.get("archived")
            ):
                continue
            if (
                view == "hidden"
                and not record["hidden"]
                or view == "active"
                and (record["hidden"] or record.get("cancelled"))
            ):
                continue
            if (
                view == "active"
                and preferences.get("hide_rest")
                and event["category"] == "休息"
            ):
                continue
            names = [sources[c["source_id"]] for c in record["contributions"]]
            if source_id and not any(
                c["source_id"] == source_id for c in record["contributions"]
            ):
                continue
            if category and event["category"] != category:
                continue
            if (
                date_from
                and (event.get("end_date") or event["date"] or "") < date_from
                or date_to
                and (event["date"] or "") > date_to
            ):
                continue
            if (
                query
                and query.casefold()
                not in " ".join(
                    [event["date"] or "", event["title"], event["location"], *names]
                ).casefold()
            ):
                continue
            matches.append(
                {
                    **event,
                    "source_names": names,
                    "archived": bool(record.get("archived")),
                    "cancelled": bool(record.get("cancelled")),
                    "conflict": record["id"] in conflicting,
                }
            )
        matches.sort(key=lambda e: (e["date"] or "9999", e["start"] or "", e["title"]))
        page = max(0, int(page))
        return dict(
            items=deepcopy(matches[page * 50 : (page + 1) * 50]),
            total=len(matches),
            page=page,
            conflicts=len(conflicts),
        )

    def save_template(self, name, rules, description="", template_id=None):
        name = name.strip()
        if not name or len(name) > 100 or len(description) > 2000:
            raise LocalError("INVALID_INPUT", "请填写有效模板名称和说明")
        rules = validate_rules(rules)
        if template_id:
            self.store.document("template", template_id)
        value = dict(
            format="calisift.template",
            version=1,
            id=template_id or identity(),
            name=name,
            description=description,
            rules=rules,
        )
        self.store.put("template", value["id"], "", value)
        return value

    def import_template(self, data):
        value = json.loads(data)
        if (
            value.get("format") != "calisift.template"
            or value.get("version") != 1
            or set(value) - {"format", "version", "id", "name", "description", "rules"}
        ):
            raise LocalError("INVALID_INPUT", "请选择版本 1 的 CaliSift 声明式模板")
        return self.save_template(
            value["name"], value["rules"], value.get("description", "")
        )

    def templates(self):
        return self.store.documents("template")

    def export_template(self, template_id):
        value = self.store.document("template", template_id)
        return encode({k: v for k, v in value.items() if k != "id"})

    def save_profile(
        self, workspace_id, name, options, profile_id=None, filename="CaliSift-日程.ics"
    ):
        self.store.workspace(workspace_id)
        if not name.strip() or len(name) > 100:
            raise LocalError("INVALID_INPUT", "请填写导出方案名称")
        # Validate options without failing on unrelated incomplete events.
        from .calendar import empty_calendar

        export_ics(empty_calendar("校验"), options)
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 200:
            raise LocalError("INVALID_INPUT", "请填写有效的导出文件名")
        value = dict(
            id=profile_id or identity(),
            name=name.strip(),
            options=options,
            filename=filename,
        )
        self.store.put("profile", value["id"], workspace_id, value)
        return value

    def export_preview(self, workspace_id, options):
        calendar = self.store.workspace(workspace_id)["calendar"]
        selected = []
        excluded = []
        for record in calendar["events"]:
            event = effective(record)
            if (
                options.get("from")
                and (event["date"] or "") < options["from"]
                or options.get("to")
                and (event["date"] or "") > options["to"]
            ):
                continue
            if options.get("category") and event["category"] != options["category"]:
                continue
            if options.get("source_id") and not any(
                c["source_id"] == options["source_id"] for c in record["contributions"]
            ):
                continue
            reason = (
                "已归档"
                if record.get("archived")
                else (
                    "已隐藏"
                    if record["hidden"]
                    else (
                        "已取消"
                        if record.get("cancelled")
                        else (
                            "待确认"
                            if event["status"] != "confirmed"
                            else (
                                "需补全时间或设为全天"
                                if not event["start"] and not event["all_day"]
                                else ""
                            )
                        )
                    )
                )
            )
            if reason:
                excluded.append(
                    dict(
                        id=record["id"],
                        title=event["title"],
                        date=event["date"],
                        reason=reason,
                    )
                )
            else:
                selected.append(record)
        candidate = deepcopy(calendar)
        candidate["events"] = deepcopy(selected)
        export_ics(candidate, options)
        return dict(
            version=calendar["version"],
            count=len(selected),
            excluded=excluded,
            blocked=any(e["reason"] == "需补全时间或设为全天" for e in excluded),
            calendar=candidate,
        )

    def export_file(self, workspace_id, expected_version, options, path, profile_id=""):
        with self.store.lock:
            preview = self.export_preview(workspace_id, options)
            if preview["version"] != expected_version:
                raise LocalError("VERSION_CONFLICT", "日历已变化，请重新查看导出预览")
            if preview["blocked"]:
                raise LocalError(
                    "CONFIRMATION_REQUIRED", "请先补全导出范围内的时间，或明确设置全天"
                )
            if not preview["count"]:
                raise LocalError("INVALID_INPUT", "当前范围没有可导出的安排")
            calendar = preview["calendar"]
            states = self.store.documents("export_state", workspace_id)
            state = deepcopy(states[0]["events"]) if states else {}
            fingerprints = {}
            for record in calendar["events"]:
                event = effective(record)
                fingerprint = digest(
                    {
                        k: v
                        for k, v in event.items()
                        if k
                        in (
                            "date",
                            "start",
                            "end",
                            "end_date",
                            "title",
                            "location",
                            "notes",
                            "category",
                            "all_day",
                        )
                    }
                    | {
                        "alarm": options.get("alarm", 0),
                        "sources": [
                            s["name"]
                            for s in calendar["sources"]
                            if any(
                                c["source_id"] == s["id"]
                                for c in record["contributions"]
                            )
                        ],
                    }
                )
                prior = state.get(record["id"])
                record["sequence"] = (
                    max(
                        record["sequence"],
                        prior["sequence"] + int(prior["hash"] != fingerprint),
                    )
                    if prior
                    else record["sequence"]
                )
                state[record["id"]] = dict(
                    hash=fingerprint, sequence=record["sequence"]
                )
                fingerprints[record["id"]] = fingerprint
            content = export_ics(calendar, options).encode("utf-8")
            previous = next(
                (
                    r
                    for r in self.store.documents("export", workspace_id)
                    if r.get("profile_id", "") == profile_id
                ),
                None,
            )
            before = previous["fingerprints"] if previous else {}
            changes = dict(
                added=len(set(fingerprints) - set(before)),
                removed=len(set(before) - set(fingerprints)),
                changed=sum(
                    before[k] != fingerprints[k]
                    for k in set(before) & set(fingerprints)
                ),
            )
            target = Path(path)
            atomic_write(target, content)
            record = dict(
                id=identity(),
                created_at=now(),
                filename=target.name,
                path=str(target.resolve()),
                profile_id=profile_id,
                count=len(fingerprints),
                version=expected_version,
                options=options,
                fingerprints=fingerprints,
                checksum=hashlib.sha256(content).hexdigest(),
                changes=changes,
            )
            with self.store.connection(True) as db:
                self.store._put(
                    db,
                    "export_state",
                    workspace_id,
                    workspace_id,
                    dict(id=workspace_id, events=state),
                )
                self.store._put(db, "export", record["id"], workspace_id, record)
            return record

    def backup_file(self, workspace_id, path):
        atomic_write(Path(path), pack_backup(self.store, workspace_id))
        return dict(path=str(Path(path).resolve()))

    def prepare_restore(self, data):
        payload = unpack_backup(data)
        token = identity()
        self.restore_tokens[token] = payload
        calendar = payload["calendar"]
        return dict(
            token=token,
            name=calendar["personName"],
            events=len(calendar["events"]),
            sources=len(calendar["sources"]),
            evidence=len(payload["evidence"]["crops"]),
        )

    def restore_backup(self, token, replace_workspace_id=None, expected_version=None):
        if token not in self.restore_tokens:
            raise LocalError("VERSION_CONFLICT", "恢复预览已失效，请重新选择备份")
        payload = deepcopy(self.restore_tokens[token])
        calendar = payload["calendar"]
        # Validate all ancillary data before writing a single workspace row.
        from .preferences import Preferences, from_legacy

        prefs = Preferences.model_validate(
            payload.get("preferences", from_legacy(calendar.get("settings", {})))
        ).model_dump()
        if payload.get("semester"):
            validate_rules({"semester": payload["semester"]})
        for template in payload.get("templates", []):
            validate_rules(template["rules"])
        with self.store.lock:
            export_states = (payload.get("export_states") or [{}])[0].get("events", {})
            if replace_workspace_id:
                current = self.store.workspace(replace_workspace_id)
                if current["version"] != expected_version:
                    raise LocalError("VERSION_CONFLICT", "工作区已变化，请重新预览恢复")
                calendar["version"] = max(calendar["version"], current["version"]) + 1
                for state in self.store.documents("export_state", replace_workspace_id):
                    for eid, value in state["events"].items():
                        if (
                            eid not in export_states
                            or export_states[eid]["sequence"] <= value["sequence"]
                        ):
                            export_states[eid] = value
            wid = replace_workspace_id or identity()
            self.store.safety_backup("restore")
            self.store.externalize(payload["evidence"])
            calendar = self.store.externalize(calendar)
            with self.store.connection(True) as db:
                if replace_workspace_id:
                    db.execute(
                        "UPDATE workspaces SET name=?,version=?,calendar=?,updated_at=? WHERE id=?",
                        (
                            calendar["personName"],
                            calendar["version"],
                            encode(calendar),
                            now(),
                            wid,
                        ),
                    )
                    db.execute(
                        "DELETE FROM documents WHERE workspace=? AND kind IN ('profile','export','export_state')",
                        (wid,),
                    )
                    db.execute(
                        "DELETE FROM previews WHERE workspace=? AND receipt IS NULL",
                        (wid,),
                    )
                else:
                    db.execute(
                        "INSERT INTO workspaces VALUES(?,?,?,?,?)",
                        (
                            wid,
                            calendar["personName"],
                            calendar["version"],
                            encode(calendar),
                            now(),
                        ),
                    )
                self.store._index(db, wid, calendar)
                self.store._put(
                    db, "preferences", wid, wid, dict(revision=0, values=prefs)
                )
                db.execute(
                    "DELETE FROM documents WHERE kind='semester' AND workspace=?",
                    (wid,),
                )
                if payload.get("semester"):
                    self.store._put(db, "semester", wid, wid, payload["semester"])
                profile_ids = {
                    item["id"]: identity() for item in payload.get("profiles", [])
                }
                for kind, items in [
                    ("template", payload.get("templates", [])),
                    ("profile", payload.get("profiles", [])),
                    ("export", payload.get("exports", [])),
                ]:
                    for item in items:
                        item["id"] = (
                            profile_ids[item["id"]] if kind == "profile" else identity()
                        )
                        if kind == "export":
                            item.pop("path", None)
                            item["profile_id"] = profile_ids.get(
                                item.get("profile_id"), ""
                            )
                        self.store._put(
                            db,
                            kind,
                            item["id"],
                            "" if kind == "template" else wid,
                            item,
                        )
                if export_states:
                    self.store._put(
                        db, "export_state", wid, wid, dict(id=wid, events=export_states)
                    )
            del self.restore_tokens[token]
            return self.workspace(wid)

    def close(self):
        try:
            self.jobs.close()
        finally:
            self.instance.close()

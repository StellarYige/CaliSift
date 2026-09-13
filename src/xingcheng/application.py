"""Browser application commands. Persistence is committed by IndexedDB after each command."""

import base64
from copy import deepcopy
from datetime import date
import hashlib
import json
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
from .localstore import LocalError, LocalStore, digest, encode
from .rules import expand_course, validate_rules


class Application:
    def __init__(self, state=None):
        self.store = LocalStore(state)
        self.jobs = JobManager(self.store)
        self.restore_tokens = self.store.state["restore_tokens"]

    def capabilities(self):
        return dict(
            name="CaliSift · 星程",
            version=__version__,
            timezone="Asia/Shanghai",
            ocr=dict(
                ready=True,
                model="PP-OCRv5 mobile · ONNX Runtime Web 1.23.2",
                message="首次使用会加载本站资源",
            ),
            workspaces=self.store.workspaces(),
            device=self.store.device_preferences(),
            limits=dict(files=10, images=5, file_mib=10, batch_mib=30, pixels=12000000),
        )

    def _event_view(self, workspace_id):
        calendar = self.store.workspace(workspace_id)["calendar"]
        values = [(r, effective(r)) for r in calendar["events"]]
        visible = [
            SimpleNamespace(**v)
            for r, v in values
            if not r["hidden"]
            and not r.get("cancelled")
            and not r.get("archived")
            and v["status"] == "confirmed"
        ]
        return dict(
            calendar=calendar, values=values, conflicts=detect_conflicts(visible)
        )

    def image_preview(self, job_id, file_id):
        from PIL import Image, ImageOps
        import io

        job, file = self.job_file(job_id, file_id)
        with Image.open(io.BytesIO(self.jobs.file_data(file))) as original:
            picture = ImageOps.exif_transpose(original).convert("RGB")
            picture.thumbnail((1800, 1800))
            stream = io.BytesIO()
            picture.save(stream, format="JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode(
            "ascii"
        )

    def commit_change(self, preview_id, expected_version):
        result = self.store.commit(preview_id, expected_version)
        if result.get("job_id"):
            self.jobs.clean(result["job_id"])
        self.store.collect_evidence()
        return {
            **result,
            "warning": "",
            "workspace": self.workspace(result["workspace_id"]),
        }

    def restore_backup(self, token, replace_workspace_id=None, expected_version=None):
        from .preferences import Preferences, from_legacy

        if token not in self.restore_tokens:
            raise LocalError("VERSION_CONFLICT", "恢复预览已失效，请重新选择备份")
        payload = deepcopy(self.restore_tokens[token])
        calendar = payload["calendar"]
        prefs = Preferences.model_validate(
            payload.get("preferences", from_legacy(calendar.get("settings", {})))
        ).model_dump()
        if payload.get("semester"):
            validate_rules({"semester": payload["semester"]})
        for template in payload.get("templates", []):
            validate_rules(template["rules"])
        states = (payload.get("export_states") or [{}])[0].get("events", {})
        revision = 0
        if replace_workspace_id:
            current = self.store.workspace(replace_workspace_id)
            if current["version"] != expected_version:
                raise LocalError("VERSION_CONFLICT", "工作区已变化，请重新预览恢复")
            revision = self.store.preferences(replace_workspace_id)["revision"] + 1
            calendar["version"] = max(calendar["version"], current["version"]) + 1
            for state in self.store.documents("export_state", replace_workspace_id):
                for eid, value in state["events"].items():
                    if (
                        eid not in states
                        or states[eid]["sequence"] <= value["sequence"]
                    ):
                        states[eid] = value
            self.store.safety_backup("restore")
        self.store.externalize(payload["evidence"])
        calendar = self.store.externalize(calendar)
        wid = replace_workspace_id or identity()
        self.store.set_workspace(wid, calendar)
        for key, doc in list(self.store.state["documents"].items()):
            if doc["workspace"] == wid:
                del self.store.state["documents"][key]
        self.store.state["previews"] = {
            k: v
            for k, v in self.store.state["previews"].items()
            if v["workspace"] != wid
        }
        self.store.put("preferences", wid, wid, dict(revision=revision, values=prefs))
        if payload.get("semester"):
            self.store.put("semester", wid, wid, payload["semester"])
        profile_ids = {p["id"]: identity() for p in payload.get("profiles", [])}
        for kind, items in [
            ("template", payload.get("templates", [])),
            ("profile", payload.get("profiles", [])),
            ("export", payload.get("exports", [])),
        ]:
            for item in items:
                item["id"] = (
                    profile_ids[item["id"]] if kind == "profile" else identity()
                )
                item.pop("path", None)
                if kind == "export":
                    item["profile_id"] = profile_ids.get(item.get("profile_id"), "")
                self.store.put(
                    kind, item["id"], "" if kind == "template" else wid, item
                )
        if states:
            self.store.put("export_state", wid, wid, dict(id=wid, events=states))
        del self.restore_tokens[token]
        self.store.collect_evidence()
        return self.workspace(wid)

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

    def ocr_details(self, job_id, file_id):
        _, file = self.job_file(job_id, file_id)
        report = file.get("report") or {}
        return next((f["ocr"] for f in report.get("files", []) if "ocr" in f), {})

    def edit_draft(self, job_id, edits, expected_revision=None):
        with self.jobs.lock:
            job = self.store.document("job", job_id)
            if (
                expected_revision is not None
                and job.get("revision") != expected_revision
            ):
                raise LocalError(
                    "VERSION_CONFLICT",
                    "草稿已被另一个标签页修改，请重新打开任务后再核对",
                )
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
                if edit["values"].get("status") == "confirmed":
                    # Explicit review clears warnings; their original text stays in history.
                    candidate["warnings"] = []
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
            job["report"]["conflicts"] = detect_conflicts(
                [SimpleNamespace(**e) for e in values]
            )
            self.store.put("job", job_id, job["workspace_id"], job)
            return self.get_job(job_id)

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

    def delete_template(self, template_id, expected_revision=None):
        current = self.store.document("template", template_id)
        if (
            expected_revision is not None
            and current.get("revision", 0) != expected_revision
        ):
            raise LocalError("VERSION_CONFLICT", "模板已变化，请刷新后重试")
        self.store.delete("template", template_id)
        return True

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

    def preview_change(
        self,
        workspace_id,
        expected_version,
        operation,
        job_id=None,
        expected_job_revision=None,
    ):
        current = self.store.workspace(workspace_id)["calendar"]
        if current["version"] != expected_version:
            raise LocalError("VERSION_CONFLICT", "日历已变化，请刷新后重新预览")
        operation = deepcopy(operation)
        dependency = None
        if job_id:
            job = self.store.document("job", job_id)
            if (
                expected_job_revision is not None
                and job.get("revision") != expected_job_revision
            ):
                raise LocalError(
                    "VERSION_CONFLICT", "草稿已变化，请重新打开任务后再预览"
                )
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
        report = result.pop("report", {})
        affected = {e["id"] for e in result["summary"]["added"]}
        affected.update(e["id"] for e in result["summary"]["changed"])
        event_by_id = {e["id"]: e for e in report.get("events", [])}
        result["summary"]["schedule_conflicts"] = [
            conflict
            for conflict in report.get("conflicts", [])
            if affected.intersection(conflict["event_ids"])
        ]
        conflict_ids = {
            eid
            for c in result["summary"]["schedule_conflicts"]
            for eid in c["event_ids"]
        }
        result["summary"]["schedule_conflict_events"] = {
            eid: {
                k: event_by_id[eid].get(k)
                for k in ("id", "title", "date", "start", "end", "end_date", "sources")
            }
            for eid in sorted(conflict_ids)
        }
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

    def save_template(
        self, name, rules, description="", template_id=None, expected_revision=None
    ):
        name = name.strip()
        if not name or len(name) > 100 or len(description) > 2000:
            raise LocalError("INVALID_INPUT", "请填写有效模板名称和说明")
        rules = validate_rules(rules)
        if template_id:
            current = self.store.document("template", template_id)
            if (
                expected_revision is not None
                and current.get("revision", 0) != expected_revision
            ):
                raise LocalError("VERSION_CONFLICT", "模板已变化，请刷新后重试")
        value = dict(
            format="calisift.template",
            version=1,
            id=template_id or identity(),
            name=name,
            description=description,
            rules=rules,
        )
        self.store.put("template", value["id"], "", value)
        return self.store.document("template", value["id"])

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
        return encode({k: v for k, v in value.items() if k not in ("id", "revision")})

    def save_profile(
        self,
        workspace_id,
        name,
        options,
        profile_id=None,
        filename="CaliSift-日程.ics",
        expected_revision=None,
    ):
        self.store.workspace(workspace_id)
        if profile_id:
            current = next(
                (
                    p
                    for p in self.store.documents("profile", workspace_id)
                    if p["id"] == profile_id
                ),
                None,
            )
            if (
                not current
                or expected_revision is not None
                and current.get("revision", 0) != expected_revision
            ):
                raise LocalError("VERSION_CONFLICT", "导出方案已变化，请刷新后重试")
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
        return self.store.document("profile", value["id"])

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

    def export_file(
        self,
        workspace_id,
        expected_version,
        options,
        filename="CaliSift-日程.ics",
        profile_id="",
    ):
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 200:
            raise ValueError("请填写有效的导出文件名")
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
            record = dict(
                id=identity(),
                created_at=now(),
                filename=filename,
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
            return {
                **record,
                "download": dict(
                    filename=filename,
                    mime="text/calendar;charset=utf-8",
                    data=base64.b64encode(content).decode("ascii"),
                ),
            }

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

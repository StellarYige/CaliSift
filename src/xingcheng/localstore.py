"""Serializable state. Every command is isolated; IndexedDB commits it using CAS."""

import base64
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import re
from .calendar import empty_calendar, identity, now, validate_calendar


class LocalError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


class LocalStore:
    def __init__(self, state=None):
        self.state = (
            deepcopy(state)
            if state
            else dict(
                schema=1,
                workspaces={},
                documents={},
                previews={},
                evidence={},
                restore_tokens={},
                recovery=[],
            )
        )
        if self.state.get("schema") != 1:
            raise LocalError(
                "SCHEMA_TOO_NEW", "数据来自其他版本，请使用兼容版本；原数据已保留"
            )
        self.lock = nullcontext()

    def connection(self, writing=False):
        return nullcontext()

    def set_workspace(self, wid, calendar):
        validate_calendar(calendar)
        self.state["workspaces"][wid] = dict(
            id=wid,
            name=calendar["personName"],
            version=calendar["version"],
            calendar=deepcopy(calendar),
            updated_at=now(),
        )

    def create_workspace(self, name, calendar=None):
        name = name.strip() if isinstance(name, str) else ""
        calendar = deepcopy(calendar) if calendar else empty_calendar(name)
        if name != calendar["personName"]:
            raise LocalError("INVALID_INPUT", "工作区姓名与日历不一致")
        wid = identity()
        self.set_workspace(wid, calendar)
        from .preferences import from_legacy

        self.put(
            "preferences",
            wid,
            wid,
            dict(revision=0, values=from_legacy(calendar.get("settings", {}))),
        )
        return self.workspace(wid)

    def workspace(self, wid):
        if wid not in self.state["workspaces"]:
            raise LocalError("NOT_FOUND", "工作区不存在，请重新选择")
        return deepcopy(self.state["workspaces"][wid])

    def workspaces(self):
        return [
            {k: v for k, v in w.items() if k != "calendar"}
            for w in sorted(
                self.state["workspaces"].values(),
                key=lambda w: w["updated_at"],
                reverse=True,
            )
        ]

    def document(self, kind, item_id):
        item = self.state["documents"].get(kind + ":" + item_id)
        if item is None:
            raise LocalError("NOT_FOUND", "记录不存在，请刷新后重试")
        return deepcopy(item["body"])

    def documents(self, kind, wid=None):
        return [
            deepcopy(d["body"])
            for d in reversed(list(self.state["documents"].values()))
            if d["kind"] == kind and (wid is None or d["workspace"] == wid)
        ]

    def put(self, kind, item_id, wid, value):
        key = kind + ":" + item_id
        value = deepcopy(value)
        if kind in ("job", "template", "profile"):
            previous = self.state["documents"].get(key, {}).get("body", {})
            value["revision"] = previous.get("revision", 0) + 1
        self.state["documents"].pop(key, None)
        self.state["documents"][key] = dict(
            kind=kind, workspace=wid, body=deepcopy(value)
        )

    def _put(self, db, kind, item_id, wid, value):
        self.put(kind, item_id, wid, value)

    def delete(self, kind, item_id):
        self.state["documents"].pop(kind + ":" + item_id, None)

    def preferences(self, wid):
        self.workspace(wid)
        return self.document("preferences", wid)

    def save_preferences(self, wid, revision, values):
        from .preferences import Preferences

        checked = Preferences.model_validate(values).model_dump()
        previous = self.preferences(wid)
        if previous["revision"] != revision:
            raise LocalError("VERSION_CONFLICT", "偏好已变化，请刷新设置后重试")
        if {c["name"] for c in previous["values"]["categories"]} - {
            c["name"] for c in checked["categories"]
        }:
            raise LocalError("INVALID_INPUT", "已有分类请停用，保留历史名称与配色")
        result = dict(revision=revision + 1, values=checked)
        self.put("preferences", wid, wid, result)
        return result

    def device_preferences(self):
        from .preferences import DevicePreferences

        return (
            self.documents("device_preferences") or [DevicePreferences().model_dump()]
        )[0]

    def save_device_preferences(self, values):
        from .preferences import DevicePreferences

        checked = DevicePreferences.model_validate(
            {**self.device_preferences(), **values}
        ).model_dump()
        self.put("device_preferences", "device", "", checked)
        return checked

    def preview(self, wid, result, dependency=None):
        pid = identity()
        self.state["previews"][pid] = dict(
            workspace=wid, result=deepcopy(result), dependency=dependency, receipt=None
        )
        while len(self.state["previews"]) > 20:
            del self.state["previews"][next(iter(self.state["previews"]))]
        return dict(
            preview_id=pid,
            base_version=result["base_version"],
            summary=result["summary"],
        )

    def commit(self, pid, expected_version):
        preview = self.state["previews"].get(pid)
        if not preview:
            raise LocalError("VERSION_CONFLICT", "预览已失效，请重新预览")
        if preview["receipt"]:
            return preview["receipt"]
        wid, result = preview["workspace"], preview["result"]
        current = self.workspace(wid)
        if (
            current["version"] != expected_version
            or result["base_version"] != expected_version
        ):
            raise LocalError("VERSION_CONFLICT", "日历已变化，请刷新后重新预览")
        dependency = preview["dependency"]
        job = None
        if dependency:
            job = self.document(dependency["kind"], dependency["id"])
            if digest(job) != dependency["digest"]:
                raise LocalError("VERSION_CONFLICT", "导入草稿已变化，请重新预览")
        if result["summary"].get("unresolved"):
            raise LocalError(
                "CONFIRMATION_REQUIRED", "请先处理变更对应关系和个人修正冲突"
            )
        calendar = result["calendar"]
        if calendar["version"] != expected_version + 1:
            raise LocalError("VERSION_CONFLICT", "候选版本无效，请重新预览")
        self.verify_evidence(calendar)
        if current["calendar"].get("settings") != calendar.get("settings"):
            from .preferences import from_legacy

            legacy = from_legacy(calendar.get("settings", {}))
            prefs = self.preferences(wid)
            prefs["values"].update(
                font_size=legacy["font_size"], hide_rest=legacy["hide_rest"]
            )
            palette = {c["name"]: c["color"] for c in legacy["categories"]}
            for category in prefs["values"]["categories"]:
                category["color"] = palette.get(category["name"], category["color"])
            self.put(
                "preferences",
                wid,
                wid,
                dict(revision=prefs["revision"] + 1, values=prefs["values"]),
            )
        self.set_workspace(wid, calendar)
        receipt = dict(
            workspace_id=wid,
            version=calendar["version"],
            preview_id=pid,
            job_id=job["id"] if job else None,
        )
        if job:
            job.update(status="committed", committed_version=calendar["version"])
            self.put("job", job["id"], wid, job)
        preview.update(receipt=receipt, result=None, dependency=None)
        return receipt

    def evidence(self, eid):
        if not isinstance(eid, str) or not re.fullmatch("[a-f0-9]{20}", eid):
            raise LocalError("INVALID_INPUT", "证据编号无效")
        try:
            raw = base64.b64decode(self.state["evidence"][eid], validate=True)
        except (KeyError, ValueError) as exc:
            raise LocalError(
                "EVIDENCE_MISSING", "局部证据缺失，请从完整备份恢复"
            ) from exc
        if hashlib.sha256(raw).hexdigest()[:20] != eid:
            raise LocalError("EVIDENCE_MISSING", "局部证据校验失败，请从完整备份恢复")
        return raw

    def externalize(self, value):
        value = deepcopy(value)

        def walk(item):
            if isinstance(item, list):
                for v in item:
                    walk(v)
            elif isinstance(item, dict):
                for k, v in item.items():
                    if k == "crops" and isinstance(v, dict):
                        for eid, content in v.items():
                            if not content.startswith("evidence:"):
                                raw = base64.b64decode(content, validate=True)
                                if hashlib.sha256(raw).hexdigest()[:20] != eid:
                                    raise LocalError(
                                        "EVIDENCE_MISSING", "图片证据校验失败"
                                    )
                                self.state["evidence"][eid] = content
                            self.evidence(eid)
                            v[eid] = "evidence:" + eid
                    else:
                        walk(v)

        walk(value)
        self.verify_evidence(value)
        return value

    @staticmethod
    def evidence_ids(value):
        ids = set()

        def walk(item):
            if isinstance(item, list):
                for v in item:
                    walk(v)
            elif isinstance(item, dict):
                for k, v in item.items():
                    if (
                        k == "image"
                        and isinstance(v, str)
                        and re.fullmatch("[a-f0-9]{20}", v)
                    ):
                        ids.add(v)
                    elif k == "crops" and isinstance(v, dict):
                        ids.update(v)
                    else:
                        walk(v)

        walk(value)
        return ids

    def verify_evidence(self, value):
        for eid in self.evidence_ids(value):
            self.evidence(eid)

    def collect_evidence(self):
        ids = self.evidence_ids(
            [
                self.state["workspaces"],
                self.state["documents"],
                self.state["recovery"],
                self.state["restore_tokens"],
            ]
        )
        self.state["evidence"] = {
            k: v for k, v in self.state["evidence"].items() if k in ids
        }

    def safety_backup(self, reason="restore"):
        self.state["recovery"] = (
            self.state["recovery"]
            + [
                dict(
                    created_at=now(),
                    workspaces=deepcopy(self.state["workspaces"]),
                    documents={
                        k: deepcopy(v)
                        for k, v in self.state["documents"].items()
                        if v["kind"] != "job"
                    },
                )
            ]
        )[-2:]

"""Portable backups and the read-only v1/v2 WeChat migration boundary."""

import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import PurePosixPath
import zipfile

from .calendar import empty_calendar, identity, new_event, normalized, validate_calendar
from .localstore import LocalError, LocalStore, encode


def fnv_js(text):
    value = 2166136261
    raw = text.encode("utf-16le")
    for offset in range(0, len(raw), 2):
        value = (
            (value ^ int.from_bytes(raw[offset : offset + 2], "little")) * 16777619
        ) & 0xFFFFFFFF
    return format(value, "x")


def migrate_v1(snapshot):
    calendar = empty_calendar(snapshot["personName"])
    sources = {}
    report = snapshot["report"]
    for raw in report["events"] + report["pending"]:
        value = normalized(raw)
        record = new_event(value)
        record["id"] = raw.get("id") or record["id"]
        for evidence in value["sources"]:
            key = evidence["file_id"] or evidence["filename"]
            if key not in sources:
                revision = dict(
                    id=identity(),
                    imported_at=snapshot.get("savedAt", ""),
                    coverage=None,
                    report=dict(
                        events=[], pending=[], files=[], warnings=[], conflicts=[]
                    ),
                )
                sources[key] = dict(
                    id=identity(),
                    name=evidence["filename"],
                    rules={},
                    revisions=[revision],
                )
            source = sources[key]
            if any(c["source_id"] == source["id"] for c in record["contributions"]):
                continue
            original = normalized(
                (value.get("reviews") or [{}])[0].get("before", value)
            )
            original["sources"] = [
                s for s in original["sources"] if (s["file_id"] or s["filename"]) == key
            ]
            record["contributions"].append(
                dict(
                    source_id=source["id"],
                    revision_id=source["revisions"][0]["id"],
                    raw=deepcopy(original),
                    value=deepcopy(original),
                )
            )
            source["revisions"][0]["report"][
                "pending" if original["status"] == "pending" else "events"
            ].append(original)
        if value.get("reviews"):
            record["overrides"] = {
                key: value[key]
                for key in (
                    "date",
                    "title",
                    "shift",
                    "start",
                    "end",
                    "end_date",
                    "precision",
                    "location",
                    "notes",
                    "status",
                )
            }
        calendar["events"].append(record)
    calendar["sources"] = list(sources.values())
    return validate_calendar(calendar)


def pack_backup(store, wid):
    calendar = store.workspace(wid)["calendar"]
    payload = dict(
        format="calisift.backup",
        version=1,
        calendar=calendar,
        templates=store.documents("template"),
        profiles=store.documents("profile", wid),
        exports=store.documents("export", wid),
        export_states=store.documents("export_state", wid),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = {"data.json": encode(payload).encode("utf-8")}
        for eid in store.evidence_ids(calendar):
            entries["evidence/" + eid + ".jpg"] = store.evidence(eid)
        manifest = dict(
            format="calisift.backup",
            version=1,
            files={
                name: hashlib.sha256(data).hexdigest() for name, data in entries.items()
            },
        )
        archive.writestr("manifest.json", encode(manifest))
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def unpack_backup(data):
    if len(data) > 300 * 1024 * 1024:
        raise LocalError("INVALID_INPUT", "备份超过 300 MiB，请使用较小的工作区备份")
    evidence = {}
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.infolist()
            names = [f.filename for f in info]
            if (
                len(info) > 10002
                or len(set(names)) != len(names)
                or sum(f.file_size for f in info) > 300 * 1024 * 1024
            ):
                raise LocalError("INVALID_INPUT", "备份展开后过大或包含重复条目")
            for entry in info:
                name = entry.filename
                if (
                    "\\" in name
                    or ":" in name
                    or PurePosixPath(name).is_absolute()
                    or ".." in PurePosixPath(name).parts
                    or ((entry.external_attr >> 16) & 0o170000) == 0o120000
                ):
                    raise LocalError("INVALID_INPUT", "备份包含不安全的文件路径")
            if "manifest.json" not in names or "data.json" not in names:
                raise LocalError(
                    "INVALID_INPUT", "备份缺少数据清单，请重新选择完整的 CaliSift 备份"
                )
            manifest = json.loads(archive.read("manifest.json"))
            if (
                manifest.get("format") != "calisift.backup"
                or manifest.get("version") != 1
            ):
                raise LocalError("SCHEMA_TOO_NEW", "不支持此备份版本")
            if set(names) != set(manifest["files"]) | {"manifest.json"}:
                raise LocalError("INVALID_INPUT", "备份清单不完整")
            for name, checksum in manifest["files"].items():
                content = archive.read(name)
                if hashlib.sha256(content).hexdigest() != checksum:
                    raise LocalError("INVALID_INPUT", "备份文件校验失败")
                if name.startswith("evidence/"):
                    eid = PurePosixPath(name).stem
                    evidence[eid] = base64.b64encode(content).decode("ascii")
                elif name != "data.json":
                    raise LocalError("INVALID_INPUT", "备份包含不支持的条目")
            payload = json.loads(archive.read("data.json"))
            if (
                payload.get("format") != "calisift.backup"
                or payload.get("version") != 1
            ):
                raise LocalError("SCHEMA_TOO_NEW", "不支持此备份版本")
            calendar = payload["calendar"]
    else:
        payload = json.loads(data.decode("utf-8-sig"))
        if isinstance(payload, dict) and "payload" in payload:
            if not isinstance(payload["payload"], str) or fnv_js(
                payload["payload"]
            ) != payload.get("checksum"):
                raise LocalError("INVALID_INPUT", "旧备份校验失败")
            payload = json.loads(payload["payload"])
        if payload.get("schema") == 2 and "calendar" in payload:
            calendar = payload["calendar"]
        elif payload.get("version") == 1:
            calendar = migrate_v1(payload)
        else:
            raise LocalError(
                "SCHEMA_TOO_NEW", "请选择 CaliSift 备份或星程 v1 / v2 完整备份"
            )

        def collect(item):
            if isinstance(item, list):
                for child in item:
                    collect(child)
            elif isinstance(item, dict):
                for key, child in item.items():
                    if key == "crops" and isinstance(child, dict):
                        for eid, content in child.items():
                            if isinstance(content, str) and not content.startswith(
                                "evidence:"
                            ):
                                evidence[eid] = content
                    else:
                        collect(child)

        collect(payload)
        payload = dict(
            calendar=calendar, templates=[], profiles=[], exports=[], export_states=[]
        )
    validate_calendar(calendar)
    required = LocalStore.evidence_ids(calendar)
    if not required.issubset(evidence):
        raise LocalError(
            "EVIDENCE_MISSING", "备份缺少仍被引用的图片证据，请在旧设备导出完整备份"
        )
    for eid, content in evidence.items():
        if (
            hashlib.sha256(base64.b64decode(content, validate=True)).hexdigest()[:20]
            != eid
        ):
            raise LocalError("EVIDENCE_MISSING", "备份中的图片证据校验失败")
    payload["evidence"] = {"crops": evidence}
    return payload

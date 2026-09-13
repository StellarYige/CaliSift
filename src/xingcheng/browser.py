"""JSON-only worker entrypoints. No server, filesystem persistence or native bridge."""

import base64
import json
from datetime import date
from .application import Application
from .backup import pack_backup
from .localstore import encode
from .processing import execute, apply_report_rules
from .jobs import IMAGES

COMMANDS = {
    "capabilities",
    "workspace",
    "create_workspace",
    "get_job",
    "list_jobs",
    "ocr_details",
    "image_preview",
    "edit_draft",
    "course_draft",
    "get_preferences",
    "save_preferences",
    "device_preferences",
    "last_semester",
    "delete_template",
    "preview_change",
    "commit_change",
    "events",
    "save_template",
    "templates",
    "save_profile",
    "export_preview",
    "export_file",
    "restore_backup",
}


def download(filename, content, mime="application/json"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return dict(
        download=dict(
            filename=filename, data=base64.b64encode(content).decode("ascii"), mime=mime
        )
    )


def dispatch_json(raw):
    request = json.loads(raw)
    app = Application(request.get("state"))
    method, p = request["method"], request.get("payload") or {}
    if method in COMMANDS:
        value = getattr(app, method)(**p)
    elif method == "stage_files":
        value = app.jobs.stage(p["workspace_id"], p["files"])
    elif method == "start_job":
        value = app.jobs.start(**p)
    elif method == "finish_file":
        value = app.jobs.finish(**p)
    elif method == "cancel_job":
        value = app.jobs.cancel(p["job_id"])
    elif method == "discard_job":
        app.jobs.clean(p["job_id"])
        value = True
    elif method == "table":
        value = app.jobs.table(**p)
    elif method in ("profiles", "exports"):
        value = app.store.documents(
            "profile" if method == "profiles" else "export", p["workspace_id"]
        )
    elif method == "evidence":
        value = "data:image/jpeg;base64," + base64.b64encode(
            app.store.evidence(p["id"])
        ).decode("ascii")
    elif method == "backup":
        value = download(
            f"CaliSift-{date.today()}.calisift-backup.zip",
            pack_backup(app.store, p["workspace_id"]),
            "application/zip",
        )
    elif method == "prepare_restore":
        # Bound abandoned previews; none contains an unconfirmed source file.
        app.restore_tokens.clear()
        value = app.prepare_restore(base64.b64decode(p["data"], validate=True))
    elif method == "import_template":
        value = app.import_template(p["data"])
    elif method == "export_template":
        if not p.get("reviewed"):
            raise ValueError("请先检查模板中没有私人表头或姓名")
        value = download("CaliSift-模板.json", app.export_template(p["template_id"]))
    elif method == "export_json":
        job = app.store.document("job", p["job_id"])
        if not job.get("report"):
            raise ValueError("尚无可导出的提取报告")
        value = download(
            "CaliSift-提取报告.json", encode(app._calendar_report(job["report"]))
        )
    elif method == "recovery_points":
        value = [
            dict(
                index=i,
                created_at=r["created_at"],
                workspaces=[
                    dict(id=w["id"], name=w["name"]) for w in r["workspaces"].values()
                ],
            )
            for i, r in enumerate(app.store.state["recovery"])
        ]
    elif method == "recovery_backup":
        from .localstore import LocalStore

        point = app.store.state["recovery"][p["index"]]
        state = {**app.store.state, **point}
        value = download(
            "CaliSift-恢复点.calisift-backup.zip",
            pack_backup(LocalStore(state), p["workspace_id"]),
            "application/zip",
        )
    else:
        raise ValueError("不支持的浏览器操作: " + method)
    if method == "export_preview":
        value.pop("calendar", None)
    return encode(
        dict(
            value=value,
            state=app.store.state,
            changed=app.store.state != request.get("state"),
        )
    )


async def process_json(raw):
    request = json.loads(raw)
    data = base64.b64decode(request.pop("data"), validate=True)
    if request["kind"] == "ocr":
        from .browser_ocr import recognize

        report = await recognize(
            data,
            request["filename"],
            request["name"],
            request["year"],
            {**request.get("options", {}), "include_preview": True},
        )
        result = dict(report=apply_report_rules(report, request.get("rules", {})))
    else:
        result = execute(request, data)
    return encode(result)

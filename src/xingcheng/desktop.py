"""Native desktop boundary: explicit dialogs and a small command allowlist."""

from __future__ import annotations

import base64
from datetime import date
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import webbrowser

from .application import Application
from .assets import AssetServer
from .localstore import LocalError, atomic_write


def data_directory():
    if os.environ.get("CALISIFT_DATA_DIR"):
        return Path(os.environ["CALISIFT_DATA_DIR"]).resolve()
    from platformdirs import user_data_dir

    return Path(user_data_dir("CaliSift", appauthor=False))


class Bridge:
    def __init__(self, app):
        self._app = app
        self._window = None

    def _dialog(self, save=False, filename="", types=(), multiple=False):
        import webview

        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE if save else webview.FileDialog.OPEN,
            save_filename=filename,
            file_types=types,
            allow_multiple=multiple,
        )
        if not result:
            return None
        return result if isinstance(result, (tuple, list)) else [result]

    def call(self, method, payload=None):
        try:
            if self._window is not None and hasattr(self._window, "get_current_url"):
                from .platforms import allowed_origin

                if not allowed_origin(self._window.get_current_url()):
                    raise LocalError("ACCESS_DENIED", "仅允许 CaliSift 本机界面调用")
            value = self._call(method, payload or {})
            return dict(ok=True, value=value)
        except Exception as error:
            code = getattr(
                error,
                "code",
                (
                    "INVALID_INPUT"
                    if isinstance(error, (ValueError, TypeError, KeyError))
                    else "STORAGE_FAILED"
                ),
            )
            message = (
                str(error)
                if isinstance(error, (ValueError, OSError))
                else "操作未完成，请检查输入或本机空间后重试"
            )
            return dict(ok=False, error=dict(code=code, message=message))

    def _call(self, method, p):
        from .desktop_contracts import validate_request

        p = validate_request(method, p)
        app = self._app
        if method == "copy_diagnostics":
            from .platforms import copy_text

            copy_text(
                self._window,
                json.dumps(app.diagnostics(), ensure_ascii=False, indent=2),
            )
            return True
        calls = {
            "capabilities": app.capabilities,
            "get_preferences": app.get_preferences,
            "save_preferences": app.save_preferences,
            "device_preferences": app.device_preferences,
            "delete_template": app.delete_template,
            "last_semester": app.last_semester,
            "diagnostics": app.diagnostics,
            "create_workspace": app.create_workspace,
            "workspace": app.workspace,
            "list_jobs": app.list_jobs,
            "get_job": app.get_job,
            "edit_draft": app.edit_draft,
            "course_draft": app.course_draft,
            "preview_change": app.preview_change,
            "commit_change": app.commit_change,
            "events": app.events,
            "templates": app.templates,
            "save_template": app.save_template,
            "save_profile": app.save_profile,
            "image_preview": app.image_preview,
            "ocr_details": app.ocr_details,
            "restore_backup": app.restore_backup,
        }
        if method in calls:
            return calls[method](**p)
        if method == "select_files":
            paths = self._dialog(
                types=("表格与图片 (*.xlsx;*.xls;*.csv;*.png;*.jpg;*.jpeg)",),
                multiple=True,
            )
            return app.jobs.stage(p["workspace_id"], list(paths)) if paths else None
        if method == "paste_image":
            from PIL import Image, ImageGrab

            value = ImageGrab.grabclipboard()
            if not isinstance(value, Image.Image):
                raise LocalError("INVALID_INPUT", "剪贴板里没有图片，请先复制截图")
            if value.width * value.height > 12_000_000:
                raise LocalError(
                    "INVALID_INPUT", "截图超过 1200 万像素，请裁剪后再复制"
                )
            with tempfile.TemporaryDirectory(prefix="calisift-clipboard-") as folder:
                path = Path(folder) / "剪贴板截图.png"
                value.save(path, format="PNG")
                return app.jobs.stage(p["workspace_id"], [str(path)])
        if method == "sample":
            candidates = [
                Path(getattr(sys, "_MEIPASS", "")) / "samples",
                Path(__file__).resolve().parents[2] / "samples",
            ]
            folder = next((x for x in candidates if x.is_dir()), None)
            if folder is None:
                raise LocalError("NOT_FOUND", "示例文件缺失，请重新安装完整包")
            return app.jobs.stage(
                p["workspace_id"], [str(f) for f in sorted(folder.glob("*.csv"))[:2]]
            )
        if method == "start_job":
            return app.jobs.start(
                p["job_id"],
                p["year"],
                p.get("rules"),
                p.get("source_id", ""),
                p.get("retry_ids"),
                p.get("options"),
            )
        if method == "cancel_job":
            return app.jobs.cancel(p["job_id"])
        if method == "discard_job":
            app.jobs.clean(p["job_id"])
            return True
        if method == "table":
            return app.jobs.table(
                p["job_id"],
                p["file_id"],
                sheet=p.get("sheet", 0),
                row=p.get("row", 0),
                col=p.get("col", 0),
                header_row=p.get("header_row"),
            )
        if method == "evidence":
            return "data:image/jpeg;base64," + base64.b64encode(
                app.store.evidence(p["id"])
            ).decode("ascii")
        if method == "export_preview":
            result = app.export_preview(p["workspace_id"], p["options"])
            result.pop("calendar", None)
            return result
        if method == "export_file":
            paths = self._dialog(
                True, p.get("filename", "CaliSift-日程.ics"), ("日历文件 (*.ics)",)
            )
            return (
                app.export_file(
                    p["workspace_id"],
                    p["expected_version"],
                    p["options"],
                    paths[0],
                    p.get("profile_id", ""),
                )
                if paths
                else None
            )
        if method == "export_json":
            paths = self._dialog(True, "CaliSift-提取报告.json", ("JSON (*.json)",))
            if not paths:
                return None
            job = app.store.document("job", p["job_id"])
            if not job.get("report"):
                raise LocalError("INVALID_INPUT", "尚无可导出的提取报告")
            from .localstore import encode

            atomic_write(
                Path(paths[0]),
                encode(app._calendar_report(job["report"])).encode("utf-8"),
            )
            return dict(filename=Path(paths[0]).name)
        if method in ("profiles", "exports"):
            return app.store.documents(
                "profile" if method == "profiles" else "export", p["workspace_id"]
            )
        if method == "backup":
            paths = self._dialog(
                True, f"CaliSift-{date.today()}.calisift-backup.zip", ("备份 (*.zip)",)
            )
            return app.backup_file(p["workspace_id"], paths[0]) if paths else None
        if method == "prepare_restore":
            paths = self._dialog(types=("日历备份 (*.zip;*.json)",))
            if not paths:
                return None
            path = Path(paths[0])
            if path.stat().st_size > 300 * 1024 * 1024:
                raise LocalError("INVALID_INPUT", "备份超过 300 MiB")
            return app.prepare_restore(path.read_bytes())
        if method == "import_template":
            paths = self._dialog(types=("规则模板 (*.json)",))
            if not paths:
                return None
            path = Path(paths[0])
            if path.stat().st_size > 256 * 1024:
                raise LocalError("INVALID_INPUT", "模板超过 256 KiB")
            return app.import_template(path.read_text(encoding="utf-8-sig"))
        if method == "export_template":
            if not p.get("reviewed"):
                raise LocalError(
                    "CONFIRMATION_REQUIRED", "请先检查模板中没有私人表头或姓名"
                )
            content = app.export_template(p["template_id"])
            paths = self._dialog(True, "CaliSift-模板.json", ("规则模板 (*.json)",))
            if paths:
                atomic_write(Path(paths[0]), content.encode("utf-8"))
            return bool(paths)
        if method == "model_repair":
            paths = self._dialog(types=("离线模型包 (*.zip)",))
            if not paths:
                return None
            from .modelpack import install_pack

            return install_pack(Path(paths[0]), app.store.root / "models")
        if method == "open_export":
            record = app.store.document("export", p["export_id"])
            if not record.get("path") or not Path(record["path"]).is_file():
                raise LocalError("NOT_FOUND", "此设备没有该导出文件，请重新导出")
            from .platforms import open_folder

            open_folder(Path(record["path"]).parent)
            return True
        if method == "open_project":
            webbrowser.open("https://github.com/StellarYige/CaliSift")
            return True
        raise LocalError("INVALID_INPUT", "不支持的桌面操作")


def main(data_dir=None, on_ready=None):
    import webview
    from webview.dom import DOMEventHandler

    root = Path(data_dir) if data_dir else data_directory()
    model_path = root / "model-path.txt"
    if model_path.is_file() or (root / "models").is_dir():
        from . import ocr

        ocr.MODEL_DIR = (
            Path(model_path.read_text(encoding="utf-8"))
            if model_path.is_file()
            else root / "models"
        )
        os.environ["XINGCHENG_OCR_MODELS"] = str(ocr.MODEL_DIR)
    app = Application(root)
    bridge = Bridge(app)
    packaged = Path(getattr(sys, "_MEIPASS", "")) / "desktop-ui" / "index.html"
    source = Path(__file__).resolve().parents[2] / "desktop" / "dist" / "index.html"
    entry = packaged if getattr(sys, "frozen", False) else source
    if not entry.is_file():
        app.close()
        raise RuntimeError("桌面界面尚未构建，请先运行 npm run build:desktop")
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    device = app.store.device_preferences()
    window = webview.create_window(
        "CaliSift · 星程",
        str(entry),
        js_api=bridge,
        width=device["width"],
        height=device["height"],
        min_size=(640, 420),
        text_select=True,
        background_color="#f7f7fb",
    )
    bridge._window = window
    navigation_hooked = False
    ready_called = False

    def dropped(event):
        try:
            paths = [
                item["pywebviewFullPath"] for item in event["dataTransfer"]["files"]
            ]
            wid = window.evaluate_js('window.calisiftWorkspace || ""')
            if not wid:
                raise ValueError("请先建立工作区")
            value = dict(job=app.jobs.stage(wid, paths))
        except Exception as exc:
            value = dict(error=str(exc))
        window.evaluate_js(
            'window.dispatchEvent(new CustomEvent("calisift-drop", {detail:'
            + json.dumps(value, ensure_ascii=True)
            + "}))"
        )

    def loaded():
        nonlocal ready_called
        window.dom.document.events.dragover += DOMEventHandler(
            lambda event: None, prevent_default=True
        )
        window.dom.document.events.drop += DOMEventHandler(
            dropped, prevent_default=True
        )
        if on_ready and not ready_called:
            ready_called = True
            on_ready(window, bridge)

    def shown():
        nonlocal navigation_hooked
        if sys.platform == "darwin" and not navigation_hooked:
            from .platforms import protect_cocoa

            protect_cocoa(window)
            navigation_hooked = True
        if os.name == "nt" and not navigation_hooked:
            from System import Action, EventHandler
            from Microsoft.Web.WebView2.Core import (
                CoreWebView2NavigationStartingEventArgs,
            )

            def navigation(sender, args):
                from urllib.parse import urlsplit

                url = urlsplit(str(args.Uri))
                allowed = any(
                    url.scheme == "http" and url.netloc == f"127.0.0.1:{s.port}"
                    for s in AssetServer.instances
                    if s.running
                )
                if not allowed:
                    args.Cancel = True

            window.native.Invoke(
                Action(
                    lambda: window.native.webview.CoreWebView2.add_NavigationStarting(
                        EventHandler[CoreWebView2NavigationStartingEventArgs](
                            navigation
                        )
                    )
                )
            )
            navigation_hooked = True

    def resized(width, height):
        if 640 <= width <= 7680 and 420 <= height <= 4320:
            app.store.save_device_preferences(dict(width=width, height=height))

    # CoreWebView2 is initialized by the time the first local page has loaded.
    window.events.loaded += shown
    window.events.loaded += loaded
    window.events.resized += resized
    window.events.closed += app.close
    try:
        webview.start(
            gui="edgechromium" if os.name == "nt" else None,
            private_mode=True,
            server=AssetServer,
        )
    finally:
        app.close()
        for server in AssetServer.instances:
            server.close()


def launch():
    try:
        main()
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError))
            else "启动失败。请检查数据目录和 WebView2 运行时，原数据不会自动删除。"
        )
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                message + "\n\n数据目录：" + str(data_directory()),
                "CaliSift 无法启动",
                0x10,
            )
        else:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(launch())

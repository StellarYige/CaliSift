"""Native boundary allowlist, cancellation, CLI and model repair contracts."""

import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error
import urllib.request
import zipfile

import pytest
from PIL import Image

from xingcheng.assets import AssetServer
from xingcheng.cli import main as cli
from xingcheng.desktop import Bridge, data_directory
from xingcheng.desktop_worker import main as worker_main, execute
from xingcheng import modelpack
from xingcheng.localstore import LocalError, encode
from tests.test_desktop_store import local, imported, draft, change


def test_assets_serve_only_bundled_files_without_business_http(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<h1>Local</h1>")
    (ui / "secret.txt").write_text("do not serve")
    (tmp_path / "private.html").write_text("outside")
    address, root, server = AssetServer.start_server([str(ui / "index.html")])
    try:
        assert (
            server.is_running
            and root == str(ui.resolve())
            and server.js_api_endpoint is None
        )
        assert urllib.request.urlopen(address).read() == b"<h1>Local</h1>"
        for path in (
            "../private.html",
            "%2e%2e/private.html",
            "secret.txt",
            "missing.js",
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(address + path)
            assert error.value.code == 404
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(
                urllib.request.Request(address, headers={"Host": "untrusted.example"})
            )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(
                urllib.request.Request(address + "js_api", data=b"{}")
            )
    finally:
        server.close()
    server.close()
    assert not server.is_running


def test_offline_repair_validates_all_files_before_activation(tmp_path, monkeypatch):
    values = {"model.onnx": b"pinned model", "font.ttf": b"pinned font"}
    manifest = {k: hashlib.sha256(v).hexdigest() for k, v in values.items()}
    monkeypatch.setattr(modelpack, "resources", lambda: manifest)
    monkeypatch.setattr(modelpack.ocr, "readiness", lambda: {"ready": True})
    monkeypatch.setattr(modelpack.ocr, "MODEL_DIR", tmp_path / "old")
    monkeypatch.setenv("XINGCHENG_OCR_MODELS", str(tmp_path / "old"))
    source = tmp_path / "source"
    source.mkdir()
    for name, data in values.items():
        (source / name).write_bytes(data)
    pack = tmp_path / "models.zip"
    modelpack.create_pack(source, pack)
    assert modelpack.install_pack(pack, tmp_path / "models")["ready"]
    active = (tmp_path / "model-path.txt").read_text(encoding="utf-8")
    assert Path(active, "model.onnx").read_bytes() == values["model.onnx"]
    for mode in ("missing", "tampered"):
        with zipfile.ZipFile(pack, "w") as z:
            for name, data in values.items():
                if mode == "missing" and name == "font.ttf":
                    continue
                z.writestr(name, b"altered" if name == "model.onnx" else data)
        with pytest.raises(LocalError):
            modelpack.install_pack(pack, tmp_path / "models")
        assert (tmp_path / "model-path.txt").read_text(encoding="utf-8") == active
    (source / "font.ttf").write_bytes(b"bad")
    with pytest.raises(LocalError):
        modelpack.create_pack(source, pack)


def test_bridge_allowlist_and_cancelled_dialogs(local, monkeypatch):
    app, wid = local
    bridge = Bridge(app)
    monkeypatch.setattr(bridge, "_dialog", lambda *a, **k: None)
    assert (
        bridge.call("workspace", {"workspace_id": wid})["value"]["name"] == "星辰奕歌"
    )
    assert bridge.call("capabilities")["value"]["ocr"]["model"]
    assert not bridge.call("shell", {"command": "anything"})["ok"]
    assert not bridge.call("workspace", {})["ok"]
    actions = [
        "select_files",
        "export_file",
        "export_json",
        "backup",
        "prepare_restore",
        "import_template",
        "model_repair",
    ]
    for action in actions:
        result = bridge.call(action, {"workspace_id": wid})
        assert result["ok"] and result["value"] is None, (action, result)
    assert not app.list_jobs(wid) and not app.store.documents("export", wid)
    with pytest.raises(LocalError):
        bridge._call("export_template", {})


def test_bridge_export_template_report_backup_restore_and_project(
    local, tmp_path, monkeypatch
):
    app, wid = local
    monkeypatch.setattr("xingcheng.desktop.webbrowser.open", Mock(return_value=True))
    bridge = Bridge(app)
    imported(app, wid)
    output = tmp_path / "output"
    monkeypatch.setattr(bridge, "_dialog", lambda *a, **k: [str(output)])
    result = bridge.call("export_preview", dict(workspace_id=wid, options={}))
    assert "calendar" not in result["value"] and result["value"]["count"] == 1
    record = bridge._call(
        "export_file", dict(workspace_id=wid, expected_version=1, options={})
    )
    assert output.read_bytes().startswith(b"BEGIN:VCALENDAR")
    assert len(bridge._call("exports", dict(workspace_id=wid))) == 1
    monkeypatch.setattr("xingcheng.desktop.os.startfile", Mock(), raising=False)
    assert bridge._call("open_export", {"export_id": record["id"]})
    output.unlink()
    with pytest.raises(LocalError):
        bridge._call("open_export", {"export_id": record["id"]})
    jid = draft(app, wid)
    bridge._call("export_json", {"job_id": jid})
    assert json.loads(output.read_text(encoding="utf-8"))["events"]
    bridge._call("backup", {"workspace_id": wid})
    restored = bridge._call("prepare_restore", {})
    assert restored["events"] == 1
    template = app.save_template("共享", {})
    assert bridge._call(
        "export_template", dict(template_id=template["id"], reviewed=True)
    )
    assert bridge._call("import_template", {})["name"] == "共享"
    monkeypatch.setattr("xingcheng.desktop.webbrowser.open", Mock(return_value=True))
    assert bridge._call("open_project", {})
    assert bridge._call("profiles", {"workspace_id": wid}) == []
    with pytest.raises(LocalError):
        bridge._call("export_json", {"job_id": app.list_jobs(wid)[-1]["id"]})


def test_bridge_native_input_handles(local, tmp_path, monkeypatch):
    app, wid = local
    bridge = Bridge(app)
    monkeypatch.setattr(
        bridge, "_dialog", lambda *a, **k: [str(Path("samples/九月排班.csv").resolve())]
    )
    job = bridge._call("select_files", {"workspace_id": wid})
    fid = job["files"][0]["id"]
    table = bridge._call("table", dict(job_id=job["id"], file_id=fid, header_row=0))
    assert table["headers"][0] == "姓名"
    with pytest.raises(LocalError):
        app.image_preview(job["id"], fid)
    bridge._call("cancel_job", {"job_id": job["id"]})
    assert bridge._call("discard_job", {"job_id": job["id"]})
    sample = bridge._call("sample", {"workspace_id": wid})
    assert len(sample["files"]) == 2
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard", lambda: None)
    assert not bridge.call("paste_image", {"workspace_id": wid})["ok"]
    monkeypatch.setattr(
        "PIL.ImageGrab.grabclipboard", lambda: Image.new("RGB", (50, 50), "white")
    )
    pasted = bridge._call("paste_image", {"workspace_id": wid})
    assert pasted["files"][0]["filename"] == "剪贴板截图.png"
    payload = b"crop"
    eid = hashlib.sha256(payload).hexdigest()[:20]
    app.store.externalize({"crops": {eid: base64.b64encode(payload).decode()}})
    assert bridge._call("evidence", {"id": eid}).endswith(
        base64.b64encode(payload).decode()
    )
    fake = Mock()
    fake.create_file_dialog.return_value = str(tmp_path / "file")
    bridge._window = fake
    # Exercise actual dialog argument adaptation, without opening a user dialog in pytest.
    assert Bridge._dialog(bridge, True, "schedule.ics", ("ICS (*.ics)",)) == [
        str(tmp_path / "file")
    ]
    fake.create_file_dialog.return_value = None
    assert Bridge._dialog(bridge) is None
    fake.create_file_dialog.return_value = ("a", "b")
    assert Bridge._dialog(bridge, multiple=True) == ("a", "b")


def test_cli_full_preview_commit_export_restore_and_bad_request(tmp_path, capsys):
    directory = str(tmp_path / "cli")
    prefix = ["--data-dir", directory]
    assert cli(prefix + ["doctor"]) == 0
    diagnostics = json.loads(capsys.readouterr().out)
    assert diagnostics["limits"]["files"] == 10
    assert "ready" in diagnostics["ocr"]
    assert cli(prefix + ["workspace", "--create", "星辰奕歌"]) == 0
    wid = json.loads(capsys.readouterr().out)["id"]
    assert cli(prefix + ["workspace"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert (
        cli(["parse", "samples/九月排班.csv", "--name", "星辰奕歌", "--year", "2026"])
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["events"]) == 2
    assert (
        cli(
            prefix
            + ["import", "samples/九月排班.csv", "--workspace", wid, "--year", "2026"]
        )
        == 0
    )
    job = json.loads(capsys.readouterr().out)["job_id"]
    operation = tmp_path / "operation.json"
    operation.write_text('{"type":"append","source_name":"Work"}')
    assert (
        cli(
            prefix
            + [
                "change",
                "--workspace",
                wid,
                "--operation",
                str(operation),
                "--job",
                job,
                "--expected-version",
                "0",
                "--commit",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["committed"]["version"] == 1
    target = tmp_path / "calendar.ics"
    assert cli(prefix + ["export", "--workspace", wid, "--output", str(target)]) == 0
    capsys.readouterr()
    assert "UID:" in target.read_text(encoding="utf-8")
    backup = tmp_path / "backup.zip"
    assert cli(prefix + ["backup", "--workspace", wid, "--output", str(backup)]) == 0
    capsys.readouterr()
    assert cli(prefix + ["restore", str(backup)]) == 0
    assert json.loads(capsys.readouterr().out)["events"] == 2
    assert cli(prefix + ["restore", str(backup), "--commit"]) == 0
    capsys.readouterr()
    assert cli(["parse", "missing", "--name", "星辰奕歌"]) == 1
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "OPERATION_FAILED"


def test_worker_protocol_unicode_and_errors(monkeypatch, tmp_path):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                dict(
                    kind="table",
                    path=str(Path("samples/九月排班.csv").resolve()),
                    filename="排班.csv",
                )
            )
        ),
    )
    worker_main()
    assert json.loads(stdout.getvalue())["sheet"] == "CSV"
    stdout.seek(0)
    stdout.truncate()
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid json"))
    worker_main()
    assert "error" in json.loads(stdout.getvalue())


def test_desktop_directory_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CALISIFT_DATA_DIR", str(tmp_path))
    assert data_directory() == tmp_path
    monkeypatch.delenv("CALISIFT_DATA_DIR")
    assert data_directory().name == "CaliSift"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native WebView2 boundary")
def test_window_lifecycle_restricts_navigation_and_routes_native_drop(
    tmp_path, monkeypatch
):
    from xingcheng import desktop, ocr

    class Event:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

    events = SimpleNamespace(loaded=Event(), closed=Event())
    document = SimpleNamespace(events=SimpleNamespace(dragover=Event(), drop=Event()))
    core = Mock()
    native = SimpleNamespace(
        Invoke=lambda fn: fn(), webview=SimpleNamespace(CoreWebView2=core)
    )
    window = SimpleNamespace(
        events=events,
        dom=SimpleNamespace(document=document),
        native=native,
        evaluate_js=Mock(),
    )
    fake = SimpleNamespace(settings={}, create_window=Mock(return_value=window))
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setitem(
        sys.modules,
        "webview.dom",
        SimpleNamespace(DOMEventHandler=lambda callback, **k: callback),
    )

    class GenericDelegate:
        def __getitem__(self, kind):
            return lambda fn: fn

    monkeypatch.setitem(
        sys.modules,
        "System",
        SimpleNamespace(Action=lambda f: f, EventHandler=GenericDelegate()),
    )
    monkeypatch.setitem(
        sys.modules,
        "Microsoft.Web.WebView2.Core",
        SimpleNamespace(CoreWebView2NavigationStartingEventArgs=object),
    )

    def start(**kwargs):
        assert kwargs["server"] is AssetServer
        events.loaded.handlers[0]()
        events.loaded.handlers[1]()
        args = SimpleNamespace(Uri="https://untrusted.example/", Cancel=False)
        core.add_NavigationStarting.call_args.args[0](None, args)
        assert args.Cancel
        document.events.drop.handlers[0](
            {
                "dataTransfer": {
                    "files": [
                        {
                            "pywebviewFullPath": str(
                                Path("samples/九月排班.csv").resolve()
                            )
                        }
                    ]
                }
            }
        )
        document.events.drop.handlers[0]({"dataTransfer": {"files": [{}]}})

    fake.start = start

    def ready(window, bridge):
        wid = bridge._app.create_workspace("星辰奕歌")["id"]
        window.evaluate_js.return_value = wid

    # The real UI build is not needed to exercise native lifecycle failures in CI.
    entry = tmp_path / "bundle/desktop-ui"
    entry.mkdir(parents=True)
    (entry / "index.html").write_text("<html></html>")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(entry.parent), raising=False)
    model = tmp_path / "models"
    model.mkdir()
    (tmp_path / "model-path.txt").write_text(str(model), encoding="utf-8")
    monkeypatch.setattr(ocr, "MODEL_DIR", ocr.MODEL_DIR)
    monkeypatch.setenv("XINGCHENG_OCR_MODELS", str(ocr.MODEL_DIR))
    desktop.main(tmp_path, ready)
    assert window.evaluate_js.call_count >= 3
    assert not list((tmp_path / "jobs").glob("*.tmp"))
    (entry / "index.html").unlink()
    with pytest.raises(RuntimeError, match="尚未构建"):
        desktop.main(tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native startup dialog")
def test_startup_error_has_recovery_guidance(monkeypatch):
    from xingcheng import desktop
    import ctypes

    message = Mock()
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", message)
    monkeypatch.setattr(
        desktop, "main", lambda: (_ for _ in ()).throw(OSError("storage failure"))
    )
    assert desktop.launch() == 1
    assert "原数据" in message.call_args.args[1]
    monkeypatch.setattr(desktop, "main", lambda: None)
    assert desktop.launch() == 0

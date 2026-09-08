"""Explicit --self-check diagnostic: real UI workflow in a temporary workspace."""

import json
import os
from pathlib import Path
import tempfile
import time


def run():
    from .desktop import main

    result = {"success": False, "native_dialogs_verified": False}
    output = Path(os.environ["CALISIFT_CHECK_OUTPUT"]).resolve()
    with tempfile.TemporaryDirectory(prefix="calisift-check-") as directory:

        def ready(window, bridge):
            def wait_for(script, seconds=40):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    if window.evaluate_js(script):
                        return
                    time.sleep(0.15)
                raise RuntimeError("UI step timed out: " + script[:100])

            def click(label):
                expression = (
                    "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes("
                    + json.dumps(label)
                    + ")&&!b.disabled)"
                )
                wait_for("Boolean(" + expression + ")")
                window.evaluate_js("(" + expression + ").click()")

            try:
                click("先用示例体验")
                click("开始识别")
                click("预览并加入日历")
                click("确认保存")
                wait_for("document.body.textContent.includes('安排已保存')")
                app = bridge._app
                wid = app.store.workspaces()[0]["id"]
                events = app.events(wid)["items"]
                if len(events) != 4:
                    raise RuntimeError("Expected four sample events")
                options = dict(alarm=15)
                exported = Path(directory) / "calendar.ics"
                app.export_file(wid, app.workspace(wid)["version"], options, exported)
                if exported.read_text(encoding="utf-8").count("BEGIN:VEVENT") != 4:
                    raise RuntimeError("Calendar export incomplete")
                app.backup_file(wid, str(Path(directory) / "backup.zip"))
                result.update(
                    success=True,
                    events=4,
                    ids=[e["id"] for e in events],
                    ui_import_confirm=True,
                    export=True,
                    backup=True,
                )
                # Reading through a fresh database connection verifies committed persistence.
                from .localstore import LocalStore

                reopened = LocalStore(directory)
                assert {
                    e["id"] for e in reopened.workspace(wid)["calendar"]["events"]
                } == set(result["ids"])
                result["reopen_persistence"] = True
            except Exception as error:
                result["error"] = str(error)
                result["ui_state"] = window.evaluate_js(
                    "({url:location.href,title:document.title,text:document.body.innerText,bridge:!!window.pywebview})"
                )
                result["native_capabilities"] = bridge.call("capabilities")
            finally:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                window.destroy()

        main(directory, ready)
    return 0 if result["success"] else 1

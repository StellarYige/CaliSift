"""Native WebView2 smoke test using real application services and worker processes."""

import json
import os
from pathlib import Path
import sys
import time
import traceback

from xingcheng.desktop import main

OUT = Path("artifacts/desktop-smoke").resolve()
OUT.mkdir(parents=True, exist_ok=True)


def ready(window, bridge):
    def wait(expression, timeout=30):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            value = window.evaluate_js(expression)
            if value:
                return value
            time.sleep(0.15)
        raise AssertionError("UI condition not reached: " + expression)

    def click(text):
        return window.evaluate_js(
            "(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==="
            + json.dumps(text)
            + ");if(!b)throw Error('Button missing');b.click();return true})()"
        )

    def capture(name):
        from System import Action
        from System.IO import FileStream, FileMode
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

        stream = FileStream(str(OUT / (name + ".png")), FileMode.Create)
        tasks = []
        window.native.Invoke(
            Action(
                lambda: tasks.append(
                    window.native.webview.CoreWebView2.CapturePreviewAsync(
                        CoreWebView2CapturePreviewImageFormat.Png, stream
                    )
                )
            )
        )
        tasks[0].Wait()
        stream.Dispose()

    try:
        wait("!!document.querySelector('.onboarding')")
        window.evaluate_js(
            "(()=>{location.href='https://example.invalid/blocked';return true})()"
        )
        time.sleep(1)
        print(
            "After rejected navigation", window.evaluate_js("location.href"), flush=True
        )
        assert window.evaluate_js(
            "location.protocol==='http:' && location.hostname==='127.0.0.1'"
        )
        capture("onboarding")
        click("先用示例体验")
        wait("document.querySelectorAll('.file-tabs button').length===2")
        click("开始识别")
        wait("document.querySelectorAll('.draft-list .event-row').length===4", 60)
        wait("!!document.querySelector('.source-table')")
        window.evaluate_js(
            "document.querySelector('.review-grid').scrollIntoView({block:'start'})"
        )
        capture("workbench")
        click("预览并加入日历")
        wait("!!document.querySelector('.modal')")
        (OUT / "preview-text.txt").write_text(
            window.evaluate_js("document.body.innerText"), encoding="utf-8"
        )
        buttons = window.evaluate_js(
            "[...document.querySelectorAll('.modal button')].map(x=>x.textContent.trim())"
        )
        print("preview buttons", json.dumps(buttons, ensure_ascii=True), flush=True)
        capture("preview")
        click("确认保存")
        wait("!document.querySelector('.modal')")
        wait("!!document.querySelector('.welcome-grid')")
        window.evaluate_js(
            "[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('安排')).click()"
        )
        wait(
            "!!document.querySelector('h1')&&document.querySelector('h1').textContent==='安排预览'"
        )
        wait("document.body.innerText.includes('急救培训')")
        capture("events")
        window.resize(720, 640)
        time.sleep(0.5)
        window.evaluate_js("document.documentElement.style.fontSize='17px'")
        capture("events-narrow-large")
        assert window.evaluate_js("document.documentElement.scrollWidth<=innerWidth+1")
        window.resize(1280, 720)
        time.sleep(0.5)
        capture("events-large")
        assert (
            bridge._app.workspace(window.evaluate_js("window.calisiftWorkspace"))[
                "count"
            ]
            == 4
        )
        result = dict(
            passed=True,
            items=4,
            renderer="WebView2",
            workflow="onboarding → sample → real parse → preview → commit → events → narrow / large text",
            ui_text=window.evaluate_js("document.body.innerText"),
        )
        (OUT / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("NATIVE SMOKE PASSED", flush=True)
    except Exception:
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), flush=True)
        try:
            capture("failure")
        except Exception:
            pass
    finally:
        window.destroy()


if __name__ == "__main__":
    import tempfile

    (OUT / "result.json").unlink(missing_ok=True)
    (OUT / "error.txt").unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="calisift-native-") as directory:
        main(directory, ready)
    if not (OUT / "result.json").is_file():
        raise SystemExit(1)

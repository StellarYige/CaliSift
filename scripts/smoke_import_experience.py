"""Windows source-build UI regression with synthetic fixtures and isolated local data.

Uses real WebView2, workers, SQLite and export bridge. Only the save-dialog path
is supplied by the test; native dialogs, drag/drop and calendar clients are NOT tested.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback

from xingcheng.desktop import main

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT / "artifacts" / "import-experience" / datetime.now().strftime("%Y%m%d-%H%M%S")
)


def ready(window, bridge):
    completed = []
    captures = {}
    bridge_errors = []
    native_call = bridge._call

    def traced_call(method, payload):
        try:
            return native_call(method, payload)
        except Exception as exc:
            bridge_errors.append(dict(method=method, error=str(exc)))
            raise

    bridge._call = traced_call

    def wait(expression, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if value := window.evaluate_js(expression):
                return value
            time.sleep(0.15)
        raise AssertionError("UI condition not reached: " + expression)

    def click(label, selector="button"):
        wait(
            "[...document.querySelectorAll("
            + json.dumps(selector)
            + ")].some(b=>b.textContent.trim()==="
            + json.dumps(label)
            + "&&!b.disabled)"
        )
        window.evaluate_js(
            "(()=>{const b=[...document.querySelectorAll("
            + json.dumps(selector)
            + ")].find(b=>b.textContent.trim()==="
            + json.dumps(label)
            + ");if(!b || b.disabled)throw Error('Button unavailable');b.click()})()"
        )

    def select_filter(value):
        window.evaluate_js(
            "(()=>{const s=document.querySelector('[aria-label=核对范围]');s.value="
            + json.dumps(value)
            + ";s.dispatchEvent(new Event('change',{bubbles:true}))})()"
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
        captures[name] = window.evaluate_js(
            "({width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio})"
        )

    def edit(title, values):
        window.evaluate_js(
            "(()=>{const row=[...document.querySelectorAll('.event-row')].find(r=>r.querySelector('h3').textContent==="
            + json.dumps(title)
            + ");[...row.querySelectorAll('button')].find(b=>b.textContent.trim()==='修正').click()})()"
        )
        wait("!!document.querySelector('.modal form')")
        window.evaluate_js(
            "(()=>{const values="
            + json.dumps(values)
            + ";for(const [label,value] of Object.entries(values)){"
            "const l=[...document.querySelectorAll('.modal label')].find(l=>l.firstChild.textContent.trim()===label);"
            "const input=l.querySelector('input,select');input.value=value;"
            "input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));}})()"
        )
        click("保存修正", ".modal button")
        wait("!document.querySelector('.modal')")

    result = dict(
        passed=False,
        timestamp=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(),
        python=platform.python_version(),
        renderer="WebView2",
        build="source",
        provenance="synthetic",
        real_anonymized_samples=0,
        native_file_dialogs_tested=False,
        native_drag_drop_tested=False,
        external_calendar_clients_tested=[],
        completed=completed,
        measured_capture_viewports=captures,
        bridge_errors=bridge_errors,
    )
    try:
        wait("!!document.querySelector('.onboarding')")
        click("先用示例体验")
        wait("document.querySelectorAll('.file-tabs button').length===2")
        click("开始识别")
        wait("document.querySelectorAll('.draft-list .event-row').length===4")
        click("查看原文", ".draft-list button")
        wait("!!document.querySelector('.evidence-context blockquote')")
        assert window.evaluate_js(
            "!!document.querySelector('.source-table td.highlight')"
        )
        completed.append(
            "Built-in CSV samples parsed by real workers; source evidence highlighted"
        )

        wid = window.evaluate_js("window.calisiftWorkspace")
        click("预览并加入日历")
        wait("!!document.querySelector('.modal')")
        click("确认保存", ".modal button")
        wait("!document.querySelector('.modal')")
        assert bridge._app.workspace(wid)["count"] == 4
        staged = bridge._app.jobs.stage(
            wid,
            [
                str(ROOT / "tests/fixtures/冲突与重复.xlsx"),
                str(ROOT / "tests/fixtures/周期课表待确认.xlsx"),
            ],
        )
        # The application event passes a genuinely staged job, not a browser mock.
        window.evaluate_js(
            "window.dispatchEvent(new CustomEvent('calisift-drop',{detail:{job:"
            + json.dumps(staged)
            + "}}))"
        )
        wait(
            "document.querySelector('.file-tabs').textContent.includes('周期课表待确认')"
        )
        click("开始识别")
        wait(
            "document.querySelector('.review-counts')?.textContent.includes('2 项涉及冲突')"
        )
        select_filter("conflicts")
        wait("document.querySelectorAll('.draft-list .event-row').length===2")
        click("查看原文", ".draft-list button")
        wait(
            "document.querySelector('.evidence-context')?.textContent.includes('冲突与重复.xlsx')"
        )
        wait(
            "(()=>{const cell=document.querySelector('td[data-coordinate=B2]');"
            "if(!cell)return false;const box=cell.getBoundingClientRect();"
            "return box.left>=cell.parentElement.querySelector('th').getBoundingClientRect().right})()"
        )
        window.evaluate_js(
            "document.querySelector('.review-grid').scrollIntoView({block:'start'})"
        )
        capture("review-wide")
        window.resize(720, 760)
        window.evaluate_js(
            "document.documentElement.style.fontSize='20px';document.documentElement.dataset.theme='dark'"
        )
        time.sleep(0.5)
        assert window.evaluate_js("document.documentElement.scrollWidth<=innerWidth+1")
        window.evaluate_js(
            "document.querySelector('.draft-panel').scrollIntoView({block:'start'})"
        )
        capture("review-narrow-dark-20")
        window.resize(1280, 820)
        window.evaluate_js(
            "document.documentElement.style.fontSize='14px';document.documentElement.dataset.theme='light'"
        )
        edit("应急演练", {"开始时间": "16:00"})
        wait(
            "document.querySelector('.review-counts')?.textContent.includes('0 项涉及冲突')"
        )
        completed.append(
            "Definite conflict filter and source lookup; editing refreshes conflict count"
        )

        select_filter("pending")
        wait("document.querySelectorAll('.draft-list .event-row').length===1")
        pending_title = window.evaluate_js(
            "document.querySelector('.draft-list h3').textContent"
        )
        click("查看原文", ".draft-list button")
        wait(
            "document.querySelector('.evidence-context')?.textContent.includes('周期课表待确认.xlsx')"
        )
        edit(
            pending_title,
            {
                "日期": "2026-09-08",
                "开始时间": "09:00",
                "结束时间": "10:00",
                "核对状态": "confirmed",
            },
        )
        wait(
            "document.querySelector('.review-counts')?.textContent.includes('0 项待确认')"
        )
        select_filter("all")
        click("预览并加入日历")
        wait("!!document.querySelector('.modal')")
        assert window.evaluate_js(
            "document.querySelector('.preview-conflicts')?.textContent.includes('含已保存安排')"
        )
        window.evaluate_js(
            "document.querySelector('.preview-conflicts details').open=true"
        )
        assert window.evaluate_js(
            "document.querySelectorAll('.preview-conflicts blockquote').length===2"
        )
        capture("conflict-with-saved-preview")
        completed.append(
            "Import preview exposes overlap with an already saved sample and both original excerpts"
        )
        click("确认保存", ".modal button")
        wait("!document.querySelector('.modal')")
        click("继续导出日历")
        wait("!!document.querySelector('.export-help')")
        click("查看导出预览")
        wait("document.body.innerText.includes('本次可导出 7 项')")
        assert window.evaluate_js(
            "document.querySelectorAll('.snapshot-notice').length===2"
        )
        completed.append(
            "Missing date/time reviewed in UI; three events committed to local SQLite"
        )

        target = OUT / "synthetic-snapshot.ics"
        bridge._dialog = lambda *args, **kwargs: (str(target),)
        click("保存 ICS 文件")
        wait("document.body.innerText.includes('ICS 安排快照已保存')")
        exported = target.read_text(encoding="utf-8")
        assert exported.count("BEGIN:VEVENT") == 7
        assert "DTSTART;TZID=Asia/Shanghai:20260907T160000" in exported
        window.evaluate_js(
            "document.querySelector('.page-stack').scrollIntoView({block:'start'})"
        )
        capture("export-wide")
        window.resize(720, 760)
        window.evaluate_js(
            "document.documentElement.style.fontSize='20px';document.documentElement.dataset.theme='dark'"
        )
        time.sleep(0.5)
        assert window.evaluate_js("document.documentElement.scrollWidth<=innerWidth+1")
        capture("export-narrow-dark-20")
        assert not window.evaluate_js(
            "document.querySelector('.toast.error')?.textContent"
        ), bridge_errors
        completed.append(
            "Snapshot warning, dedicated-calendar guidance, real ICS bridge save (dialog path supplied by test)"
        )
        result.update(
            passed=True,
            exported_events=7,
            requested_window_sizes=[[1280, 820], [720, 760]],
            font_sizes=[14, 20],
            themes=["light", "dark"],
        )
        print("IMPORT EXPERIENCE NATIVE SMOKE PASSED", flush=True)
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], flush=True)
        try:
            capture("failure")
        except Exception:
            pass
    finally:
        (OUT / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        window.destroy()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit(
            "This native smoke runner currently requires Windows WebView2; other platforms are untested."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    print("Artifacts: " + str(OUT), flush=True)
    with tempfile.TemporaryDirectory(prefix="calisift-import-experience-") as directory:
        main(directory, ready)
    if not json.loads((OUT / "result.json").read_text(encoding="utf-8"))["passed"]:
        raise SystemExit(1)

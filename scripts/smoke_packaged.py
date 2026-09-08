"""Exercise the shipped EXE through Windows UI Automation, without a JS test bridge."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import tempfile
import time
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    args = parser.parse_args()
    import clr

    wpf = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/WPF"
    clr.AddReference(str(wpf / "UIAutomationClient.dll"))
    clr.AddReference(str(wpf / "UIAutomationTypes.dll"))
    from System import Int32
    from System.Windows.Automation import (
        AutomationElement,
        TreeScope,
        PropertyCondition,
        ControlType,
        InvokePattern,
        ValuePattern,
        WindowPattern,
        ElementNotAvailableException,
    )

    output = Path("artifacts/packaged-smoke")
    output.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, checks=[])
    with tempfile.TemporaryDirectory(prefix="calisift-shipped-") as directory:
        process = subprocess.Popen(
            [str(Path(args.executable).resolve())],
            env={
                **os.environ,
                "CALISIFT_DATA_DIR": directory,
                "PATH": os.path.join(os.environ["SystemRoot"], "System32"),
            },
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def windows():
            return list(
                AutomationElement.RootElement.FindAll(
                    TreeScope.Children,
                    PropertyCondition(
                        AutomationElement.ProcessIdProperty, Int32(process.pid)
                    ),
                )
            )

        def wait(fn, timeout=40):
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                try:
                    value = fn()
                except ElementNotAvailableException:
                    value = None
                if value:
                    return value
                if process.poll() is not None:
                    raise RuntimeError("Desktop process exited early")
                time.sleep(0.2)
            raise AssertionError("Native UI condition timed out")

        def find(name, kind=ControlType.Button):
            for window in windows():
                for element in window.FindAll(
                    TreeScope.Descendants,
                    PropertyCondition(AutomationElement.ControlTypeProperty, kind),
                ):
                    if (
                        element.Current.Name.strip().endswith(name)
                        and element.Current.IsEnabled
                    ):
                        return element

        def click(name):
            element = wait(lambda: find(name))
            element.GetCurrentPattern(InvokePattern.Pattern).Invoke()

        def event_ids():
            with closing(sqlite3.connect(Path(directory) / "calendar.sqlite3")) as db:
                return [
                    row[0]
                    for row in db.execute("SELECT id FROM event_index ORDER BY id")
                ]

        def close_windows():
            for window in reversed(windows()):
                try:
                    window.GetCurrentPattern(WindowPattern.Pattern).Close()
                except Exception:
                    pass
            process.wait(timeout=15)

        def dialog_file(path):
            def field():
                for window in windows():
                    for element in window.FindAll(
                        TreeScope.Descendants,
                        PropertyCondition(
                            AutomationElement.ControlTypeProperty, ControlType.Edit
                        ),
                    ):
                        label = element.Current.Name.replace("\u200b", "")
                        if element.Current.AutomationId in ("1001", "1148") and (
                            "文件名" in label or "File name" in label
                        ):
                            return element

            element = wait(field)
            element.GetCurrentPattern(ValuePattern.Pattern).SetValue(
                str(Path(path).resolve())
            )

            def submit():
                for window in windows():
                    buttons = window.FindAll(
                        TreeScope.Descendants,
                        PropertyCondition(
                            AutomationElement.ControlTypeProperty, ControlType.Button
                        ),
                    )
                    for node in buttons:
                        if node.Current.Name.startswith(
                            ("保存(", "打开(")
                        ) or node.Current.Name in ("Save", "Open"):
                            return node

            wait(submit).GetCurrentPattern(InvokePattern.Pattern).Invoke()

        try:
            start = time.monotonic()
            click("先用示例体验")
            result["startup_seconds"] = round(time.monotonic() - start, 2)
            click("开始识别")
            click("预览并加入日历")
            click("确认保存")
            result["checks"].append("bundled examples parsed and committed through UI")
            click("导出与记录")
            click("查看导出预览")
            click("保存 ICS 文件")
            target = output / "native-export.ics"
            target.unlink(missing_ok=True)
            dialog_file(target)
            wait(lambda: target.is_file())
            assert target.read_text(encoding="utf-8").count("BEGIN:VEVENT") == 4
            result["checks"].append("native save dialog wrote 4 ICS events")
            click("导入")
            click("选择文件")
            dialog_file(Path("tests/fixtures/ocr/clean.png"))
            click("开始识别")
            click("预览并加入日历")
            click("确认保存")
            wait(lambda: len(event_ids()) == 5)
            saved_ids = event_ids()
            result["checks"].append(
                "native open dialog and frozen OCR process committed image result"
            )
            close_windows()
            process = subprocess.Popen(
                [str(Path(args.executable).resolve())],
                env={
                    **os.environ,
                    "CALISIFT_DATA_DIR": directory,
                    "PATH": os.path.join(os.environ["SystemRoot"], "System32"),
                },
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            click("安排")
            assert event_ids() == saved_ids
            result["checks"].append(
                "five stable event IDs retained after native application restart"
            )
            result["passed"] = True
        except Exception:
            result["error"] = traceback.format_exc()
            result["visible_buttons"] = [
                e.Current.Name
                for w in windows()
                for e in w.FindAll(
                    TreeScope.Descendants,
                    PropertyCondition(
                        AutomationElement.ControlTypeProperty, ControlType.Button
                    ),
                )
            ]
            result["window_classes"] = [w.Current.ClassName for w in windows()]
            result["input_ids"] = [
                dict(name=e.Current.Name, automation_id=e.Current.AutomationId)
                for w in windows()
                for e in w.FindAll(
                    TreeScope.Descendants,
                    PropertyCondition(
                        AutomationElement.ControlTypeProperty, ControlType.Edit
                    ),
                )
            ]
        finally:
            for window in windows():
                node = window.FindFirst(
                    TreeScope.Descendants,
                    PropertyCondition(AutomationElement.AutomationIdProperty, "2"),
                )
                if node:
                    try:
                        node.GetCurrentPattern(InvokePattern.Pattern).Invoke()
                    except Exception:
                        pass
            for window in reversed(windows()):
                try:
                    window.GetCurrentPattern(WindowPattern.Pattern).Close()
                except Exception:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                result["passed"] = False
                result["forced_exit"] = True
        result["exit_code"] = process.returncode
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

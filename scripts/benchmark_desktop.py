"""Reproducible local 5000-record timings, separate from recognition accuracy."""

from datetime import date, timedelta
import json
from pathlib import Path
import platform
import tempfile
import time

from xingcheng.application import Application
from xingcheng.calendar import empty_calendar, identity, normalized


def main():
    calendar = empty_calendar("星辰奕歌")
    for index in range(5000):
        value = normalized(
            dict(
                date=str(date(2026, 1, 1) + timedelta(days=index)),
                title=f"公开性能样例 {index}",
                start="08:00",
                end="09:00",
            )
        )
        calendar["events"].append(
            dict(
                id=identity(),
                sequence=0,
                hidden=False,
                base=value,
                contributions=[],
                overrides={},
                history=[],
            )
        )
    result = dict(
        system=platform.platform(), python=platform.python_version(), records=5000
    )
    with tempfile.TemporaryDirectory(prefix="calisift-benchmark-") as folder:
        app = Application(folder)
        try:
            start = time.perf_counter()
            wid = app.store.create_workspace("星辰奕歌", calendar)["id"]
            result["create_seconds"] = round(time.perf_counter() - start, 4)
            queries = []
            for options in (
                {},
                {},
                {"query": "公开性能"},
                {"date_from": "2027-01-01", "date_to": "2027-12-31"},
            ):
                start = time.perf_counter()
                found = app.events(wid, **options)
                queries.append(
                    dict(
                        options=options,
                        total=found["total"],
                        seconds=round(time.perf_counter() - start, 4),
                    )
                )
            result["queries"] = queries
            start = time.perf_counter()
            app.preview_change(
                wid, 0, dict(type="settings", settings={"large_text": True})
            )
            result["preview_seconds"] = round(time.perf_counter() - start, 4)
            if platform.system() == "Windows":
                import ctypes
                from ctypes import wintypes

                class Memory(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                    ] + [
                        (k, ctypes.c_size_t)
                        for k in (
                            "PeakWorkingSetSize",
                            "WorkingSetSize",
                            "QuotaPeakPagedPoolUsage",
                            "QuotaPagedPoolUsage",
                            "QuotaPeakNonPagedPoolUsage",
                            "QuotaNonPagedPoolUsage",
                            "PagefileUsage",
                            "PeakPagefileUsage",
                        )
                    ]

                value = Memory()
                value.cb = ctypes.sizeof(value)
                ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(Memory),
                    wintypes.DWORD,
                ]
                ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
                if ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(),
                    ctypes.byref(value),
                    value.cb,
                ):
                    result["process_peak_working_set_mib"] = round(
                        value.PeakWorkingSetSize / 1024**2, 1
                    )
        finally:
            app.close()
    target = Path("artifacts/desktop-performance.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

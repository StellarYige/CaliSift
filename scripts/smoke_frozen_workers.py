"""Release gate: execute real spreadsheet/OCR inference through the frozen worker."""

import json
import os
from pathlib import Path
import subprocess
import threading
import time


def main():
    executable = Path("dist/CaliSift/calisift-worker.exe").resolve()
    results = []
    for kind, filename, expected in [
        ("parse", "samples/九月排班.csv", 2),
        ("ocr", "tests/fixtures/ocr/clean.png", 1),
    ]:
        started = time.perf_counter()
        request = dict(
            kind=kind,
            path=str(Path(filename).resolve()),
            filename=Path(filename).name,
            name="星辰奕歌",
            year=2026,
        )
        process = subprocess.Popen(
            [str(executable)],
            text=True,
            encoding="utf-8",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env={
                **os.environ,
                "PATH": os.path.join(os.environ["SystemRoot"], "System32"),
            },
        )
        peak = [0]

        def monitor():
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

            counter = Memory()
            counter.cb = ctypes.sizeof(counter)
            query = ctypes.windll.psapi.GetProcessMemoryInfo
            query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
            while process.poll() is None:
                if query(
                    wintypes.HANDLE(int(process._handle)),
                    ctypes.byref(counter),
                    counter.cb,
                ):
                    peak[0] = max(peak[0], counter.PeakWorkingSetSize)
                time.sleep(0.05)

        sampler = threading.Thread(target=monitor, daemon=True)
        sampler.start()
        try:
            stdout, stderr = process.communicate(
                json.dumps(request, ensure_ascii=False), timeout=90
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            sampler.join(timeout=2)
        value = json.loads(stdout) if stdout else {}
        report = value.get("report", {})
        item = dict(
            kind=kind,
            exit_code=process.returncode,
            error=value.get("error"),
            items=len(report.get("events", [])) + len(report.get("pending", [])),
            seconds=round(time.perf_counter() - started, 3),
            peak_working_set_mib=round(peak[0] / 1024**2, 1),
        )
        results.append(item)
        if process.returncode or item["error"] or item["items"] != expected:
            raise RuntimeError(f"Frozen {kind} check failed: {item}; {stderr[-500:]}")
        print(json.dumps(item, ensure_ascii=False), flush=True)
    cli = subprocess.run(
        [
            str(executable.with_name("calisift-cli.exe")),
            "ocr",
            str(Path("tests/fixtures/ocr/clean.png").resolve()),
            "--name",
            "星辰奕歌",
            "--year",
            "2026",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=95,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "PATH": os.path.join(os.environ["SystemRoot"], "System32")},
    )
    assert cli.returncode == 0, cli.stderr[-500:]
    assert len(json.loads(cli.stdout)["events"]) == 1
    print("Frozen CLI OCR passed", flush=True)
    Path("artifacts/frozen-worker-results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

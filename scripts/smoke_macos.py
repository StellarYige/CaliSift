"""Run the shipped binaries. Native dialog/Gatekeeper checks remain explicit gaps."""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    if sys.platform != "darwin":
        raise SystemExit("This check requires macOS.")
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/CaliSift.app").resolve()
    executable = bundle / "Contents/MacOS/CaliSift"
    worker = executable.with_name("calisift-worker")
    results = []
    env = {**os.environ, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    for kind, file, count in [
        ("parse", "samples/九月排班.csv", 2),
        ("ocr", "tests/fixtures/ocr/clean.png", 1),
    ]:
        started = time.monotonic()
        request = dict(
            kind=kind,
            path=str(Path(file).resolve()),
            filename=Path(file).name,
            name="星辰奕歌",
            year=2026,
        )
        run = subprocess.run(
            [str(worker)],
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=95,
            env=env,
        )
        assert run.returncode == 0, run.stderr[-1000:]
        value = json.loads(run.stdout)
        assert "error" not in value, value
        report = value["report"]
        assert len(report["events"]) + len(report["pending"]) == count
        results.append(
            dict(kind=kind, seconds=round(time.monotonic() - started, 3), events=count)
        )
    output = Path("artifacts/macos-ui.json").resolve()
    launch = subprocess.run(
        [str(executable), "--self-check"],
        env={**env, "CALISIFT_CHECK_OUTPUT": str(output)},
        check=False,
        timeout=120,
    )
    ui = json.loads(output.read_text(encoding="utf-8"))
    assert launch.returncode == 0 and ui["success"], ui
    result = dict(
        system=platform.platform(),
        architecture=platform.machine(),
        workers=results,
        ui=ui,
        gatekeeper_download_verified=False,
        apple_calendar_verified=False,
        drag_clipboard_verified=False,
    )
    Path("artifacts/macos-smoke.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

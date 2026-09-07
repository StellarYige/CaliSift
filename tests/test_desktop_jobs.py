import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

from PIL import Image
import pytest

from xingcheng.application import Application
from xingcheng.desktop_worker import execute
from xingcheng.localstore import LocalError
from tests.test_desktop_store import local, draft, change
from tests.test_calendar import NAME, report


def finish(app, jid):
    until = time.monotonic() + 30
    while time.monotonic() < until:
        job = app.get_job(jid)
        if job["status"] not in ("running", "queued"):
            return job
        time.sleep(0.03)
    pytest.fail("Worker did not complete")


def test_real_workers_partial_failure_retry_and_cleanup(local, tmp_path):
    app, wid = local
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"broken ZIP")
    good = Path("samples/九月排班.csv")
    staged = app.jobs.stage(wid, [str(good), str(bad)])
    jid = staged["id"]
    badid = staged["files"][1]["id"]
    app.jobs.start(jid, 2026)
    result = finish(app, jid)
    assert result["status"] == "review"
    assert result["files"][1]["status"] == "error"
    assert len(result["report"]["events"]) == 2
    assert result["report"]["files"][1]["status"] == "error"
    assert app.workspace(wid)["count"] == 0
    with pytest.raises(LocalError):
        app.jobs.start(jid, 2027, retry_ids=[badid])
    with pytest.raises(LocalError):
        app.jobs.start(jid, 2026, retry_ids=["unknown"])
    app.jobs.start(jid, 2026, retry_ids=[badid])
    result = finish(app, jid)
    assert len(result["report"]["events"]) == 2
    change(app, wid, dict(type="append", source_name="排班"), jid)
    assert app.workspace(wid)["count"] == 2
    assert not (app.store.jobs_dir / jid).exists()
    with pytest.raises(LocalError):
        app.jobs.start(jid, 2026)


def test_full_table_pagination_mapping_candidates_and_source_rules(local, tmp_path):
    app, wid = local
    import csv

    path = tmp_path / "wide.csv"
    heads = ["姓名"] + ["自定义" + str(i) for i in range(1, 31)]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(heads)
        for i in range(65):
            writer.writerow([NAME] + [str(i)] * 30)
    template = app.save_template(
        "宽表",
        {
            "template": dict(
                layout="records",
                sheet="CSV",
                header_row=0,
                headers=heads,
                mapping={"name": 0, "date": 1, "title": 2},
            )
        },
    )
    job = app.jobs.stage(wid, [str(path)])
    fid = job["files"][0]["id"]
    page = app.jobs.table(job["id"], fid, row=50, col=20, header_row=0)
    assert len(page["headers"]) == 31
    assert page["cells"][0][0]["coordinate"] == "U51"
    assert page["template_matches"][0]["id"] == template["id"]
    with pytest.raises(LocalError):
        app.jobs.table(job["id"], "no-file")
    request = dict(
        kind="parse",
        path=str(Path("samples/九月排班.csv")),
        filename="排班.csv",
        name=NAME,
        year=2026,
        rules={
            "shifts": [dict(name="早班", aliases=["早班"], start="09:00", end="15:00")]
        },
    )
    parsed = execute(request)["report"]
    assert parsed["events"][0]["start"] == "08:00"  # explicit source time wins
    with pytest.raises(ValueError):
        execute({**request, "kind": "unknown"})
    with pytest.raises(ValueError):
        execute({**request, "path": "missing.csv"})
    with pytest.raises(ValueError):
        execute({**request, "kind": "table", "sheet": 999})
    app.jobs.clean(job["id"])
    with pytest.raises(LocalError):
        app.jobs.start(job["id"], 2026)


def test_job_resume_after_restart_preserves_original_files(local, tmp_path):
    app, wid = local
    job = app.jobs.stage(wid, [str(Path("samples/九月排班.csv"))])
    original = app.store.document("job", job["id"])
    original["status"] = "running"
    original["files"][0]["status"] = "running"
    app.store.put("job", job["id"], wid, original)
    app.close()
    restarted = Application(tmp_path / "data")
    try:
        paused = restarted.get_job(job["id"])
        assert paused["status"] == "paused" and paused["files"][0]["status"] == "paused"
        restarted.jobs.start(job["id"], 2026)
        assert finish(restarted, job["id"])["status"] == "review"
    finally:
        restarted.close()


def test_cancellation_ignores_late_worker_result(local, monkeypatch):
    app, wid = local
    started = threading.Event()
    released = threading.Event()

    def slow(*args, **kwargs):
        started.set()
        released.wait(5)
        return dict(report=report())

    monkeypatch.setattr(app.jobs, "run_worker", slow)
    job = app.jobs.stage(wid, [str(Path("samples/九月排班.csv"))])
    app.jobs.start(job["id"], 2026)
    assert started.wait(3)
    with pytest.raises(LocalError):
        app.jobs.start(job["id"], 2026)
    cancelled = app.jobs.cancel(job["id"])
    released.set()
    assert cancelled["status"] == "cancelled"
    app.jobs.close()
    assert app.get_job(job["id"])["report"] is None
    assert app.events(wid)["total"] == 0


@pytest.mark.parametrize(
    "paths", [[], ["samples/九月排班.csv"] * 11, ["missing.csv"], ["README.md"]]
)
def test_stage_limits_leave_no_draft(local, paths):
    app, wid = local
    with pytest.raises(LocalError):
        app.jobs.stage(wid, paths)
    assert not app.list_jobs(wid)


def test_image_limits_preview_and_retry_options(local, tmp_path):
    app, wid = local
    image = tmp_path / "image.png"
    Image.new("RGB", (100, 80), "white").save(image)
    with pytest.raises(LocalError):
        app.jobs.stage(wid, [str(image)] * 6)
    job = app.jobs.stage(wid, [str(image)])
    fid = job["files"][0]["id"]
    assert app.image_preview(job["id"], fid).startswith("data:image/jpeg;base64,")
    assert app.ocr_details(job["id"], fid) == {}
    with pytest.raises(LocalError):
        app.job_file(job["id"], "unknown")
    for year in [1899, 2200, "2026"]:
        with pytest.raises(LocalError):
            app.jobs.start(job["id"], year)
    huge = tmp_path / "huge.png"
    Image.new("RGB", (4001, 3000), "white").save(huge)
    with pytest.raises(LocalError):
        app.jobs.stage(wid, [str(huge)])
    empty = tmp_path / "empty.csv"
    empty.touch()
    with pytest.raises(LocalError):
        app.jobs.stage(wid, [str(empty)])
    app.jobs.clean(job["id"])
    assert not app.list_jobs(wid)


def test_worker_timeout_crash_protocol_and_frozen_entry(local, monkeypatch, tmp_path):
    app, wid = local
    process = Mock()
    process.returncode = 0
    process.communicate.side_effect = [subprocess.TimeoutExpired("worker", 1), ("", "")]
    popen = Mock(return_value=process)
    monkeypatch.setattr("xingcheng.jobs.subprocess.Popen", popen)
    with pytest.raises(LocalError, match="超过"):
        app.jobs.run_worker({"kind": "parse"}, timeout=1)
    process.kill.assert_called_once()
    assert not app.jobs.processes
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "CaliSift.exe"))
    process.communicate.side_effect = None
    process.communicate.return_value = (json.dumps({"error": "invalid layout"}), "")
    with pytest.raises(LocalError, match="invalid layout"):
        app.jobs.run_worker({"kind": "parse"})
    assert Path(popen.call_args.args[0][0]).name == "calisift-worker.exe"
    process.returncode = 1
    with pytest.raises(LocalError, match="进程"):
        app.jobs.run_worker({"kind": "parse"})
    process.returncode = 0
    process.communicate.return_value = ("{}", "")
    app.jobs.cancelled.add("cancelled")
    with pytest.raises(LocalError, match="取消"):
        app.jobs.run_worker({"kind": "ocr"}, "cancelled")
    assert not app.jobs.processes

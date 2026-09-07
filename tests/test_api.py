import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from scripts.generate_fixtures import NAME, csv_bytes, xlsx_bytes
from xingcheng.api import MAX_REQUEST_BYTES, app, parse_isolated

client = TestClient(app)
ROWS = [["日期", "姓名", "事项", "时间"], ["2026-09-07", NAME, "培训", "08:00-10:00"]]


def upload(data=None, filename="培训.csv", **fields):
    return client.post(
        "/api/parse",
        files={"files": (filename, data if data is not None else csv_bytes(ROWS))},
        data={"name": NAME, "reference_year": "2026", **fields},
    )


def test_health_and_openapi():
    assert client.get("/health").json()["name"] == "星程"
    assert set(client.get("/openapi.json").json()["paths"]) == {
        "/health",
        "/api/parse",
        "/api/merge",
        "/api/review",
        "/api/ocr",
        "/api/calendar/transform",
        "/api/calendar/export",
        "/api/calendar/course",
    }


def test_real_worker_upload():
    response = upload()
    assert response.status_code == 200
    result = response.json()
    assert result["events"][0]["title"] == "培训"
    assert result["events"][0]["sources"][0]["filename"] == "培训.csv"


def test_multi_file_partial_success():
    response = client.post(
        "/api/parse",
        files=[
            ("files", ("排班.xlsx", xlsx_bytes({"表": ROWS}))),
            ("files", ("坏表.xls", b"broken")),
        ],
        data={"name": NAME, "reference_year": 2026},
    )
    assert response.status_code == 200
    assert len(response.json()["events"]) == 1
    assert [f["status"] for f in response.json()["files"]] == ["ok", "error"]


def test_original_filename_for_wechat():
    response = upload(filename="temporary_file", original_filename="培训.csv")
    assert response.json()["files"][0]["filename"] == "培训.csv"
    assert response.json()["events"]


def test_untrusted_path_is_basename():
    response = upload(original_filename="../../培训.csv")
    assert response.json()["events"][0]["sources"][0]["filename"] == "培训.csv"


def test_merge_recomputes_duplicates_and_conflicts():
    first = upload().json()
    second = upload(
        csv_bytes(
            [
                ["日期", "姓名", "事项", "时间"],
                ["2026-09-07", NAME, "考试", "09:00-11:00"],
            ]
        ),
        "考试.csv",
    ).json()
    response = client.post("/api/merge", json={"reports": [first, first, second]})
    assert response.status_code == 200
    assert len(response.json()["events"]) == 2
    assert response.json()["conflicts"][0]["kind"] == "definite"


@pytest.mark.parametrize(
    "fields",
    [
        {"name": " "},
        {"name": "甲、乙"},
        {"reference_year": "1800"},
        {"reference_year": "abc"},
    ],
)
def test_invalid_form(fields):
    assert upload(**fields).status_code == 422


def test_missing_file():
    assert (
        client.post(
            "/api/parse", data={"name": NAME, "reference_year": 2026}
        ).status_code
        == 422
    )


def test_file_count_limit():
    response = client.post(
        "/api/parse",
        files=[("files", (f"{i}.csv", b"a")) for i in range(11)],
        data={"name": NAME, "reference_year": 2026},
    )
    assert response.status_code == 422


def test_body_limit():
    response = client.post(
        "/api/parse",
        content=b"a",
        headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)},
    )
    assert response.status_code == 413
    response = client.post(
        "/api/merge", content=b"a", headers={"Content-Length": "invalid"}
    )
    assert response.status_code == 413


def test_single_file_limit():
    response = upload(b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "error"


def test_timeout_and_temp_cleanup():
    observed = []

    def fail(command, **kwargs):
        observed.append(Path(command[-1]))
        assert observed[0].exists()
        raise subprocess.TimeoutExpired(command, 20)

    with patch("xingcheng.api.subprocess.run", side_effect=fail):
        result = parse_isolated(b"a", "a.csv", NAME, 2026)
    assert "20 秒" in result.files[0]["error"]
    assert not observed[0].parent.exists()


@pytest.mark.parametrize("stdout,code", [("not json", 0), ("", 1)])
def test_worker_failure(stdout, code):
    with patch(
        "xingcheng.api.subprocess.run",
        return_value=subprocess.CompletedProcess([], code, stdout, ""),
    ):
        result = parse_isolated(b"a", "a.csv", NAME, 2026)
    assert result.files[0]["status"] == "error"


@pytest.fixture
def report():
    from xingcheng.aggregate import merge_reports
    from xingcheng.parsing import parse_file

    return merge_reports(
        [parse_file(csv_bytes(ROWS), "培训.csv", NAME, 2026)]
    ).to_dict()


@pytest.mark.parametrize(
    "change",
    [
        {"date": "09/07/2026"},
        {"date": "2026-02-30"},
        {"date": None},
        {"start": "25:00"},
        {"start": None},
        {"end": "07:00"},
        {"precision": "point"},
        {"precision": "date"},
        {"status": "pending"},
    ],
)
def test_reject_malformed_merge_events(report, change):
    report["events"][0].update(change)
    assert client.post("/api/merge", json={"reports": [report]}).status_code == 422


def test_merge_empty_limit():
    assert client.post("/api/merge", json={"reports": []}).status_code == 422
    assert client.post("/api/merge", json={"reports": [{}] * 11}).status_code == 422


def test_pending_roundtrip():
    report = upload(
        csv_bytes([["日期", "姓名", "事项"], ["每周一", NAME, "课程"]])
    ).json()
    assert report["pending"]
    response = client.post("/api/merge", json={"reports": [report]})
    assert response.status_code == 200 and response.json()["pending"]


def test_point_and_date_roundtrip():
    report = upload(
        csv_bytes(
            [
                ["日期", "姓名", "事项", "时间"],
                ["9月7日", NAME, "课程", "14:00"],
                ["9月8日", NAME, "值班", ""],
            ]
        )
    ).json()
    assert [e["precision"] for e in report["events"]] == ["point", "date"]
    assert client.post("/api/merge", json={"reports": [report]}).status_code == 200

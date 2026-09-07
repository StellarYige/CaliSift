from pathlib import Path
from unittest.mock import patch
import subprocess
import pytest
from xingcheng.ocr import (
    readiness,
    decode,
    engine,
    recognize,
    recognize_isolated,
    verify_models,
)

ROOT = Path(__file__).parent / "fixtures" / "ocr"
NAME = "星辰奕歌"


@pytest.fixture(scope="module")
def real_engine():
    if not readiness()["ready"]:
        pytest.skip(
            "Real OCR models are not installed; run python -m scripts.install_ocr"
        )
    return engine()


@pytest.mark.parametrize(
    "filename",
    [
        "clean.png",
        "rotated.png",
        "skewed.png",
        "compressed.jpg",
        "merged.png",
        "borderless.png",
    ],
)
def test_real_models_extract_printed_table_and_never_match_similar_name(
    real_engine, filename
):
    result = recognize(
        (ROOT / filename).read_bytes(), filename, NAME, 2026, {}, real_engine
    )
    items = result["events"] + result["pending"]
    assert len(items) == 1, result
    assert items[0]["date"] == "2026-09-07", result
    assert items[0]["title"] == "消防培训", result
    assert items[0]["start"] == "08:00" and items[0]["end"] == "10:00"
    assert all("星辰奕歌甲" not in s["excerpt"] for s in items[0]["sources"])
    assert result["files"][0]["ocr"]["crops"]


def test_real_ocr_process_boundary():
    if not readiness()["ready"]:
        pytest.skip("Real models not installed")
    r = recognize_isolated(
        (ROOT / "clean.png").read_bytes(), "clean.png", NAME, 2026, {}
    )
    assert len(r["events"]) + len(r["pending"]) == 1


def test_image_resource_limits_before_decode():
    from PIL import Image
    import io

    b = io.BytesIO()
    Image.new("RGB", (4001, 3000)).save(b, format="PNG")
    with pytest.raises(ValueError, match="1200"):
        decode(b.getvalue(), {})
    with pytest.raises(ValueError):
        decode(b"broken", {})
    with pytest.raises(ValueError):
        decode((ROOT / "clean.png").read_bytes(), {"crop": [0.7, 0, 0.2, 1]})
    with pytest.raises(ValueError):
        recognize_isolated(b"x", "bad.pdf", NAME, 2026, {})


def test_missing_models_and_timeout_do_not_break_excel():
    from xingcheng.parsing import parse_file
    from scripts.generate_fixtures import csv_bytes

    with patch("xingcheng.ocr.MODEL_DIR", ROOT / "missing"):
        assert not readiness()["ready"]
        with pytest.raises(ValueError, match="离线模型包"):
            verify_models()
    with (
        patch("xingcheng.ocr.readiness", return_value={"ready": True}),
        patch(
            "xingcheng.ocr.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ocr", 90),
        ),
    ):
        with pytest.raises(ValueError, match="90"):
            recognize_isolated(b"x", "test.png", NAME, 2026, {})
    assert parse_file(
        csv_bytes([["日期", "姓名", "事项"], ["2026-09-07", NAME, "培训"]]),
        "test.csv",
        NAME,
        2026,
    ).events


def test_uncertain_layout_stays_pending(real_engine):
    from PIL import Image, ImageDraw
    import io

    im = Image.open(ROOT / "clean.png")
    draw = ImageDraw.Draw(im)
    draw.rectangle((565, 10, 580, 265), fill="white")
    b = io.BytesIO()
    im.save(b, format="PNG")
    result = recognize(b.getvalue(), "uncertain.png", NAME, 2026, {}, real_engine)
    assert not result["events"] or result["files"][0]["ocr"]["reliable"]


def test_explicit_ocr_text_correction_keeps_original(real_engine):
    initial = recognize(
        (ROOT / "clean.png").read_bytes(), "clean.png", NAME, 2026, {}, real_engine
    )
    block = next(b for b in initial["files"][0]["ocr"]["blocks"] if b["text"] == NAME)
    result = recognize(
        (ROOT / "clean.png").read_bytes(),
        "clean.png",
        "星辰奕歌乙",
        2026,
        {"corrections": {block["id"]: "星辰奕歌乙"}},
        real_engine,
    )
    corrected = next(
        b for b in result["files"][0]["ocr"]["blocks"] if b["id"] == block["id"]
    )
    assert corrected["original_text"] == NAME and corrected["corrected"]
    assert len(result["events"]) + len(result["pending"]) == 1

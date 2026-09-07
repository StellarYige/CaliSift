"""Local OCR boundary. Models are installed out of band; uploads never trigger downloads."""

from __future__ import annotations

import base64
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

MODEL_DIR = Path(
    os.environ.get(
        "XINGCHENG_OCR_MODELS",
        (
            Path(sys._MEIPASS)
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2]
        )
        / "models"
        / "ocr",
    )
)
MODELS = {
    "Det": (
        "ch_PP-OCRv5_mobile_det.onnx",
        "PP-OCRv5/det",
        "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    ),
    "Rec": (
        "ch_PP-OCRv5_rec_mobile_infer.onnx",
        "PP-OCRv5/rec",
        "5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5",
    ),
    "Cls": (
        "ch_ppocr_mobile_v2.0_cls_infer.onnx",
        "PP-OCRv4/cls",
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
}
FONT = (
    "NotoSansSC.ttf",
    "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da",
)
FONT_URL = "https://raw.githubusercontent.com/google/fonts/5e35378e6bda803962ee6fd257e444a7d459660d/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
_verified_resources = {}
OCR_TIMEOUT = 90
_gate = threading.BoundedSemaphore(1)


def readiness():
    packages = all(
        importlib.util.find_spec(m) for m in ("rapidocr", "onnxruntime", "cv2", "PIL")
    )
    missing, damaged = [], []
    for filename, expected in [(v[0], v[2]) for v in MODELS.values()] + [FONT]:
        path = MODEL_DIR / filename
        try:
            stat = path.stat()
            key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
            actual = _verified_resources.get(key)
            if actual is None:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                _verified_resources[key] = actual
            if actual != expected:
                damaged.append(filename)
        except OSError:
            missing.append(filename)
    ready = packages and not missing and not damaged
    return dict(
        ready=ready,
        missing=missing,
        damaged=damaged,
        model="中文 PP-OCRv5 mobile / ONNX Runtime CPU",
        message=(
            ""
            if ready
            else "图片识别资源缺失或校验失败，请在设置中导入离线模型包；源码用户可运行 python -m scripts.install_ocr。表格仍可导入"
        ),
    )


def verify_models():
    if not readiness()["ready"]:
        raise ValueError(readiness()["message"])
    for filename, _, expected in MODELS.values():
        if hashlib.sha256((MODEL_DIR / filename).read_bytes()).hexdigest() != expected:
            raise ValueError("OCR 模型校验失败，请重新安装模型；表格导入仍可使用")
    if hashlib.sha256((MODEL_DIR / FONT[0]).read_bytes()).hexdigest() != FONT[1]:
        raise ValueError("OCR 字体校验失败，请重新安装")


def recognize_isolated(data, filename, name, year, options):
    if Path(filename).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("图片仅支持 PNG、JPG、JPEG")
    if not data or len(data) > 10 * 1024 * 1024:
        raise ValueError("单图必须为 1 字节至 10 MiB")
    if not readiness()["ready"]:
        raise ValueError(readiness()["message"])
    if not _gate.acquire(blocking=False):
        raise ValueError("正在识别另一张图片，请稍后重试；表格导入仍可使用")
    try:
        with tempfile.TemporaryDirectory(prefix="xingcheng-ocr-") as directory:
            path = Path(directory) / ("image" + Path(filename).suffix.lower())
            path.write_bytes(data)
            try:
                process = subprocess.run(
                    [sys.executable, "-m", "xingcheng.ocr", str(path)],
                    input=json.dumps(
                        dict(
                            filename=Path(filename.replace("\\", "/")).name,
                            name=name,
                            year=year,
                            options=options,
                        )
                    ),
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    timeout=OCR_TIMEOUT,
                    env={**os.environ, "PYTHONUTF8": "1"},
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if process.returncode:
                    raise ValueError("图片识别失败，请裁剪到清晰的打印体表格后重试")
                result = json.loads(process.stdout)
                if "error" in result:
                    raise ValueError(result["error"])
                return result
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    "图片识别超过 90 秒，请缩小图片区域后单独重试"
                ) from exc
    finally:
        _gate.release()


def engine():
    verify_models()
    from rapidocr import RapidOCR, OCRVersion, ModelType, EngineType, LangDet, LangRec

    params = {
        "Global.log_level": "error",
        "Global.text_score": 0.4,
        "Global.font_path": str(MODEL_DIR / FONT[0]),
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }
    for key, (filename, _, _) in MODELS.items():
        params.update(
            {
                f"{key}.model_path": str(MODEL_DIR / filename),
                f"{key}.engine_type": EngineType.ONNXRUNTIME,
                f"{key}.model_type": ModelType.MOBILE,
                f"{key}.ocr_version": (
                    OCRVersion.PPOCRV4 if key == "Cls" else OCRVersion.PPOCRV5
                ),
            }
        )
    params.update({"Det.lang_type": LangDet.CH, "Rec.lang_type": LangRec.CH})
    # Fail closed even if a future dependency attempts to fetch a dictionary/font.
    from unittest.mock import patch

    with patch(
        "socket.socket.connect",
        side_effect=RuntimeError("OCR runtime networking disabled"),
    ):
        return RapidOCR(params=params)


def decode(data, options):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as source:
            if (
                source.format not in ("PNG", "JPEG")
                or source.width * source.height > 12_000_000
            ):
                raise ValueError("仅支持 PNG/JPEG，解码后不得超过 1200 万像素")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("图片无法解码，请选择清晰的 PNG/JPEG") from exc
    rotation = options.get("rotation", 0)
    if rotation not in (0, 90, 180, 270):
        raise ValueError("旋转角度无效")
    image = image.rotate(-rotation, expand=True)
    crop = options.get("crop")
    if crop:
        if (
            len(crop) != 4
            or any(not isinstance(v, (int, float)) for v in crop)
            or not (0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1)
        ):
            raise ValueError("裁剪范围无效")
        image = image.crop(
            (
                int(crop[0] * image.width),
                int(crop[1] * image.height),
                int(crop[2] * image.width),
                int(crop[3] * image.height),
            )
        )
    array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    lines = cv2.HoughLinesP(
        cv2.Canny(gray, 60, 160),
        1,
        np.pi / 1800,
        100,
        minLineLength=max(50, image.width // 4),
        maxLineGap=20,
    )
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if abs(angle) <= 8:
                angles.append(angle)
    angle = float(np.median(angles)) if angles else 0
    if 0.15 < abs(angle) <= 8:
        matrix = cv2.getRotationMatrix2D((image.width / 2, image.height / 2), angle, 1)
        array = cv2.warpAffine(
            array, matrix, (image.width, image.height), borderValue=(255, 255, 255)
        )
    return array, angle


def clusters(values, tolerance):
    groups = []
    for value in sorted(values):
        if groups and abs(value - sum(groups[-1]) / len(groups[-1])) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(g) / len(g) for g in groups]


def reconstruct(array, blocks):
    import cv2
    import numpy as np
    from .readers import Cell, Sheet

    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    horizontal = cv2.morphologyEx(
        ink,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 12), 1)),
    )
    vertical = cv2.morphologyEx(
        ink,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(25, h // 12))),
    )
    ys = clusters(np.where((horizontal > 0).sum(axis=1) > w * 0.3)[0].tolist(), 5)
    xs = clusters(np.where((vertical > 0).sum(axis=0) > h * 0.3)[0].tolist(), 5)
    bounded = len(xs) >= 3 and len(ys) >= 3
    reliable = True
    if bounded:
        rows, cols = len(ys) - 1, len(xs) - 1
    else:
        heights = [b["box"][3] - b["box"][1] for b in blocks]
        tolerance = max(8, float(np.median(heights)) * 0.65)
        ys = clusters([(b["box"][1] + b["box"][3]) / 2 for b in blocks], tolerance)
        xs = clusters([b["box"][0] for b in blocks], tolerance)
        rows, cols = len(ys), len(xs)
        reliable = 2 <= rows <= 200 and 2 <= cols <= 30
    if rows * cols > 20000 or not rows or not cols:
        raise ValueError("无法可靠还原表格，请裁剪到一张完整、对齐清晰的表格")
    sheet = Sheet("图片表格", [[Cell(r, c) for c in range(cols)] for r in range(rows)])
    positions = {}
    for block in blocks:
        x0, y0, x1, y1 = block["box"]
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        if bounded:
            if not (xs[0] < x < xs[-1] and ys[0] < y < ys[-1]):
                continue
            r = max(0, min(rows - 1, int(np.searchsorted(ys, y) - 1)))
            c = max(0, min(cols - 1, int(np.searchsorted(xs, x) - 1)))
        else:
            r = min(range(rows), key=lambda i: abs(ys[i] - y))
            c = min(range(cols), key=lambda i: abs(xs[i] - x0))
        cell = sheet.at(r, c)
        if cell.label:
            reliable = False
        cell.value = (cell.label + " " + block["text"]).strip()
        positions.setdefault(cell.coordinate, []).append(block)
        block["cell"] = cell.coordinate
    if bounded:
        # A missing internal border may represent a merged header. Only fill rectangular connected areas.
        visited = set()
        for r in range(rows):
            for c in range(cols):
                if (r, c) in visited:
                    continue
                region, todo = set(), [(r, c)]
                while todo:
                    a, b = todo.pop()
                    if (a, b) in region:
                        continue
                    region.add((a, b))
                    visited.add((a, b))
                    for da, db in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        aa, bb = a + da, b + db
                        if not (0 <= aa < rows and 0 <= bb < cols):
                            continue
                        if db:
                            xx = int(xs[max(b, bb)])
                            part = vertical[
                                int(ys[a]) + 3 : int(ys[a + 1]) - 3,
                                max(0, xx - 2) : xx + 3,
                            ]
                        else:
                            yy = int(ys[max(a, aa)])
                            part = horizontal[
                                max(0, yy - 2) : yy + 3,
                                int(xs[b]) + 3 : int(xs[b + 1]) - 3,
                            ]
                        if (
                            part.size
                            and (part > 0).mean() < 0.08
                            and (aa, bb) not in region
                        ):
                            todo.append((aa, bb))
                if len(region) <= 1:
                    continue
                r0, r1 = min(a for a, b in region), max(a for a, b in region)
                c0, c1 = min(b for a, b in region), max(b for a, b in region)
                populated = [sheet.at(a, b) for a, b in region if sheet.at(a, b).label]
                if len(region) != (r1 - r0 + 1) * (c1 - c0 + 1) or len(populated) > 1:
                    reliable = False
                    continue
                if populated:
                    value = populated[0].value
                    refs = positions.get(populated[0].coordinate, [])
                    for a, b in region:
                        cell = sheet.at(a, b)
                        cell.value = value
                        cell.anchor = (r0, c0)
                    positions[sheet.at(r0, c0).coordinate] = refs
    if not bounded:
        counts = [sum(bool(c.label) for c in row) for row in sheet.rows]
        reliable = reliable and len(set(counts)) == 1 and counts[0] == cols
    return sheet, positions, reliable, bounded


def recognize(data, filename, name, year, options, ocr_engine=None):
    import cv2
    import numpy as np
    from .parsing import parse_sheets, matches_name, field_name
    from .aggregate import merge_reports
    from unittest.mock import patch

    array, angle = decode(data, options)
    ocr_engine = ocr_engine or engine()
    with patch(
        "socket.socket.connect",
        side_effect=RuntimeError("OCR runtime networking disabled"),
    ):
        result = ocr_engine(array)

        def quality(output):
            horizontal = (
                0
                if output.boxes is None
                else sum(
                    (b[:, 0].max() - b[:, 0].min()) >= (b[:, 1].max() - b[:, 1].min())
                    for b in output.boxes
                )
            )
            headers = [
                float(b[:, 1].mean())
                for b, t in zip(
                    output.boxes if output.boxes is not None else [], output.txts or []
                )
                if field_name(t)
            ]
            people = [
                float(b[:, 1].mean())
                for b, t in zip(
                    output.boxes if output.boxes is not None else [], output.txts or []
                )
                if matches_name(t, name)
            ]
            top_header = (
                20
                if headers and people and np.median(headers) < np.median(people)
                else 0
            )
            return (
                sum(
                    10 if matches_name(t, name) else 2 if field_name(t) else 0
                    for t in (output.txts or [])
                )
                + horizontal * 2
                + top_header
            )

        # Explicitly selected orientation is respected; automatic fallback checks quarter turns.
        vertical_boxes = (
            result.boxes is not None
            and sum(
                (b[:, 0].max() - b[:, 0].min()) < (b[:, 1].max() - b[:, 1].min())
                for b in result.boxes
            )
            > len(result.boxes) / 2
        )
        header_ys = [
            float(b[:, 1].mean())
            for b, t in zip(
                result.boxes if result.boxes is not None else [], result.txts or []
            )
            if field_name(t)
        ]
        name_ys = [
            float(b[:, 1].mean())
            for b, t in zip(
                result.boxes if result.boxes is not None else [], result.txts or []
            )
            if matches_name(t, name)
        ]
        inverted = header_ys and name_ys and np.median(header_ys) > np.median(name_ys)
        if not options.get("rotation") and (
            quality(result) < 4 or vertical_boxes or inverted
        ):
            best = initial_quality = quality(result)
            for turns in (1, 2, 3):
                rotated = np.rot90(array, turns).copy()
                attempt = ocr_engine(rotated)
                score = quality(attempt)
                if score > best:
                    result, best, best_array = attempt, score, rotated
            if best > initial_quality:
                array = best_array
    if result.boxes is None or not result.txts:
        raise ValueError("未识别到清晰打印体文字，请重新拍照或裁剪")
    if len(result.txts) > 2000:
        raise ValueError("图片文字过多，请拆分图片后重试")
    corrections = options.get("corrections", {})
    blocks = []
    for i, (box, txt, score) in enumerate(
        zip(result.boxes, result.txts, result.scores)
    ):
        x0, y0 = box.min(axis=0)
        x1, y1 = box.max(axis=0)
        corrected = corrections.get(str(i), txt)
        if not isinstance(corrected, str) or len(corrected) > 1000:
            raise ValueError("文字修正无效")
        blocks.append(
            dict(
                id=str(i),
                text=corrected,
                original_text=txt,
                corrected=corrected != txt,
                score=float(score),
                box=[int(x0), int(y0), int(x1), int(y1)],
            )
        )
    sheet, positions, reliable, bounded = reconstruct(array, blocks)
    report = parse_sheets(
        hashlib.sha256(data).hexdigest()[:20],
        [sheet],
        filename,
        name,
        year,
        options.get("layout_hint"),
    )
    all_events = report.events + report.pending
    report.events, report.pending = [], []
    crops = {}
    for event in all_events:
        relevant = []
        for source in event.sources:
            refs = {source.name_cell}
            import re

            for value in source.evidence.values():
                refs.update(re.findall(r"[A-Z]+\d+", value))
            relevant += [b for ref in refs for b in positions.get(ref, [])]
            source.evidence["recognition"] = (
                "图片文字与坐标；分数仅表示文字识别，不代表日程正确率"
            )
            if any(b["corrected"] for b in relevant):
                source.evidence["correction"] = "用户核对：" + "；".join(
                    b["original_text"] + " → " + b["text"]
                    for b in relevant
                    if b["corrected"]
                )
        if not reliable or any(
            b["score"] < 0.92 and not b["corrected"] for b in relevant
        ):
            event.status = "pending"
            event.warnings.append("图片布局或文字不确定，请对照局部证据逐项确认")
        if relevant:
            # Keep evidence rows only. A distant date header must not retain every intervening person's row.
            centers = clusters([(b["box"][1] + b["box"][3]) / 2 for b in relevant], 15)
            strips = []
            for center in centers:
                group = [
                    b
                    for b in relevant
                    if abs((b["box"][1] + b["box"][3]) / 2 - center) <= 15
                ]
                x0 = max(0, min(b["box"][0] for b in group) - 12)
                y0 = max(0, min(b["box"][1] for b in group) - 12)
                x1 = min(array.shape[1], max(b["box"][2] for b in group) + 12)
                y1 = min(array.shape[0], max(b["box"][3] for b in group) + 12)
                strips.append(array[y0:y1, x0:x1])
            crop = np.full(
                (
                    sum(s.shape[0] + 8 for s in strips),
                    max(s.shape[1] for s in strips),
                    3,
                ),
                255,
                dtype=np.uint8,
            )
            cursor = 0
            for strip in strips:
                crop[cursor : cursor + strip.shape[0], : strip.shape[1]] = strip
                cursor += strip.shape[0] + 8
            if crop.shape[1] > 1000:
                crop = cv2.resize(
                    crop, (1000, max(1, int(crop.shape[0] * 1000 / crop.shape[1])))
                )
            encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])[
                1
            ].tobytes()
            evidence_id = hashlib.sha256(encoded).hexdigest()[:20]
            crops[evidence_id] = base64.b64encode(encoded).decode("ascii")
            for source in event.sources:
                source.evidence["image"] = evidence_id
        (report.pending if event.status == "pending" else report.events).append(event)
    if not reliable:
        report.warnings.append(
            "无法可靠还原全部布局，结果仅作为待确认线索；不支持手写、严重透视或模糊图片"
        )
    report.files[0]["ocr"] = dict(
        blocks=blocks,
        crops=crops,
        deskew=round(angle, 2),
        bounded=bounded,
        reliable=reliable,
    )
    if options.get("include_preview"):
        height, width = array.shape[:2]
        scale = min(1, 1600 / max(height, width))
        preview = cv2.resize(
            array, (max(1, int(width * scale)), max(1, int(height * scale)))
        )
        preview_bytes = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 85])[
            1
        ].tobytes()
        report.files[0]["ocr"].update(
            width=width,
            height=height,
            preview_image="data:image/jpeg;base64,"
            + base64.b64encode(preview_bytes).decode("ascii"),
        )
    return merge_reports([report]).to_dict()


if __name__ == "__main__":
    settings = json.load(sys.stdin)
    try:
        with redirect_stdout(sys.stderr):
            output = recognize(
                Path(sys.argv[1]).read_bytes(),
                settings["filename"],
                settings["name"],
                settings["year"],
                settings["options"],
            )
    except Exception as exc:
        output = {
            "error": (
                str(exc)
                if isinstance(exc, ValueError)
                else "图片识别失败，请重新拍摄清晰表格后重试"
            )
        }
    json.dump(output, sys.stdout, ensure_ascii=False)

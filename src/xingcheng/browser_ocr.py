"""PP-OCR inference via ONNX Runtime Web, single-image/single-thread WASM.

The detection postprocessor is vendored from RapidOCR 3.4.2 (Apache-2.0).
Preprocessing, orientation, layout, confidence and evidence are shared with ocr.py.
"""

import math
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from .vendor.db import DetPreProcess, DBPostProcess


def normalized_crop(img, width):
    w = min(width, max(1, math.ceil(48 * img.shape[1] / img.shape[0])))
    resized = cv2.resize(img, (w, 48)).astype("float32").transpose(2, 0, 1) / 127.5 - 1
    result = np.zeros((1, 3, 48, width), dtype=np.float32)
    result[0, :, :, :w] = resized
    return result


async def infer(role, data):
    from js import ortInfer
    from pyodide.ffi import to_js

    output = await ortInfer(
        role, to_js(np.ascontiguousarray(data).ravel()), to_js(list(data.shape))
    )
    return np.asarray(output.data.to_py()).reshape(tuple(output.dims.to_py()))


async def engine(array):
    # Bound the long edge before min-side normalization to avoid panoramic OOM.
    h, w = array.shape[:2]
    scale = min(1, 2000 / max(h, w))
    image = (
        cv2.resize(array, (max(1, int(w * scale)), max(1, int(h * scale))))
        if scale < 1
        else array
    )
    upscale = max(1, 736 / min(image.shape[:2]))
    if image.shape[0] * image.shape[1] * upscale**2 > 16000000:
        raise ValueError("图片长宽比过大，请裁剪到一张表格")
    tensor = DetPreProcess(limit_side_len=736, limit_type="min")(image)
    if tensor is None or tensor.size > 3 * 4000 * 4000:
        raise ValueError("图片长宽比过大，请裁剪到一张表格")
    pred = await infer("Det", tensor)
    boxes, _ = DBPostProcess(
        thresh=0.3,
        box_thresh=0.5,
        max_candidates=1000,
        unclip_ratio=1.6,
        use_dilation=True,
    )(pred, image.shape[:2])
    boxes = sorted(boxes, key=lambda b: (b[0][1], b[0][0]))
    for i in range(len(boxes) - 1):
        for j in range(i, -1, -1):
            if (
                abs(boxes[j + 1][0][1] - boxes[j][0][1]) < 10
                and boxes[j + 1][0][0] < boxes[j][0][0]
            ):
                boxes[j], boxes[j + 1] = boxes[j + 1], boxes[j]
            else:
                break
    chars = (
        ["blank"]
        + (Path(__file__).parent / "vendor/characters.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        + [" "]
    )
    texts, scores, kept = [], [], []
    for box in boxes:
        pts = np.float32(box)
        cw = max(
            1,
            int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3]))),
        )
        ch = max(
            1,
            int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2]))),
        )
        transform = cv2.getPerspectiveTransform(
            pts, np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
        )
        crop = cv2.warpPerspective(
            image,
            transform,
            (cw, ch),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if ch / cw >= 1.5:
            crop = np.rot90(crop).copy()
        cls = await infer("Cls", normalized_crop(crop, 192))
        if cls[0].argmax() == 1 and cls[0].max() > 0.9:
            crop = cv2.rotate(crop, cv2.ROTATE_180)
        width = max(320, int(48 * crop.shape[1] / crop.shape[0]))
        if width > 8000:
            raise ValueError("单行文字过长，请拆分图片")
        rec = (await infer("Rec", normalized_crop(crop, width)))[0]
        indices = rec.argmax(axis=1)
        probs = rec.max(axis=1)
        selected = np.ones(len(indices), dtype=bool)
        selected[1:] = indices[1:] != indices[:-1]
        selected &= indices != 0
        text = "".join(chars[int(i)] for i in indices[selected])
        score = float(probs[selected].mean()) if selected.any() else 0.0
        if score >= 0.5 and text:
            texts.append(text)
            scores.append(score)
            kept.append(np.asarray(box, dtype=np.float32) / scale)
    return SimpleNamespace(
        boxes=np.asarray(kept) if kept else None, txts=texts, scores=scores
    )


async def recognize(data, filename, name, year, options):
    from .ocr import recognize as shared_recognize

    return await shared_recognize(
        data, filename, name, year, options, ocr_engine=engine
    )

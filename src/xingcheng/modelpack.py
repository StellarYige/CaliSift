"""Offline, allowlisted model repair. Never accepts an arbitrary model or path."""

import hashlib
import io
import os
from pathlib import Path
import zipfile

from . import ocr
from .localstore import LocalError, atomic_write


def resources():
    return {v[0]: v[2] for v in ocr.MODELS.values()} | {ocr.FONT[0]: ocr.FONT[1]}


def create_pack(directory, target):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, expected in resources().items():
            data = (Path(directory) / filename).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise LocalError("OCR_NOT_READY", "模型校验失败：" + filename)
            archive.writestr(filename, data)
    atomic_write(Path(target), stream.getvalue())


def install_pack(path, directory):
    if Path(path).stat().st_size > 200 * 1024 * 1024:
        raise LocalError("INVALID_INPUT", "模型包超过 200 MiB")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != len(resources()) or {i.filename for i in entries} != set(
            resources()
        ):
            raise LocalError("INVALID_INPUT", "请选择本版本对应的完整离线模型包")
        if sum(i.file_size for i in entries) > 200 * 1024 * 1024:
            raise LocalError("INVALID_INPUT", "模型包解码后过大")
        data = {name: archive.read(name) for name in resources()}
        if any(
            hashlib.sha256(value).hexdigest() != resources()[name]
            for name, value in data.items()
        ):
            raise LocalError(
                "OCR_NOT_READY", "模型包校验失败，请重新下载官方发布的模型包"
            )
    # A content-addressed directory makes a partial repair invisible to workers.
    target = (
        Path(directory).parent
        / "model-packs"
        / hashlib.sha256("".join(resources().values()).encode()).hexdigest()[:20]
    )
    target.mkdir(parents=True, exist_ok=True)
    for name, value in data.items():
        atomic_write(target / name, value)
    atomic_write(
        Path(directory).parent / "model-path.txt", str(target.resolve()).encode("utf-8")
    )
    ocr.MODEL_DIR = target
    os.environ["XINGCHENG_OCR_MODELS"] = str(target)
    return ocr.readiness()

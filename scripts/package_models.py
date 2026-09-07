"""Produce the allowlisted repair package from verified local model resources."""

from pathlib import Path
from xingcheng.modelpack import create_pack
from xingcheng.ocr import MODEL_DIR

if __name__ == "__main__":
    folder = Path("artifacts/release")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "CaliSift-models-ppocrv5-v1.zip"
    create_pack(MODEL_DIR, target)
    print(target)

"""Install pinned Chinese mobile models, verifying publisher SHA-256 before replacing files."""

import hashlib
from pathlib import Path
import requests
from xingcheng.ocr import MODELS, MODEL_DIR, FONT, FONT_URL, verify_models


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        (
            filename,
            f"https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/{subdir}/{filename}",
            digest,
        )
        for filename, subdir, digest in MODELS.values()
    ] + [(FONT[0], FONT_URL, FONT[1])]
    for filename, url, digest in files:
        path = MODEL_DIR / filename
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            print(f"Verified {filename}", flush=True)
            continue
        partial = path.with_suffix(".download")
        print(f"Downloading {filename}", flush=True)
        with requests.get(url, stream=True, timeout=(20, 60)) as response:
            response.raise_for_status()
            with partial.open("wb") as target:
                for chunk in response.iter_content(1024 * 1024):
                    target.write(chunk)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
            partial.unlink()
            raise ValueError(f"Checksum mismatch: {filename}")
        partial.replace(path)
    verify_models()
    print("Chinese PP-OCRv5 mobile ready. Runtime uses local models only.")


if __name__ == "__main__":
    main()

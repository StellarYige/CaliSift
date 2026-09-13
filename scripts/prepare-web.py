"""Fetch pinned build inputs, verify every hash, and assemble same-origin assets.
No network access or package resolver is used by the running application.
Use --update-lock deliberately when changing browser dependency versions.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile
import io

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web/public"
LOCK = ROOT / "resources/web-runtime-lock.json"
PYODIDE = ROOT / "web/node_modules/pyodide"
VERSION = "314.0.6"
BASE = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
PACKAGES = ["pydantic", "numpy", "opencv-python", "pillow", "pyclipper", "shapely"]
PURE = {
    "openpyxl": "3.1.5",
    "xlrd": "2.0.2",
    "et-xmlfile": "2.0.0",
    "defusedxml": "0.7.1",
}


def fetch(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-lock", action="store_true")
    args = parser.parse_args()
    pylock = json.loads((PYODIDE / "pyodide-lock.json").read_text(encoding="utf-8"))
    if args.update_lock:
        chosen = set()

        def add(name):
            name = name.lower().replace("_", "-")
            if name in chosen:
                return
            chosen.add(name)
            for dep in pylock["packages"][name]["depends"]:
                add(dep)

        for name in PACKAGES:
            add(name)
        entries = []
        for name in sorted(chosen):
            p = pylock["packages"][name]
            entries.append(
                dict(
                    name=name,
                    version=p["version"],
                    path="runtime/" + p["file_name"],
                    url=BASE + p["file_name"],
                    sha256=p["sha256"],
                )
            )
        for name, version in PURE.items():
            meta = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
            wheel = next(
                f for f in meta["urls"] if f["filename"].endswith("none-any.whl")
            )
            entries.append(
                dict(
                    name=name,
                    version=version,
                    path="wheels/" + wheel["filename"],
                    url=wheel["url"],
                    sha256=wheel["digests"]["sha256"],
                )
            )
        for name in [
            "pyodide.mjs",
            "pyodide.asm.mjs",
            "pyodide.asm.wasm",
            "python_stdlib.zip",
            "pyodide-lock.json",
        ]:
            entries.append(
                dict(
                    name=name,
                    version=VERSION,
                    path="runtime/" + name,
                    local="web/node_modules/pyodide/" + name,
                    sha256=sha((PYODIDE / name).read_bytes()),
                )
            )
        for name in [
            "ort.wasm.min.mjs",
            "ort-wasm-simd-threaded.mjs",
            "ort-wasm-simd-threaded.wasm",
        ]:
            file = ROOT / "web/node_modules/onnxruntime-web/dist" / name
            entries.append(
                dict(
                    name=name,
                    version="1.23.2",
                    path="ort/" + name,
                    local=file.relative_to(ROOT).as_posix(),
                    sha256=sha(file.read_bytes()),
                )
            )
        for model in json.loads(
            (ROOT / "resources/models.json").read_text(encoding="utf-8")
        )["files"]:
            if model["role"] == "font":
                continue
            entries.append(
                dict(
                    name=model["role"],
                    version="PP-OCRv5" if model["role"] != "Cls" else "PP-OCRv2",
                    path="models/" + model["filename"],
                    url=model["url"],
                    local="models/ocr/" + model["filename"],
                    sha256=model["sha256"],
                )
            )
        sources = [
            (
                "Pyodide-MPL-2.0.txt",
                f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE",
            ),
            (
                "sources/pyodide-314.0.6.tar.gz",
                f"https://codeload.github.com/pyodide/pyodide/tar.gz/refs/tags/{VERSION}",
            ),
            (
                "sources/pyodide-recipes-314-20260815.tar.gz",
                "https://codeload.github.com/pyodide/pyodide-recipes/tar.gz/refs/tags/314-20260815",
            ),
            (
                "sources/shapely-2.1.2.tar.gz",
                "https://files.pythonhosted.org/packages/source/s/shapely/shapely-2.1.2.tar.gz",
            ),
            (
                "sources/geos-3.12.1.tar.bz2",
                "https://download.osgeo.org/geos/geos-3.12.1.tar.bz2",
            ),
        ]
        for name, url in sources:
            data = fetch(url)
            path = "licenses/" + name
            target = PUBLIC / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries.append(
                dict(
                    name=name,
                    version="source-notice",
                    path=path,
                    url=url,
                    sha256=sha(data),
                )
            )
        LOCK.write_text(
            json.dumps(
                dict(pyodide=VERSION, packages=PACKAGES, files=entries),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock["pyodide"] != VERSION:
        raise ValueError("Pyodide version mismatch")

    def download(e):
        target = PUBLIC / e["path"]
        if target.exists() and sha(target.read_bytes()) == e["sha256"]:
            return
        source = ROOT / e["local"] if e.get("local") else None
        data = source.read_bytes() if source and source.exists() else fetch(e["url"])
        if sha(data) != e["sha256"]:
            raise ValueError("Checksum mismatch: " + e["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print("Verified " + e["path"], flush=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, lock["files"]))
    # Pure Python packages and application code share one deterministic archive.
    with zipfile.ZipFile(PUBLIC / "python-app.zip", "w", zipfile.ZIP_DEFLATED) as out:

        def write(name, data):
            info = zipfile.ZipInfo(name, (2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)

        for e in lock["files"]:
            if e["path"].startswith("wheels/"):
                with zipfile.ZipFile(PUBLIC / e["path"]) as wheel:
                    for name in sorted(wheel.namelist()):
                        if not name.endswith("/"):
                            write(name, wheel.read(name))
        for p in sorted((ROOT / "src/xingcheng").rglob("*")):
            if p.is_file() and p.suffix in (".py", ".txt"):
                write(p.relative_to(ROOT / "src").as_posix(), p.read_bytes())
    (PUBLIC / "samples").mkdir(exist_ok=True)
    samples = []
    for p in sorted((ROOT / "samples").glob("*.csv")):
        shutil.copy2(p, PUBLIC / "samples" / p.name)
        samples.append(p.name)
    (PUBLIC / "samples/index.json").write_text(
        json.dumps(samples, ensure_ascii=False), encoding="utf-8"
    )
    shutil.copy2(LOCK, PUBLIC / "runtime-lock.json")
    notices = PUBLIC / "licenses"
    notices.mkdir(exist_ok=True)
    for filename in [
        "Python-PSF.txt",
        "RapidOCR-Apache-2.0.txt",
        "PaddleOCR-Apache-2.0.txt",
    ]:
        shutil.copy2(ROOT / "resources/licenses" / filename, notices / filename)
    for filename in ["LICENSE", "THIRD_PARTY_NOTICES.md"]:
        shutil.copy2(ROOT / filename, notices / filename)
    for e in lock["files"]:
        if not e["path"].endswith(".whl"):
            continue
        with zipfile.ZipFile(PUBLIC / e["path"]) as wheel:
            for name in wheel.namelist():
                if not name.endswith("/") and any(
                    word in name.lower() for word in ["license", "copying", "notice"]
                ):
                    target = notices / e["name"] / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(wheel.read(name))
    # Runtime JS dependencies and their distribution notices, independent of native packages.
    for folder in (ROOT / "web/node_modules").iterdir():
        for package in (
            folder.iterdir()
            if folder.name.startswith("@") and folder.is_dir()
            else [folder]
        ):
            if not package.is_dir():
                continue
            for p in package.iterdir():
                if p.is_file() and any(
                    word in p.name.lower()
                    for word in ["license", "copying", "thirdpartynotice"]
                ):
                    target = (
                        notices
                        / "npm"
                        / package.relative_to(ROOT / "web/node_modules")
                        / p.name
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, target)
    print("Browser runtime assets verified.", flush=True)


if __name__ == "__main__":
    main()

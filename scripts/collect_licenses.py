"""Collect runtime license texts from installed, locked distributions for release."""

import importlib.metadata as metadata
import hashlib
import json
from pathlib import Path
import shutil
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "resources/licenses/dependencies"
    destination.mkdir(parents=True, exist_ok=True)
    additional = json.loads(
        (ROOT / "resources/licenses/additional-sources.json").read_text(
            encoding="utf-8"
        )
    )
    pending = [
        "pydantic",
        "openpyxl",
        "xlrd",
        "defusedxml",
        "rapidocr",
        "onnxruntime",
        "opencv-python",
        "pillow",
        "pywebview",
        "platformdirs",
    ]
    visited, records = set(), []
    while pending:
        name = canonicalize_name(pending.pop())
        if name in visited:
            continue
        visited.add(name)
        dist = metadata.distribution(name)
        texts = []
        for file in dist.files or []:
            if "notice" in file.name.lower() or any(
                file.name.lower().startswith(key)
                for key in ("license", "licence", "copying", "notice")
            ):
                source = Path(dist.locate_file(file))
                if not source.is_file():
                    continue
                target = (
                    destination
                    / name
                    / str(file).replace("..", "_").split(".dist-info/", 1)[-1]
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                texts.append(target.relative_to(ROOT).as_posix())
        supplement = additional.get(name)
        if supplement:
            source = ROOT / "resources/licenses" / supplement["file"]
            if (
                dist.version != supplement["version"]
                or hashlib.sha256(source.read_bytes()).hexdigest()
                != supplement["sha256"]
            ):
                raise ValueError("Review supplemental license for " + name)
            texts.append(source.relative_to(ROOT).as_posix())
            texts.extend(
                "resources/licenses/" + path
                for path in supplement.get("additional_files", [])
            )
        if not texts:
            raise ValueError("Missing license text for " + name)
        records.append(
            dict(
                name=dist.metadata["Name"],
                version=dist.version,
                license=(supplement or {}).get("license")
                or dist.metadata.get("License-Expression")
                or dist.metadata.get("License", ""),
                files=texts,
            )
        )
        for raw in dist.requires or []:
            dependency = Requirement(raw)
            if dependency.marker is None or dependency.marker.evaluate({"extra": ""}):
                pending.append(dependency.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, ROOT / "resources/licenses/Python-PSF.txt")
    lock = json.loads((ROOT / "desktop/package-lock.json").read_text(encoding="utf-8"))
    for package, entry in lock["packages"].items():
        if not package or entry.get("dev"):
            continue
        folder = ROOT / "desktop" / package
        name = entry.get("name") or package.split("node_modules/")[-1]
        texts = []
        for file in folder.iterdir():
            if file.is_file() and any(
                file.name.lower().startswith(word)
                for word in ("license", "licence", "copying", "notice")
            ):
                target = destination / "npm" / name / file.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
                texts.append(target.relative_to(ROOT).as_posix())
        records.append(
            dict(
                name="npm:" + name,
                version=entry["version"],
                license=entry.get("license", ""),
                files=texts,
            )
        )
    (ROOT / "resources/dependencies.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for package in json.loads(
        (ROOT / "resources/dotnet-dependencies.json").read_text(encoding="utf-8")
    ):
        for filename in package["files"]:
            if not (ROOT / filename).is_file():
                raise ValueError("Missing .NET notice: " + filename)
    print(f"Collected runtime notices for {len(records)} dependencies")


if __name__ == "__main__":
    main()

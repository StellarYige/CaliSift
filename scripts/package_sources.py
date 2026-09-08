"""Ship corresponding sources for the unmodified GEOS and MPL dependencies."""

import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_dir = ROOT / "artifacts/corresponding-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "resources/corresponding-source.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for resource in manifest["files"]:
        target = source_dir / resource["filename"]
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != resource["sha256"]
        ):
            temporary = target.with_suffix(".download")
            try:
                with urllib.request.urlopen(resource["url"], timeout=60) as response:
                    temporary.write_bytes(response.read(40 * 1024 * 1024 + 1))
                if (
                    hashlib.sha256(temporary.read_bytes()).hexdigest()
                    != resource["sha256"]
                ):
                    raise ValueError(
                        "Source checksum mismatch: " + resource["filename"]
                    )
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        print("Verified source", target.name, flush=True)
    destination = (
        ROOT / "artifacts/release/CaliSift-third-party-source-0.3.0-alpha.2.zip"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_STORED) as archive:
        archive.write(manifest_path, "manifest.json")
        archive.write(ROOT / "resources/licenses/CORRESPONDING-SOURCE.md", "README.md")
        for resource in manifest["files"]:
            archive.write(source_dir / resource["filename"], resource["filename"])
    print(destination)


if __name__ == "__main__":
    main()

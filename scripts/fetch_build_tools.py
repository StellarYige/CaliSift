"""Download only pinned release build tools; runtime file processing never calls this."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "artifacts/toolchain"
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (ROOT / "resources/windows-toolchain.json").read_text(encoding="utf-8")
    )
    for resource in manifest["files"]:
        path = target / resource["filename"]
        if (
            path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest() == resource["sha256"]
        ):
            print("Verified", path.name, flush=True)
            continue
        temporary = path.with_suffix(".download")
        print("Downloading", path.name, flush=True)
        try:
            with (
                urllib.request.urlopen(resource["url"], timeout=60) as source,
                temporary.open("wb") as output,
            ):
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != resource["sha256"]:
                raise ValueError("Checksum mismatch: " + path.name)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

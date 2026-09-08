"""Only checksum this release; older local build artifacts must not leak into it."""

import hashlib
from pathlib import Path
from xingcheng import __version__


def main():
    version = __version__.replace("a", "-alpha.")
    folder = Path("artifacts/release")
    files = [
        p
        for p in sorted(folder.iterdir())
        if p.is_file()
        and (version in p.name or p.name == "CaliSift-models-ppocrv5-v1.zip")
        and p.name != "SHA256SUMS.txt"
    ]
    lines = []
    for p in files:
        with p.open("rb") as stream:
            lines.append(
                hashlib.file_digest(stream, "sha256").hexdigest() + "  " + p.name
            )
    (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checksummed {len(files)} assets for {version}")


if __name__ == "__main__":
    main()

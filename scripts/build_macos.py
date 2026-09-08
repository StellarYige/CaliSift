"""Build on a native macOS runner; never cross-compile a claimed Mac release."""

import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys


def run(*args):
    subprocess.run(args, check=True)


def main():
    if sys.platform != "darwin":
        raise SystemExit("Run this build on macOS 15 or later.")
    os.environ["MACOSX_DEPLOYMENT_TARGET"] = "15.0"
    run(sys.executable, "-m", "scripts.install_ocr")
    run("npm", "run", "build", "--prefix", "desktop")
    run(sys.executable, "-m", "scripts.collect_licenses")
    run(sys.executable, "-m", "scripts.package_sources")
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "packaging/calisift-macos.spec",
    )
    run("codesign", "--verify", "--deep", "--strict", "dist/CaliSift.app")
    release = Path("artifacts/release")
    release.mkdir(parents=True, exist_ok=True)
    arch = platform.machine()
    from xingcheng import __version__

    version = __version__.replace("a", "-alpha.")
    target = release / f"CaliSift-{version}-macos-{arch}.dmg"
    run(
        "hdiutil",
        "create",
        "-volname",
        "CaliSift",
        "-srcfolder",
        "dist/CaliSift.app",
        "-ov",
        "-format",
        "UDZO",
        str(target),
    )
    run(sys.executable, "-m", "scripts.package_models")
    sums = []
    for path in sorted(release.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            with path.open("rb") as f:
                sums.append(
                    hashlib.file_digest(f, "sha256").hexdigest() + "  " + path.name
                )
    (release / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

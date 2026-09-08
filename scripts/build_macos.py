"""Build on a native macOS runner; never cross-compile a claimed Mac release."""

import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


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
    with tempfile.TemporaryDirectory(prefix="calisift-dmg-") as temporary:
        stage = Path(temporary)
        run("ditto", "dist/CaliSift.app", str(stage / "CaliSift.app"))
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        run(
            "hdiutil",
            "create",
            "-volname",
            "CaliSift",
            "-srcfolder",
            str(stage),
            "-ov",
            "-format",
            "UDZO",
            str(target),
        )
    run(sys.executable, "-m", "scripts.package_models")
    run(sys.executable, "-m", "scripts.package_manifest")


if __name__ == "__main__":
    main()

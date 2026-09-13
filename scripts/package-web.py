"""Bundle the tested static bytes and deployment instructions; never native installers."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
dist = ROOT / "web/dist"
version = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))["version"]
name = f"CaliSift-web-{version}"
artifact = ROOT / "artifacts" / f"{name}.zip"
artifact.parent.mkdir(exist_ok=True)
verified = {"SHA256SUMS"}
for line in (dist / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    checksum, filename = line.split("  ", 1)
    verified.add(filename)
    if hashlib.sha256((dist / filename).read_bytes()).hexdigest() != checksum:
        raise ValueError("Build changed after verification: " + filename)
actual = {p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file()}
if actual != verified:
    raise ValueError(
        "Unverified or missing build files: " + str(sorted(actual ^ verified))
    )
with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:

    def add(file, name):
        info = zipfile.ZipInfo(name, (2026, 9, 13, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, file.read_bytes())

    for p in sorted(dist.rglob("*")):
        if p.is_file():
            add(p, "web/dist/" + p.relative_to(dist).as_posix())
    for name in [
        "Dockerfile",
        ".dockerignore",
        "compose.yaml",
        "deploy/nginx.conf",
        "scripts/serve-web.py",
        "docs/self-hosting.md",
        "docs/verification-web.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    ]:
        add(ROOT / name, name)
checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
artifact.with_suffix(".zip.sha256").write_text(
    checksum + "  " + artifact.name + "\n", encoding="utf-8", newline="\n"
)
print(f"{artifact.name}: {artifact.stat().st_size/1048576:.1f} MiB; SHA-256 {checksum}")

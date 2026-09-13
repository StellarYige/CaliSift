"""Verify a running static deployment against the exact packaged bytes."""

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read(), response.headers.get_content_type()


def verify(base, dist):
    base = base.rstrip("/") + "/"
    for attempt in range(20):
        try:
            get(base)
            break
        except (urllib.error.URLError, OSError):
            if attempt == 19:
                raise
            time.sleep(1)
    expected = (dist / "SHA256SUMS").read_bytes()
    actual, _ = get(base + "SHA256SUMS")
    if actual != expected:
        raise ValueError("Published checksums differ from the packaged build: " + base)
    types = {
        ".html": {"text/html"},
        ".css": {"text/css"},
        ".js": {"application/javascript", "text/javascript"},
        ".mjs": {"application/javascript", "text/javascript"},
        ".wasm": {"application/wasm"},
        ".json": {"application/json"},
    }
    files = 0
    size = 0
    for line in expected.decode().splitlines():
        checksum, filename = line.split("  ", 1)
        data, mime = get(base + urllib.parse.quote(filename))
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("Published checksum mismatch: " + filename)
        allowed = types.get(Path(filename).suffix)
        if allowed and mime not in allowed:
            raise ValueError(f"Incorrect Content-Type for {filename}: {mime}")
        files += 1
        size += len(data)
    try:
        get(base + "missing-calisift-resource.wasm")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        raise ValueError("Missing assets must return 404, not an HTML fallback")
    return {
        "url": base,
        "files": files,
        "bytes": size,
        "hashes": True,
        "mime": True,
        "missing404": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("web/dist"))
    parser.add_argument("urls", nargs="+")
    args = parser.parse_args()
    print(json.dumps([verify(base, args.dist) for base in args.urls], indent=2))

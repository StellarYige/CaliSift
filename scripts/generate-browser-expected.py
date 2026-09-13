"""Explicitly regenerate the native-domain baseline for the 15 existing fixtures."""

import json
from pathlib import Path
from xingcheng.processing import execute

ROOT = Path(__file__).resolve().parents[1]
NAME = "星辰奕歌"
paths = json.loads(
    (ROOT / "tests/fixtures/table-corpus.json").read_text(encoding="utf-8")
)["synthetic_files"]
values = [
    dict(
        file=p,
        report=execute(
            dict(kind="parse", filename=Path(p).name, name=NAME, year=2026),
            (ROOT / p).read_bytes(),
        )["report"],
    )
    for p in paths
]
(ROOT / "tests/fixtures/browser-expected.json").write_text(
    json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

"""Short-lived parser process: API can enforce a hard time limit on Windows."""

import json
import sys
from pathlib import Path

from .aggregate import merge_reports
from .parsing import parse_file


def main():
    settings = json.load(sys.stdin)
    report = parse_file(
        Path(sys.argv[1]).read_bytes(),
        settings["filename"],
        settings["name"],
        settings["reference_year"],
        settings.get("layout_hint"),
    )
    if settings.get("rules"):
        from .rules import apply_rules
        from dataclasses import asdict

        for event in report.events + report.pending:
            value = apply_rules(asdict(event), settings["rules"])
            for key in ("start", "end", "end_date", "precision"):
                setattr(event, key, value.get(key))
            if value.get("field_basis"):
                for source in event.sources:
                    source.evidence["time"] = value["field_basis"]["start"]
    json.dump(merge_reports([report]).to_dict(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()

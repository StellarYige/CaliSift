"""Byte-based parsing and paginated source views, shared with browser tests."""

from dataclasses import asdict
import json

from .aggregate import merge_reports
from .parsing import parse_file
from .readers import MAX_FILE_BYTES, read_workbook


def apply_report_rules(report, rules):
    from .rules import apply_rules

    for event in report["events"] + report["pending"]:
        value = apply_rules(event, rules)
        for key in ("start", "end", "end_date", "precision"):
            event[key] = value[key]
        for source in event["sources"]:
            if value.get("field_basis"):
                source["evidence"]["time"] = value["field_basis"]["start"]
    return report


def execute(request, data):
    if not 0 < len(data) <= MAX_FILE_BYTES:
        raise ValueError("单文件必须为 1 字节至 10 MiB")
    name = request.get("name", "")
    if request["kind"] == "table":
        _, sheets = read_workbook(data, request["filename"])
        index = int(request.get("sheet", 0))
        if not 0 <= index < len(sheets):
            raise ValueError("工作表不存在")
        sheet = sheets[index]
        row, col = max(0, int(request.get("row", 0))), max(
            0, int(request.get("col", 0))
        )
        header = request.get("header_row")
        headers = (
            [c.label for c in sheet.rows[int(header)]]
            if header is not None and 0 <= int(header) < sheet.height
            else None
        )
        matches = []
        for entry in request.get("templates", []):
            layout = entry["rules"].get("template") or {}
            head = layout.get("header_row", -1)
            if (
                0 <= head < sheet.height
                and layout.get("sheet", sheet.name) == sheet.name
                and layout.get("headers") == [c.label for c in sheet.rows[head]]
            ):
                matches.append(
                    dict(
                        id=entry["id"],
                        name=entry["name"],
                        reason=f"工作表和第 {head+1} 行完整表头一致",
                    )
                )
        return dict(
            sheets=[dict(name=s.name, height=s.height, width=s.width) for s in sheets],
            sheet=sheet.name,
            row=row,
            col=col,
            headers=headers,
            template_matches=matches,
            cells=[
                [
                    dict(
                        row=c.row,
                        col=c.col,
                        coordinate=c.coordinate,
                        text=c.label[:2000],
                    )
                    for c in line[col : col + 20]
                ]
                for line in sheet.rows[row : row + 50]
            ],
        )
    if request["kind"] != "parse":
        raise ValueError("工作进程任务无效")
    report = parse_file(
        data, request["filename"], name, request["year"], request.get("layout_hint")
    )
    if request.get("rules"):
        from .rules import apply_rules

        for event in report.events + report.pending:
            value = apply_rules(asdict(event), request["rules"])
            for key in ("start", "end", "end_date", "precision"):
                setattr(event, key, value.get(key))
            for source in event.sources:
                if value.get("field_basis"):
                    source.evidence["time"] = value["field_basis"]["start"]
    return dict(report=merge_reports([report]).to_dict())

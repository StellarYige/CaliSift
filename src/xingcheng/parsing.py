from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from .models import Event, Report, Source
from .readers import Cell, FileProblem, Sheet, read_workbook, text
from .temporal import Context, TimeValue, infer_context, parse_date, parse_time

ALIASES = {
    "name": {
        "姓名",
        "人员",
        "值班人员",
        "值班人",
        "参加人员",
        "参与人员",
        "培训人员",
        "教师",
        "老师",
        "学生",
        "考生",
        "员工",
        "人员姓名",
        "监考人员",
        "监考老师",
    },
    "date": {
        "日期",
        "时间日期",
        "值班日期",
        "培训日期",
        "考试日期",
        "上课日期",
        "排班日期",
        "日程日期",
        "考试时间",
        "培训时间",
        "上课时间",
        "日期时间",
    },
    "time": {"时间", "时段", "起止时间", "值班时间", "上课时段"},
    "start": {"开始", "开始时间", "起始时间"},
    "end": {"结束", "结束时间", "截止时间"},
    "shift": {"班次", "班别", "班型"},
    "title": {
        "事项",
        "内容",
        "安排",
        "活动",
        "培训内容",
        "培训项目",
        "课程",
        "课程名称",
        "科目",
        "考试科目",
        "任务",
        "工作内容",
        "项目",
    },
    "location": {
        "地点",
        "位置",
        "教室",
        "考场",
        "培训地点",
        "考试地点",
        "上课地点",
        "工作地点",
    },
    "notes": {"备注", "说明", "注意事项"},
}
REST = {"休", "休息", "轮休", "调休", "公休", "休假", "请假", "年假"}
EMPTY = {"", "-", "—", "/", "无"}
SHIFT = re.compile(
    r"(?:早班|中班|晚班|夜班|白班|日班|大夜|小夜|值班|休息|调休|轮休|公休|休假|年假)"
)


def matches_name(value, name: str) -> bool:
    return name in re.split(r"[\s、,;；，/|]+", text(value))


def field_name(value) -> str | None:
    # Only remove known input-format annotations; arbitrary parentheses may carry meaning.
    value = re.sub(
        r"[（(]\s*(?:YYYY-MM-DD|yyyy-mm-dd|年/月/日|24小时制|HH:mm|HH:MM|完整姓名)\s*[）)]\s*$",
        "",
        text(value),
    )
    label = re.sub(r"[\s:：/()（）]", "", value)
    for key, aliases in ALIASES.items():
        if label in aliases:
            return key
    return None


def _header(sheet: Sheet, r: int, c0: int, c1: int) -> dict[str, list[Cell]]:
    result = {}
    for c in range(c0, c1):
        cell = sheet.at(r, c)
        key = field_name(cell.value)
        if key:
            result.setdefault(key, []).append(cell)
    return result


def _regions(sheet: Sheet):
    """Split at completely empty separators and repeated record headers."""
    spans = []
    start = None
    for r in range(sheet.height + 1):
        active = r < sheet.height and any(
            c.label or c.formula_missing for c in sheet.rows[r]
        )
        if active and start is None:
            start = r
        if not active and start is not None:
            spans.append((start, r))
            start = None
    for r0, r1 in spans:
        column_spans = []
        start = None
        for c in range(sheet.width + 1):
            active = c < sheet.width and any(
                sheet.at(r, c).label or sheet.at(r, c).formula_missing
                for r in range(r0, r1)
            )
            if active and start is None:
                start = c
            if not active and start is not None:
                column_spans.append((start, c))
                start = None
        for c0, c1 in column_spans:
            cut = r0
            seen_header = False
            for r in range(r0, r1):
                headers = _header(sheet, r, c0, c1)
                date_axis = any(
                    parse_date(sheet.at(r, c).value, Context(2000, 1, True), True)[0]
                    for c in range(c0, c1)
                    if field_name(sheet.at(r, c).value) != "name"
                )
                is_header = "name" in headers and (
                    date_axis
                    or any(k in headers for k in ("date", "time", "title", "shift"))
                )
                if is_header and seen_header:
                    # Include a new title immediately above a repeated header.
                    prev = {
                        sheet.at(r - 1, c).coordinate: sheet.at(r - 1, c).label
                        for c in range(c0, c1)
                        if sheet.at(r - 1, c).label
                    }
                    boundary = r - 1 if len(prev) == 1 and r - 1 > cut else r
                    yield cut, boundary, c0, c1
                    cut = boundary
                seen_header = seen_header or is_header
            yield cut, r1, c0, c1


def _context(sheet, bounds, filename, year):
    r0, r1, c0, c1 = bounds
    labels = []
    for r in range(r0, min(r0 + 5, r1)):
        unique = {
            sheet.at(r, c).coordinate: sheet.at(r, c).label
            for c in range(c0, c1)
            if sheet.at(r, c).label
        }
        if len(unique) == 1:
            label = next(iter(unique.values()))
            if not field_name(label):
                labels.append(label)
        elif unique:
            break
    # A separated one-line title immediately above the block remains relevant.
    if r0 >= 2 and not any(c.label for c in sheet.rows[r0 - 1]):
        prev = {
            sheet.at(r0 - 2, c).coordinate: sheet.at(r0 - 2, c).label
            for c in range(c0, c1)
            if sheet.at(r0 - 2, c).label
        }
        if len(prev) == 1:
            labels.append(next(iter(prev.values())))
    return infer_context(labels[::-1] + [sheet.name, Path(filename).stem], year), labels


def _legends(sheet: Sheet) -> dict[str, tuple[TimeValue, str]]:
    result = {}

    def remember(key, timing, evidence):
        existing = result.get(key)
        if existing and existing[0] != timing:
            result[key] = (
                TimeValue(warning="同一班次存在不同时间定义"),
                existing[1] + ", " + evidence,
            )
        else:
            result[key] = (timing, evidence)

    for row in sheet.rows:
        populated = {c.coordinate for c in row if c.label}
        for cell in row:
            label = cell.label
            match = re.match(
                r"^(早班|中班|晚班|夜班|白班|日班|大夜|小夜|早|中|晚|夜)\s*[:：=]",
                label,
            )
            if match:
                timing = parse_time(label)
                if timing.start:
                    remember(match[1], timing, cell.coordinate)
            if len(populated) == 2 and (
                SHIFT.fullmatch(label) or label in {"早", "中", "晚", "夜"}
            ):
                right = sheet.at(cell.row, cell.col + 1)
                timing = parse_time(right.value)
                if timing.start:
                    remember(label, timing, cell.coordinate + ", " + right.coordinate)
    return result


def _base_title(filename, labels):
    label = labels[-1] if labels else Path(filename).stem
    label = re.sub(r"(?:\d{4}年)?\d{1,2}月(?:\d{1,2}日)?", "", label)
    label = re.sub(r"(?:安排表|安排|排班表|课程表|培训表|值班表|表)$", "", label).strip(
        " _-"
    )
    return label or "个人安排"


def _make_event(
    sheet,
    name_cell,
    fields,
    context,
    filename,
    file_id,
    title,
    legends,
    extra_warnings=None,
):
    evidence = {
        key: ", ".join(dict.fromkeys(c.coordinate for c in cells))
        for key, cells in fields.items()
        if cells
    }
    source = Source(
        file_id,
        filename,
        sheet.name,
        name_cell.coordinate,
        evidence,
        " | ".join(
            dict.fromkeys(
                c.label for cells in fields.values() for c in cells if c.label
            )
        )[:600],
        sheet.hidden,
    )
    warnings = list(extra_warnings or [])
    dates = set()
    for cell in fields.get("date", []):
        parsed, messages = parse_date(cell.value, context, allow_day=True)
        warnings.extend(messages)
        if parsed:
            dates.add(parsed)
    event_date = next(iter(dates)) if len(dates) == 1 else None
    if len(dates) > 1:
        warnings.append("日期证据相互矛盾")
    if event_date is None:
        warnings.append("无法确定具体日期，请核对源表；周期课表需补充学期和节次信息")

    def unique_value(key):
        labels = list(dict.fromkeys(c.label for c in fields.get(key, []) if c.label))
        if len(labels) > 1:
            warnings.append(f"{key} 字段存在多个值，请核对")
        return labels[0] if len(labels) == 1 else " / ".join(labels)

    shift = unique_value("shift")
    item = unique_value("title")
    value = unique_value("value")
    if not shift:
        found = SHIFT.search(value)
        if found:
            shift = found[0]
        elif value in legends or value in REST:
            shift = value
    if not item:
        # Names are never passed as the value of a person-filled matrix.
        item = (
            shift
            or re.sub(r"(?:上午|下午|晚上|凌晨)?\s*\d{1,2}:\d{2}.*$", "", value).strip(
                " -:："
            )
            or title
        )
    timing_candidates = []
    date_time_cells = [
        c
        for c in fields.get("date", [])
        if hasattr(c.value, "hour") or re.search(r"\d[:点时]", c.label)
    ]
    for cell in (
        fields.get("time", [])
        + date_time_cells
        + fields.get("value", [])
        + fields.get("shift", [])
    ):
        # Day numbers on date axes are not hour ranges.
        timing = parse_time(cell.value)
        if timing.warning:
            warnings.append(timing.warning)
        if timing.start:
            timing_candidates.append(timing)
    for key in ("start", "end"):
        for cell in fields.get(key, []):
            timing = parse_time(cell.value)
            if timing.warning:
                warnings.append(timing.warning)
    start_values = {parse_time(c.value).start for c in fields.get("start", [])} - {None}
    end_values = {parse_time(c.value).start for c in fields.get("end", [])} - {None}
    if len(start_values) > 1 or len(end_values) > 1:
        warnings.append("起止时间证据相互矛盾")
    elif start_values:
        start = next(iter(start_values))
        end = next(iter(end_values)) if end_values else None
        if end == start:
            warnings.append("起止时间相同，区间关系需确认")
        else:
            timing_candidates.append(TimeValue(start, end, bool(end and end < start)))
    if not timing_candidates and shift in legends:
        timing, legend_evidence = legends[shift]
        if timing.warning:
            warnings.append(timing.warning)
        elif timing.start:
            timing_candidates.append(timing)
            source.evidence["time"] = legend_evidence + "（班次图例）"
    timing = TimeValue()
    if timing_candidates:
        # A date-time cell can corroborate the start of an explicit range.
        starts = {t.start for t in timing_candidates}
        ends = {t.end for t in timing_candidates if t.end}
        if len(starts) > 1 or len(ends) > 1:
            warnings.append("时间证据相互矛盾")
        else:
            timing = max(timing_candidates, key=lambda t: bool(t.end))
    if any(c.formula_missing for cells in fields.values() for c in cells):
        warnings.append("关联单元格公式缺少缓存值")
    location = unique_value("location")
    ambiguous = any(
        any(
            word in w
            for word in (
                "矛盾",
                "多个值",
                "多个时间段",
                "不同时间定义",
                "有效范围",
                "区间关系",
                "缺少缓存",
            )
        )
        for w in warnings
    )
    status = "pending" if event_date is None or ambiguous else "confirmed"
    return Event(
        date=event_date.isoformat() if event_date else None,
        title=item,
        shift=shift,
        start=timing.start,
        end=timing.end,
        end_date=(
            (event_date + timedelta(days=int(timing.next_day))).isoformat()
            if event_date and timing.end
            else None
        ),
        precision="interval" if timing.end else "point" if timing.start else "date",
        location=location,
        notes=[c.label for c in fields.get("notes", []) if c.label],
        sources=[source],
        warnings=list(dict.fromkeys(warnings)),
        status=status,
    )


def _record_table(sheet, bounds, name, context, filename, file_id, title, legends):
    r0, r1, c0, c1 = bounds
    for header_row in range(r0, r1):
        headers = _header(sheet, header_row, c0, c1)
        if "name" not in headers or not any(
            k in headers for k in ("date", "time", "title", "shift")
        ):
            continue
        found, used = [], set()
        for r in range(header_row + 1, r1):
            name_cells = [
                sheet.at(r, h.col)
                for h in headers["name"]
                if matches_name(sheet.at(r, h.col).value, name)
            ]
            if not name_cells:
                continue
            fields = {
                key: [sheet.at(r, cell.col) for cell in cells]
                for key, cells in headers.items()
                if key != "name"
            }
            # Combined date/time header often literally reads “时间”.
            if "date" not in fields:
                fields["date"] = fields.get("time", [])
            used.update(c.coordinate for c in name_cells)
            found.append(
                _make_event(
                    sheet,
                    name_cells[0],
                    fields,
                    context,
                    filename,
                    file_id,
                    title,
                    legends,
                )
            )
        return found, used, True
    return [], set(), False


def _axis_date(sheet, coordinates, context):
    """Nearest valid date in an axis, retaining invalid-date evidence too."""
    for r, c in coordinates:
        cell = sheet.at(r, c)
        parsed, messages = parse_date(cell.value, context, allow_day=True)
        if parsed or messages:
            return cell
    return None


def _axis_labels(sheet, coordinates):
    fields = {}
    for r, c in coordinates:
        cell = sheet.at(r, c)
        if not cell.label:
            continue
        if SHIFT.search(cell.label):
            fields.setdefault("shift", []).append(cell)
            break
        if parse_time(cell.value).start:
            fields.setdefault("time", []).append(cell)
            break
    return fields


def _matrix_metadata(sheet, bounds, name_cell, orientation):
    r0, r1, c0, c1 = bounds
    result = {}
    if orientation == "row":
        for c in range(c0, c1):
            for r in range(name_cell.row - 1, r0 - 1, -1):
                key = field_name(sheet.at(r, c).value)
                if key in ("location", "notes"):
                    result.setdefault(key, []).append(sheet.at(name_cell.row, c))
                    break
    else:
        for r in range(r0, r1):
            for c in range(name_cell.col - 1, c0 - 1, -1):
                key = field_name(sheet.at(r, c).value)
                if key in ("location", "notes"):
                    result.setdefault(key, []).append(sheet.at(r, name_cell.col))
                    break
    return result


def _matrix(sheet, bounds, name, context, filename, file_id, title, legends):
    r0, r1, c0, c1 = bounds
    events, used = [], set()
    for r in range(r0, r1):
        for c in range(c0, c1):
            name_cell = sheet.at(r, c)
            if not matches_name(name_cell.value, name):
                continue
            own_above = _axis_date(
                sheet, ((rr, c) for rr in range(r - 1, r0 - 1, -1)), context
            )
            own_left = _axis_date(
                sheet, ((r, cc) for cc in range(c - 1, c0 - 1, -1)), context
            )
            # Name is a row header: dated columns above, schedules to the right.
            row_results = []
            for cc in range(c + 1, c1) if not own_above and not own_left else []:
                date_cell = _axis_date(
                    sheet, ((rr, cc) for rr in range(r - 1, r0 - 1, -1)), context
                )
                schedule = sheet.at(r, cc)
                if date_cell and (
                    schedule.label not in EMPTY or schedule.formula_missing
                ):
                    fields = {"date": [date_cell], "value": [schedule]}
                    fields.update(_matrix_metadata(sheet, bounds, name_cell, "row"))
                    fields.update(
                        _axis_labels(
                            sheet, ((rr, cc) for rr in range(r - 1, date_cell.row, -1))
                        )
                    )
                    row_results.append(
                        _make_event(
                            sheet,
                            name_cell,
                            fields,
                            context,
                            filename,
                            file_id,
                            title,
                            legends,
                        )
                    )
            # Name is a column header: dated rows below, schedules in this column.
            col_results = []
            for rr in range(r + 1, r1) if not own_above and not own_left else []:
                date_cell = _axis_date(
                    sheet, ((rr, cc) for cc in range(c - 1, c0 - 1, -1)), context
                )
                schedule = sheet.at(rr, c)
                if date_cell and (
                    schedule.label not in EMPTY or schedule.formula_missing
                ):
                    fields = {"date": [date_cell], "value": [schedule]}
                    fields.update(_matrix_metadata(sheet, bounds, name_cell, "column"))
                    fields.update(
                        _axis_labels(
                            sheet, ((rr, cc) for cc in range(c - 1, date_cell.col, -1))
                        )
                    )
                    col_results.append(
                        _make_event(
                            sheet,
                            name_cell,
                            fields,
                            context,
                            filename,
                            file_id,
                            title,
                            legends,
                        )
                    )
            if row_results or col_results:
                results = row_results + col_results
                if row_results and col_results:
                    for event in results:
                        event.status = "pending"
                        event.warnings.append("姓名同时符合行标题和列标题，布局需确认")
                events.extend(results)
                used.add(name_cell.coordinate)
                continue
            # Name fills the intersection of a date axis and a shift/time axis.
            above = _axis_date(
                sheet, ((rr, c) for rr in range(r - 1, r0 - 1, -1)), context
            )
            left = _axis_date(
                sheet, ((r, cc) for cc in range(c - 1, c0 - 1, -1)), context
            )
            if above or left:
                fields = {"date": [x for x in (above, left) if x]}
                fields.update(
                    _matrix_metadata(
                        sheet, bounds, name_cell, "row" if left else "column"
                    )
                )
                if above:
                    fields.update(
                        _axis_labels(
                            sheet, ((r, cc) for cc in range(c - 1, c0 - 1, -1))
                        )
                    )
                if left:
                    fields.update(
                        _axis_labels(
                            sheet, ((rr, c) for rr in range(r - 1, r0 - 1, -1))
                        )
                    )
                events.append(
                    _make_event(
                        sheet,
                        name_cell,
                        fields,
                        context,
                        filename,
                        file_id,
                        title,
                        legends,
                    )
                )
                used.add(name_cell.coordinate)
    return events, used


def parse_file(
    data: bytes, filename: str, name: str, reference_year: int, layout_hint=None
) -> Report:
    name = text(name)
    if not name or len(name) > 80 or re.search(r"[\s、,;；，/|]", name):
        raise ValueError("请输入一个完整姓名（不含分隔符）")
    if not 1900 <= reference_year <= 2199:
        raise ValueError("补全年份应在 1900–2199 之间")
    report = Report()
    try:
        file_id, sheets = read_workbook(data, filename)
    except FileProblem as exc:
        report.files.append(
            {"filename": filename, "status": "error", "error": str(exc), "sheets": []}
        )
        return report
    return parse_sheets(file_id, sheets, filename, name, reference_year, layout_hint)


def parse_sheets(file_id, sheets, filename, name, reference_year, layout_hint=None):
    report = Report()
    sheet_status = []
    for sheet in sheets:
        preview = [
            [{"cell": c.coordinate, "text": c.label} for c in row[:15]]
            for row in sheet.rows[:20]
        ]
        template_error = ""
        if layout_hint and (
            not layout_hint.get("sheet") or layout_hint["sheet"] == sheet.name
        ):
            try:
                header_row = int(layout_hint["header_row"])
                actual = [c.label for c in sheet.rows[header_row]]
                if actual != layout_hint["headers"]:
                    raise ValueError("表头或结构与模板不一致，请重新核对")
                if layout_hint["layout"] == "records":
                    for field, col in layout_hint["mapping"].items():
                        if field in ALIASES and 0 <= int(col) < sheet.width:
                            sheet.at(header_row, int(col)).value = sorted(
                                ALIASES[field]
                            )[0]
            except (ValueError, KeyError, IndexError, TypeError):
                template_error = "表头或结构与模板不一致，请重新核对"
                sheet.warnings.append(template_error)
        hits = {
            c.coordinate: c
            for row in sheet.rows
            for c in row
            if matches_name(c.value, name)
        }
        used = set()
        events = []
        legends = _legends(sheet)
        recognized = False
        active_hint = (
            layout_hint
            if layout_hint
            and (not layout_hint.get("sheet") or layout_hint["sheet"] == sheet.name)
            else None
        )
        explicit_matrix = (
            active_hint
            and active_hint.get("layout") in ("names_rows", "names_columns")
            and not template_error
        )
        if explicit_matrix:
            context, labels = _context(
                sheet, (0, sheet.height, 0, sheet.width), filename, reference_year
            )
            mapping = active_hint["mapping"]
            name_axis, date_axis = int(mapping["name"]), int(mapping["date"])
            horizontal = active_hint["layout"] == "names_rows"
            if not (
                0 <= name_axis < (sheet.width if horizontal else sheet.height)
                and 0 <= date_axis < (sheet.height if horizontal else sheet.width)
            ):
                raise ValueError("姓名或日期区域超出表格范围")
            for name_cell in hits.values():
                if (name_cell.col if horizontal else name_cell.row) != name_axis:
                    continue
                for i in range(sheet.width if horizontal else sheet.height):
                    if i == name_axis:
                        continue
                    value = (
                        sheet.at(name_cell.row, i)
                        if horizontal
                        else sheet.at(i, name_cell.col)
                    )
                    day = (
                        sheet.at(date_axis, i) if horizontal else sheet.at(i, date_axis)
                    )
                    if value.label in EMPTY or not day.label:
                        continue
                    events.append(
                        _make_event(
                            sheet,
                            name_cell,
                            {"date": [day], "value": [value]},
                            context,
                            filename,
                            file_id,
                            _base_title(filename, labels),
                            legends,
                        )
                    )
                    used.add(name_cell.coordinate)
            recognized = bool(events)
        for bounds in [] if template_error or explicit_matrix else _regions(sheet):
            context, labels = _context(sheet, bounds, filename, reference_year)
            title = _base_title(filename, labels)
            extracted, consumed, is_record = _record_table(
                sheet, bounds, name, context, filename, file_id, title, legends
            )
            recognized = recognized or is_record
            if not is_record:
                extracted, consumed = _matrix(
                    sheet, bounds, name, context, filename, file_id, title, legends
                )
            recognized = recognized or bool(extracted)
            events.extend(extracted)
            used.update(consumed)
        for coordinate in sorted(hits.keys() - used):
            cell = hits[coordinate]
            surrounding = [
                sheet.at(r, c).label
                for r in range(max(0, cell.row - 1), min(sheet.height, cell.row + 2))
                for c in range(max(0, cell.col - 1), min(sheet.width, cell.col + 2))
            ]
            events.append(
                Event(
                    None,
                    "待确认安排",
                    sources=[
                        Source(
                            file_id,
                            filename,
                            sheet.name,
                            coordinate,
                            excerpt=" | ".join(filter(None, surrounding))[:600],
                            hidden=sheet.hidden,
                        )
                    ],
                    warnings=["找到姓名，但无法可靠关联日期和事项；周期课表暂不展开"],
                    status="pending",
                )
            )
        for event in events:
            (report.pending if event.status == "pending" else report.events).append(
                event
            )
        status = "matched" if hits else "no_match"
        if not any(c.label or c.formula_missing for row in sheet.rows for c in row):
            status = "empty"
        sheet_status.append(
            {
                "sheet": sheet.name,
                "status": status,
                "name_matches": len(hits),
                "events": sum(e.status == "confirmed" for e in events),
                "pending": sum(e.status == "pending" for e in events),
                "recognized_layout": recognized,
                "hidden": sheet.hidden,
                "warnings": sheet.warnings,
                "preview": preview,
            }
        )
        report.warnings.extend(
            f"{filename} / {sheet.name}：{w}" for w in sheet.warnings
        )
    report.files.append(
        {
            "file_id": file_id,
            "filename": filename,
            "status": "ok",
            "sheets": sheet_status,
        }
    )
    return report

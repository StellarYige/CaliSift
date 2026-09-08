"""Evaluate independently annotated corpora; synthetic regressions cannot pass acceptance gates."""

import argparse
import json
from pathlib import Path
import time

from xingcheng.parsing import parse_file
from xingcheng.aggregate import merge_reports

FIELDS = ("date", "title", "start", "end", "end_date", "location")


def key(event):
    return tuple(event.get(k) or "" for k in FIELDS)


def anchor_matches(source, anchor):
    return (
        source.get("sheet") == anchor.get("sheet")
        and source.get("name_cell") == anchor.get("name_cell")
        and bool(anchor.get("evidence"))
        and all(
            source.get("evidence", {}).get(k) == v
            for k, v in anchor["evidence"].items()
        )
    )


def score_case(actual, expected, identity_cells):
    """Pair by annotated source cells, never by predicted title/date or list order."""
    correct = dates = times = ambiguous = unanchored = 0
    used = set()
    for event in expected:
        anchors = event.get("anchors", [])
        if not anchors:
            unanchored += 1
            continue
        candidates = [
            i
            for i, item in enumerate(actual)
            if i not in used
            and any(
                anchor_matches(source, anchor)
                for source in item.get("sources", [])
                for anchor in anchors
            )
        ]
        if len(candidates) != 1:
            ambiguous += int(len(candidates) > 1)
            continue
        index = candidates[0]
        used.add(index)
        item = actual[index]
        correct += key(item) == key(event)
        dates += item.get("date") == event.get("date")
        times += all(
            (item.get(k) or "") == (event.get(k) or "")
            for k in ("start", "end", "end_date")
        )
    names = sum(
        not e.get("sources")
        or any(
            not any(
                s.get("sheet") == a["sheet"] and s.get("name_cell") == a["cell"]
                for a in identity_cells
            )
            for s in e.get("sources", [])
        )
        for e in actual
    )
    return dict(
        correct=correct,
        date_correct=dates,
        time_correct=times,
        name_mismatches=names,
        ambiguous_anchors=ambiguous,
        unanchored=unanchored,
    )


def evaluate(manifest_path, acceptance=False):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    ocr_engine = None
    for case in manifest["cases"]:
        file = (manifest_path.parent / case["file"]).resolve()
        started = time.perf_counter()
        if case["kind"] == "image":
            from xingcheng.ocr import engine, recognize

            ocr_engine = ocr_engine or engine()
            report = recognize(
                file.read_bytes(),
                file.name,
                case["name"],
                case["year"],
                case.get("options", {}),
                ocr_engine,
            )
        else:
            report = merge_reports(
                [
                    parse_file(
                        file.read_bytes(),
                        file.name,
                        case["name"],
                        case["year"],
                        case.get("template"),
                    )
                ]
            ).to_dict()
        actual = report["events"] + report["pending"]
        expected = case["expected"]
        score = score_case(actual, expected, case["identity_cells"])
        results.append(
            dict(
                id=case["id"],
                kind=case["kind"],
                layout=case["layout"],
                provenance=case["provenance"],
                expected=len(expected),
                produced=len(actual),
                **score,
                pending=len(report["pending"]),
                manual_operations=case.get("manual_operations"),
                split=case.get("split", manifest.get("split", "development")),
                license=case.get("license"),
                seconds=round(time.perf_counter() - started, 3),
            )
        )
    totals = {}
    for kind in ("table", "image"):
        group = [r for r in results if r["kind"] == kind]
        expected = sum(r["expected"] for r in group)
        produced = sum(r["produced"] for r in group)
        correct = sum(r["correct"] for r in group)
        totals[kind] = dict(
            cases=len(group),
            independent_layouts=len({r["layout"] for r in group}),
            precision=correct / produced if produced else 0,
            recall=correct / expected if expected else 0,
            date_accuracy=(
                sum(r["date_correct"] for r in group) / expected if expected else 0
            ),
            time_accuracy=(
                sum(r["time_correct"] for r in group) / expected if expected else 0
            ),
            pending_ratio=(
                sum(r["pending"] for r in group) / produced if produced else 0
            ),
            name_mismatches=sum(r["name_mismatches"] for r in group),
            manual_operations=(
                sum(r["manual_operations"] for r in group)
                if group and all(r["manual_operations"] is not None for r in group)
                else None
            ),
        )
    blockers = []
    if any(r["split"] != "acceptance" for r in results):
        blockers.append("包含开发样本，未划入独立验收集")
    if any(not r["license"] for r in results):
        blockers.append("缺少样本授权记录")
    if any(r["ambiguous_anchors"] or r["unanchored"] for r in results):
        blockers.append("存在缺失或歧义的字段依据标注")
    if totals["table"]["independent_layouts"] < 20:
        blockers.append("不足 20 种独立表格布局")
    if totals["image"]["cases"] < 20:
        blockers.append("不足 20 张验收图片")
    if any(r["provenance"] == "synthetic" for r in results):
        blockers.append("含合成开发样本，不能充当独立真实照片验收集")
    if not manifest.get("independent_review"):
        blockers.append("尚无独立人工标注复核记录")
    if any(r["manual_operations"] is None for r in results):
        blockers.append("尚未记录全部手动修正操作量")
    if totals["table"]["precision"] < 1 or totals["table"]["recall"] < 1:
        blockers.append("干净表格尚未完整无误提取")
    if totals["image"]["precision"] < 0.98 or totals["image"]["recall"] < 0.95:
        blockers.append("图片未达到 98% 精确率 / 95% 召回率目标")
    if sum(r["name_mismatches"] for r in results):
        blockers.append("存在姓名错误关联")
    return dict(
        acceptance_passed=not blockers, blockers=blockers, totals=totals, cases=results
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.manifest, args.acceptance)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    if args.acceptance and not result["acceptance_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

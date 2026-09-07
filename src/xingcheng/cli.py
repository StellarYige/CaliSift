"""Explicit CLI operations; preview is the default for calendar mutations."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from . import __version__
from .localstore import atomic_write, encode


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) if path else {}


def parser():
    root = argparse.ArgumentParser(
        prog="calisift", description="Local, verifiable personal calendars."
    )
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument(
        "--data-dir",
        help="Local data directory (desktop and CLI must not open it simultaneously)",
    )
    commands = root.add_subparsers(dest="command", required=True)
    for kind in ("parse", "ocr"):
        command = commands.add_parser(
            kind, help="Extract to JSON; no calendar mutation"
        )
        command.add_argument("file")
        command.add_argument("--name", required=True)
        command.add_argument("--year", type=int, default=date.today().year)
        command.add_argument("--rules")
        command.add_argument("--options")
        command.add_argument("--output")
    workspace = commands.add_parser("workspace")
    workspace.add_argument("--create", metavar="NAME")
    imp = commands.add_parser(
        "import", help="Persist a draft; --commit confirms the resulting append preview"
    )
    imp.add_argument("files", nargs="+")
    imp.add_argument("--workspace", required=True)
    imp.add_argument("--year", type=int, default=date.today().year)
    imp.add_argument("--rules")
    imp.add_argument("--source-name", default="命令行导入")
    imp.add_argument("--commit", action="store_true")
    change = commands.add_parser(
        "change", help="Preview a JSON operation; explicitly add --commit to apply"
    )
    change.add_argument("--workspace", required=True)
    change.add_argument("--operation", required=True)
    change.add_argument("--expected-version", type=int, required=True)
    change.add_argument("--job")
    change.add_argument("--commit", action="store_true")
    for kind in ("export", "backup"):
        command = commands.add_parser(kind)
        command.add_argument("--workspace", required=True)
        command.add_argument("--output", required=True)
        if kind == "export":
            command.add_argument("--options")
    restore = commands.add_parser(
        "restore", help="Preview a backup; --commit creates an independent workspace"
    )
    restore.add_argument("file")
    restore.add_argument("--commit", action="store_true")
    commands.add_parser("desktop")
    commands.add_parser(
        "doctor", help="Show local data location and OCR model readiness"
    )
    commands.add_parser(
        "checkpoint", help="Create a consistent recovery point before an upgrade"
    )
    return root


def execute(args):
    if args.command in ("parse", "ocr"):
        if args.command == "parse":
            from .desktop_worker import execute as extract

            result = extract(
                dict(
                    kind="parse",
                    path=args.file,
                    filename=Path(args.file).name,
                    name=args.name,
                    year=args.year,
                    rules=read_json(args.rules),
                    layout_hint=read_json(args.rules).get("template"),
                )
            )["report"]
        else:
            options = read_json(args.options)
            rules = read_json(args.rules)
            options["layout_hint"] = rules.get("template")
            command = (
                [str(Path(sys.executable).parent / "calisift-worker.exe")]
                if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "xingcheng.desktop_worker"]
            )
            request = dict(
                kind="ocr",
                path=str(Path(args.file).resolve()),
                filename=Path(args.file).name,
                name=args.name,
                year=args.year,
                options=options,
                rules=rules,
            )
            process = subprocess.run(
                command,
                input=encode(request),
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            output = json.loads(process.stdout) if process.stdout else {}
            if process.returncode or "error" in output:
                raise ValueError(
                    output.get("error") or "图片识别进程失败，请检查模型后重试"
                )
            result = output["report"]
        if args.output:
            atomic_write(Path(args.output), encode(result).encode("utf-8"))
            return dict(output=str(Path(args.output).resolve()))
        return result
    if args.command == "desktop":
        from .desktop import main

        main(args.data_dir)
        return dict(closed=True)
    from .application import Application

    if args.data_dir:
        directory = Path(args.data_dir)
    else:
        directory = Path(
            os.environ.get("CALISIFT_DATA_DIR")
            or (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
                / "CaliSift"
            )
        )
    app = Application(directory)
    try:
        if args.command == "doctor":
            return {
                **app.capabilities(),
                "python": sys.version.split()[0],
                "platform": sys.platform,
            }
        if args.command == "checkpoint":
            return dict(path=str(app.store.safety_backup("upgrade")))
        if args.command == "workspace":
            return (
                app.create_workspace(args.create)
                if args.create
                else app.store.workspaces()
            )
        if args.command == "import":
            job = app.jobs.stage(args.workspace, args.files)
            app.jobs.start(job["id"], args.year, read_json(args.rules))
            while app.get_job(job["id"])["status"] in ("running", "queued"):
                time.sleep(0.1)
            job = app.get_job(job["id"])
            if job["status"] != "review":
                return job
            preview = app.preview_change(
                args.workspace,
                app.workspace(args.workspace)["version"],
                dict(type="append", source_name=args.source_name),
                job["id"],
            )
            result = dict(job_id=job["id"], report=job["report"], preview=preview)
            if args.commit:
                result["committed"] = app.commit_change(
                    preview["preview_id"], preview["base_version"]
                )
            return result
        if args.command == "change":
            result = app.preview_change(
                args.workspace,
                args.expected_version,
                read_json(args.operation),
                args.job,
            )
            if args.commit:
                result["committed"] = app.commit_change(
                    result["preview_id"], result["base_version"]
                )
            return result
        if args.command == "export":
            return app.export_file(
                args.workspace,
                app.workspace(args.workspace)["version"],
                read_json(args.options),
                args.output,
            )
        if args.command == "backup":
            return app.backup_file(args.workspace, args.output)
        if args.command == "restore":
            result = app.prepare_restore(Path(args.file).read_bytes())
            return app.restore_backup(result["token"]) if args.commit else result
    finally:
        app.close()


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except Exception as exc:
        print(
            encode(
                dict(
                    error=dict(
                        code=getattr(exc, "code", "OPERATION_FAILED"), message=str(exc)
                    )
                )
            ),
            file=sys.stderr,
        )
        return 1
    print(encode(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

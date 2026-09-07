"""Install, upgrade and uninstall in a temporary directory; preserve test data."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("installer", type=Path)
    args = parser.parse_args()
    # Do not overwrite an installation owned by someone using the same account.
    import winreg

    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{BF44D1E4-0583-4201-8966-C19733FC8EE2}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError(
                "An existing CaliSift installation is registered. Use a separate test account."
            )
    except FileNotFoundError:
        pass
    result = dict(passed=False, checks=[])
    target = Path("artifacts/install-smoke.json")
    with tempfile.TemporaryDirectory(prefix="calisift-install-") as folder:
        root = Path(folder)
        install = root / "program"
        data = root / "data"
        env = {
            **os.environ,
            "CALISIFT_DATA_DIR": str(data),
            "PATH": os.path.join(os.environ["SystemRoot"], "System32"),
        }
        setup = [
            str(args.installer.resolve()),
            "/CURRENTUSER",
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NOICONS",
            f"/DIR={install}",
        ]

        def run(command):
            value = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if value.returncode:
                raise RuntimeError(
                    f"Command failed ({value.returncode}): {Path(command[0]).name}: {value.stderr[-500:]}"
                )
            return value.stdout

        def cli(*values):
            return json.loads(run([str(install / "calisift-cli.exe"), *values]))

        def snapshot():
            with closing(sqlite3.connect(data / "calendar.sqlite3")) as db:
                return db.execute(
                    "SELECT id,version,calendar FROM workspaces ORDER BY id"
                ).fetchall()

        def uninstall():
            uninstaller = install / "unins000.exe"
            run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
            # Inno's original loader can return before its temporary uninstaller exits.
            until = time.monotonic() + 30
            while uninstaller.exists() and time.monotonic() < until:
                time.sleep(0.2)
            assert not uninstaller.exists(), "Native uninstall did not finish"

        try:
            start = time.perf_counter()
            run(setup)
            result["install_seconds"] = round(time.perf_counter() - start, 2)
            assert (install / "CaliSift.exe").is_file()
            result["checks"].append(
                "per-user full installer completed with WebView2 already present"
            )
            # The installed GUI is exercised through real native dialogs and OCR.
            ui = subprocess.run(
                [
                    os.sys.executable,
                    "-X",
                    "utf8",
                    "-m",
                    "scripts.smoke_packaged",
                    str(install / "CaliSift.exe"),
                ],
                timeout=180,
            )
            assert ui.returncode == 0
            result["checks"].append(
                "installed GUI, native dialogs, OCR, ICS and restart passed"
            )
            assert cli("doctor")["ocr"]["ready"]
            wid = cli("workspace", "--create", "星辰奕歌")["id"]
            value = cli(
                "import",
                str(Path("samples/九月排班.csv").resolve()),
                "--workspace",
                wid,
                "--year",
                "2026",
                "--commit",
            )
            assert value["committed"]["version"] == 1
            before = snapshot()
            run(setup)
            assert snapshot() == before
            assert list((data / "backups").glob("*-upgrade-*.sqlite3"))
            result["checks"].append(
                "upgrade created a consistent recovery point and preserved identities/version"
            )
            backup = root / "calendar.calisift-backup.zip"
            cli("backup", "--workspace", wid, "--output", str(backup))
            cli("restore", str(backup), "--commit")
            assert len(cli("workspace")) == 2
            result["checks"].append(
                "installed CLI portable backup restored into a separate workspace"
            )
            before = snapshot()
            uninstall()
            assert not (install / "CaliSift.exe").exists()
            assert snapshot() == before
            result["checks"].append(
                "uninstall removed program files and retained user database and backup"
            )
            result["passed"] = True
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            uninstaller = install / "unins000.exe"
            if uninstaller.exists():
                try:
                    uninstall()
                except Exception:
                    result["cleanup_error"] = traceback.format_exc()
                    result["passed"] = False
            target.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate a Windows-produced backup fixture for restore checks on all CI systems."""

import json
from pathlib import Path
import tempfile
from xingcheng.application import Application


def main():
    output = Path("tests/fixtures/portable")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        app = Application(directory)
        try:
            wid = app.create_workspace("星辰奕歌")["id"]
            value = dict(
                date="2026-09-08",
                title="跨设备夜班",
                start="20:00",
                end="08:00",
                end_date="2026-09-09",
                location="一号站",
            )
            preview = app.preview_change(wid, 0, dict(type="manual", values=value))
            app.commit_change(preview["preview_id"], 0)
            eid = app.events(wid)["items"][0]["id"]
            app.export_file(wid, 1, dict(alarm=15), Path(directory) / "calendar.ics")
            preview = app.preview_change(
                wid,
                1,
                dict(type="edit", event_id=eid, values={**value, "start": "21:00"}),
            )
            app.commit_change(preview["preview_id"], 1)
            app.export_file(wid, 2, dict(alarm=15), Path(directory) / "calendar.ics")
            prefs = app.get_preferences(wid)
            app.save_preferences(
                wid,
                prefs["revision"],
                {**prefs["values"], "theme": "dark", "font_size": 20},
            )
            app.backup_file(wid, str(output / "windows-v2.zip"))
            (output / "expected.json").write_text(
                json.dumps(
                    dict(origin="Windows 11 x64", event_id=eid, sequence=1, alarm=15),
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        finally:
            app.close()


if __name__ == "__main__":
    main()

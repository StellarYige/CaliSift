import json
from pathlib import Path
from tests.test_desktop_store import local


def test_windows_fixture_restores_with_same_uid_sequence_and_preferences_on_each_os(
    local, tmp_path
):
    app, _ = local
    fixture = Path(__file__).parent / "fixtures" / "portable"
    expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    preview = app.prepare_restore((fixture / "windows-v2.zip").read_bytes())
    restored = app.restore_backup(preview["token"])
    wid = restored["id"]
    event = app.events(wid)["items"][0]
    assert event["id"] == expected["event_id"] and event["start"] == "21:00"
    assert restored["preferences"]["values"]["theme"] == "dark"
    assert restored["preferences"]["values"]["font_size"] == 20
    output = tmp_path / "restored.ics"
    app.export_file(wid, restored["version"], {"alarm": expected["alarm"]}, output)
    text = output.read_text(encoding="utf-8")
    assert "UID:" + expected["event_id"] + "@xingcheng.local" in text
    assert "SEQUENCE:1" in text and "TRIGGER:-PT15M" in text

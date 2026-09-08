import json
from types import SimpleNamespace

from xingcheng import desktop, installation_check, localstore


def test_native_check_fails_when_persistence_check_fails_after_export(
    monkeypatch, tmp_path
):
    output = tmp_path / "native-result.json"
    monkeypatch.setenv("CALISIFT_CHECK_OUTPUT", str(output))
    events = [{"id": str(i)} for i in range(4)]

    def export(_wid, _version, _options, path):
        path.write_text("BEGIN:VEVENT\n" * 4, encoding="utf-8")

    app = SimpleNamespace(
        store=SimpleNamespace(workspaces=lambda: [{"id": "sample"}]),
        events=lambda _wid: {"items": events},
        workspace=lambda _wid: {"version": 1},
        export_file=export,
        backup_file=lambda *_args: None,
    )
    window = SimpleNamespace(evaluate_js=lambda _script: True, destroy=lambda: None)
    bridge = SimpleNamespace(_app=app, call=lambda _command: {})
    monkeypatch.setattr(
        desktop, "main", lambda _directory, ready: ready(window, bridge)
    )

    def broken_reopen(_directory):
        raise OSError("persisted database could not be reopened")

    monkeypatch.setattr(localstore, "LocalStore", broken_reopen)
    assert installation_check.run() == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["export"] and result["backup"]
    assert not result["success"]
    assert "could not be reopened" in result["error"]

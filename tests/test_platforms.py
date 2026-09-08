import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from xingcheng.assets import AssetServer
from xingcheng.desktop import Bridge
from xingcheng.platforms import allowed_origin, worker_command
from xingcheng.preferences import Preferences, from_legacy
from tests.test_desktop_store import local


def test_symlinked_bundle_keeps_url_and_served_resource_root_consistent(tmp_path):
    import urllib.request
    import os
    from urllib.parse import urljoin

    resources = tmp_path / "Resources"
    resources.mkdir()
    (resources / "index.html").write_text("bundle UI", encoding="utf-8")
    link = tmp_path / "Frameworks"
    try:
        link.symlink_to(resources, target_is_directory=True)
    except OSError:
        pytest.skip(
            "This Windows account cannot create symbolic links; macOS CI exercises the bundle path"
        )
    entry = str(link / "index.html")
    address, common, server = AssetServer.start_server([entry])
    try:
        url = urljoin(address, os.path.relpath(entry, common))
        assert urllib.request.urlopen(url).read() == b"bundle UI"
    finally:
        server.close()


def test_only_current_static_origin_can_call_native_bridge(local, tmp_path):
    app, wid = local
    (tmp_path / "index.html").write_text("test", encoding="utf-8")
    _, _, server = AssetServer.start_server([str(tmp_path / "index.html")])
    try:
        url = f"http://127.0.0.1:{server.port}/index.html"
        assert allowed_origin(url)
        for untrusted in (
            "file:///tmp/index.html",
            "https://example.org",
            url.replace("127.0.0.1", "localhost"),
            url.replace("127.0.0.1", "127.0.0.1.example.org"),
            url.replace("http:", "https:"),
        ):
            assert not allowed_origin(untrusted)
            bridge = Bridge(app)
            bridge._window = SimpleNamespace(get_current_url=lambda: untrusted)
            assert (
                bridge.call("create_workspace", {"name": "不应创建"})["error"]["code"]
                == "ACCESS_DENIED"
            )
        bridge._window = SimpleNamespace(get_current_url=lambda: url)
        assert bridge.call("workspace", {"workspace_id": wid})["ok"]
        assert len(app.store.workspaces()) == 1
    finally:
        server.close()
    assert not allowed_origin(url)


@pytest.mark.parametrize(
    "platform,extension", [("win32", ".exe"), ("darwin", ""), ("linux", "")]
)
def test_packaged_worker_stays_next_to_executable(
    monkeypatch, tmp_path, platform, extension
):
    executable = tmp_path / ("包含 空格的目录") / ("CaliSift" + extension)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert worker_command() == [
        str(executable.with_name("calisift-worker" + extension))
    ]


def test_category_validation_and_device_preferences_do_not_change_calendar(local):
    app, wid = local
    revision = app.workspace(wid)["version"]
    device = app.device_preferences(
        {"last_workspace": wid, "width": 900, "panel_ratio": 65}
    )
    assert device["width"] == 900 and device["panel_ratio"] == 65
    with pytest.raises(ValueError):
        app.device_preferences({"width": -1})
    assert app.device_preferences() == device
    assert app.workspace(wid)["version"] == revision
    snapshot = app.get_preferences(wid)
    values = snapshot["values"]
    for category in [
        dict(name=" 工作", color="#123456", active=True),
        dict(name="项目", color="red", active=True),
        dict(name="工作", color="#123456", active=True),
    ]:
        with pytest.raises(ValueError):
            app.save_preferences(
                wid, 0, {**values, "categories": values["categories"] + [category]}
            )
    with pytest.raises(ValueError):
        Preferences.model_validate({**values, "categories": values["categories"][1:]})
    assert (
        from_legacy({"colors": {"工作": "invalid"}})["categories"][0]["color"]
        == values["categories"][0]["color"]
    )
    diagnostics = app.diagnostics()
    assert wid not in str(diagnostics) and str(app.store.root) not in str(diagnostics)
    assert "星辰奕歌" not in str(diagnostics)

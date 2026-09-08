import pytest
from xingcheng.desktop import Bridge
from xingcheng.desktop_contracts import validate_request
from tests.test_desktop_store import local


def test_native_preference_payloads_are_checked_before_mutation(local):
    app, wid = local
    bridge = Bridge(app)
    before = app.get_preferences(wid)
    for invalid in [
        dict(workspace_id=wid, expected_revision=True, values=before["values"]),
        dict(
            workspace_id=wid, expected_revision=0, values=before["values"], unknown=True
        ),
    ]:
        assert not bridge.call("save_preferences", invalid)["ok"]
        assert app.get_preferences(wid) == before
    saved = bridge.call(
        "save_preferences",
        dict(
            workspace_id=wid,
            expected_revision=0,
            values={**before["values"], "theme": "dark"},
        ),
    )
    assert saved["ok"] and saved["value"]["revision"] == 1
    assert (
        bridge.call("get_preferences", dict(workspace_id=wid))["value"]
        == saved["value"]
    )


def test_partial_device_payload_does_not_reset_other_device_fields(local):
    app, wid = local
    bridge = Bridge(app)
    assert bridge.call("device_preferences", {"values": {"width": 900, "height": 700}})[
        "ok"
    ]
    result = bridge.call("device_preferences", {"values": {"panel_ratio": 60}})
    assert (
        result["ok"]
        and result["value"]["width"] == 900
        and result["value"]["height"] == 700
    )
    assert not bridge.call("device_preferences", {"values": {"width": True}})["ok"]
    with pytest.raises(ValueError):
        validate_request("get_preferences", [])
    with pytest.raises(ValueError):
        validate_request(
            "course_draft",
            {"workspace_id": wid, "semester": {}, "course": {}, "courses": [{}]},
        )

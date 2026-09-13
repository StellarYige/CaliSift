import base64
from copy import deepcopy
import json
import pytest
from xingcheng.browser import dispatch_json
from xingcheng.localstore import LocalError
from xingcheng.application import Application
from tests.test_browser_application import local, draft, change, input_files, finish


def test_isolated_command_does_not_mutate_input_on_failure(local):
    app, wid = local
    jid = draft(app, wid)
    state = deepcopy(app.store.state)
    with pytest.raises(ValueError):
        dispatch_json(
            json.dumps(
                dict(
                    state=state,
                    method="edit_draft",
                    payload=dict(
                        job_id=jid,
                        edits=[
                            dict(index=0, values={"title": "before failure"}),
                            dict(index=99, values={}),
                        ],
                    ),
                )
            )
        )
    assert state == app.store.state


def test_stale_job_and_previews_survive_refresh_without_silent_overwrite(local):
    app, wid = local
    jid = draft(app, wid)
    revision = app.get_job(jid)["revision"]
    app.edit_draft(jid, [dict(index=0, values={"location": "changed"})], revision)
    with pytest.raises(LocalError):
        app.edit_draft(jid, [dict(index=0, values={"location": "stale"})], revision)
    with pytest.raises(LocalError):
        app.preview_change(wid, 0, {"type": "append"}, jid, revision)
    p = app.preview_change(wid, 0, {"type": "append"}, jid)
    restarted = Application(app.store.state)
    restarted.commit_change(p["preview_id"], 0)
    assert restarted.events(wid)["items"][0]["location"] == "changed"


def test_cancelled_generation_rejects_late_results_and_discard_cleans(local):
    app, wid = local
    job = app.jobs.stage(wid, input_files(["samples/九月排班.csv"]))
    running = app.jobs.start(job["id"], 2026)
    app.jobs.cancel(job["id"])
    with pytest.raises(LocalError):
        app.jobs.finish(
            job["id"], job["files"][0]["id"], running["generation"], error="late"
        )
    restarted = Application(app.store.state)
    restarted.jobs.start(job["id"], 2026)
    assert finish(restarted, job["id"])["status"] == "review"
    restarted.jobs.clean(job["id"])
    stored = restarted.store.document("job", job["id"])
    assert all("data" not in f and "report" not in f for f in stored["files"])


def test_unknown_schema_is_refused_without_altering_saved_data(local):
    app, _ = local
    state = deepcopy(app.store.state)
    state["schema"] = 999
    before = deepcopy(state)
    with pytest.raises(LocalError):
        Application(state)
    assert state == before


def test_stale_template_and_profile_edits_cannot_overwrite_other_tabs(local):
    app, wid = local
    t = app.save_template("template", {})
    app.save_template(
        "changed", {}, template_id=t["id"], expected_revision=t["revision"]
    )
    with pytest.raises(LocalError):
        app.save_template(
            "stale", {}, template_id=t["id"], expected_revision=t["revision"]
        )
    with pytest.raises(LocalError):
        app.delete_template(t["id"], expected_revision=t["revision"])
    p = app.save_profile(wid, "profile", {})
    app.save_profile(
        wid, "changed", {}, profile_id=p["id"], expected_revision=p["revision"]
    )
    with pytest.raises(LocalError):
        app.save_profile(
            wid, "stale", {}, profile_id=p["id"], expected_revision=p["revision"]
        )

"""Native Health results and unchanged product diagnostics without provider I/O."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html as html_module
import json
import os
from pathlib import Path
import socket

import pytest

from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import project_health


STAMP = "2026-06-02T12:00:00+00:00"


def forbidden(*args, **kwargs):
    pytest.fail("Health presentation attempted native, provider, file, socket or clock access")


@pytest.fixture
def recorded(store, monkeypatch):
    from sonaloop import run_activity, avatar
    from sonaloop.services import _engines, _research, _recovery, _hooks
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(run_activity, "datetime", FixedClock)
    for module in (_engines, _research, _recovery):
        monkeypatch.setattr(module, "utc_now_iso", lambda: STAMP)
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    projects = {}
    for scenario in ("not-started", "running", "stalled", "expired", "waiting", "unverified", "finished", "no-plan", "archived"):
        project = services.start_project("Health " + scenario, "Inspect the existing evidence.",
            methodology="reaction_test" if scenario == "waiting" else None,
            operation_id="health-ui:" + scenario, store=store)
        projects[scenario] = project
        if scenario in ("running", "stalled", "expired", "waiting"):
            run = services.start_run(project["id"], operation_id="health-run:" + scenario, store=store)
            if scenario in ("stalled", "expired"):
                run["updated_at"] = "2026-06-02T04:00:00+00:00" if scenario == "stalled" else "2026-06-01T10:00:00+00:00"
                store.upsert_run(run)
            if scenario == "waiting":
                services.run_step(run["run_id"], store=store)
        if scenario in ("unverified", "finished"):
            services.record_frame(project["id"], "frame__root", ["Who owns the next handover?"],
                                  memory_refs=["memory:authored-fixture"], store=store)
        if scenario == "finished":
            # Seed an explicitly synthetic persisted journal boundary. This is
            # a native-read fixture, not a claim that finish_run's gates ran.
            store.upsert_run({"run_id": "health-fixture-finished", "project_id": project["id"],
                "status": "finished", "cursor": 0, "steps": [], "dispatches": [], "critic_rounds": [],
                "created_at": STAMP, "updated_at": STAMP})
        if scenario == "no-plan":
            store.conn.execute("DELETE FROM research_plans WHERE project_id=?", (project["id"],))
            store.commit()
        if scenario == "archived":
            services.archive_project(project["id"], "health-archive", "Keep prior evidence.", store=store)
    return projects


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_plan
    server = FastMCP("original-health")
    _tools_plan.register_plan(server)
    return server


def test_actual_native_health_fixtures(recorded, tmp_path):
    server = original_server()
    examples = []
    for scenario, project in recorded.items():
        arguments = {"project_id": project["id"]}
        envelope = server._tool_manager._tools["project_health"].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        markup, state = project_health.health(value)
        expected = "stalled" if scenario in ("not-started", "no-plan") else scenario
        assert value["state"] == expected and state == "ready"
        assert f"<dd>{value['state']}</dd>" in markup
        assert len(json.dumps({"name": "project_health", "value": value}, ensure_ascii=False).encode()) <= 8192
        examples.append({"scenario": "health-" + scenario, "tool": "project_health", "input": arguments,
                         "value": value, "state": state})
    path = Path(os.environ.get("RESEARCH_HEALTH_FIXTURE_PATH", tmp_path / "health-fixtures.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Actual native synthetic Health fixtures:", path)


def test_pure_health_never_reprojects_or_reads_media_files_or_clock(recorded, store, monkeypatch):
    from sonaloop import run_activity, embeddings
    from sonaloop.web import ui
    values = [services.project_health(project["id"], store=store) for project in recorded.values()]
    for value in values:
        project_health.health(value)
    before = deepcopy(values)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(services, "project_health", forbidden)
        patch.setattr(services, "project_run_state", forbidden)
        patch.setattr(services, "get_research_project", forbidden)
        patch.setattr(run_activity, "is_inactive_for", forbidden)
        patch.setattr(run_activity, "activity_deadline", forbidden)
        patch.setattr(ui, "avatar_group", forbidden)
        patch.setattr(embeddings, "embed_texts", forbidden)
        for name in ("open", "read_text", "read_bytes", "exists", "is_file"):
            patch.setattr(Path, name, forbidden)
        for value in values:
            markup, state = project_health.health(value)
            assert state == "ready" and "sl-research-health" in markup
            assert all(tag not in markup for tag in ("<a ", "<button", "<img", "<svg", "<form", "<pre"))
    assert values == before


def test_expiry_unknown_host_and_completed_tasks_do_not_invent_completion(recorded, store):
    expired = services.project_health(recorded["expired"]["id"], store=store)
    markup, _ = project_health.health(expired)
    assert expired["activity_lifecycle"]["resumable"] is True and expired["engine_finished"] is False
    assert "No heartbeat contract exists" in markup and "quiet activity is not proof of disconnect" in markup
    assert "Its journal is preserved" in markup and "2026-06-02T10:00:00+00:00" in markup
    unverified = services.project_health(recorded["unverified"]["id"], store=store)
    assert unverified["tasks"]["done"] == unverified["tasks"]["total"] == 1
    assert unverified["engine_finished"] is False and unverified["state"] == "unverified"
    assert "<dt>Engine finished</dt><dd>false</dd>" in project_health.health(unverified)[0]
    finished = services.project_health(recorded["finished"]["id"], store=store)
    assert finished["engine_finished"] is True
    assert "<dt>Engine finished</dt><dd>true</dd>" in project_health.health(finished)[0]


def test_waiting_has_exact_native_call_and_required_paths(recorded, store):
    value = services.project_health(recorded["waiting"]["id"], store=store)
    markup, _ = project_health.health(value)
    action = value["safe_next_action"]
    assert action["kind"] == "complete_preflight" and action["required_input_paths"]
    for path in action["required_input_paths"]:
        assert path in markup
    assert html_module.escape(project_health.action_call(action, keep_empty=True)) in markup
    # Native legacy active runs may have an empty operation id. Keep that exact
    # value in passive recommendations; preserve the old product call display.
    active = services.project_health(recorded["running"]["id"], store=store)
    active["safe_next_action"]["arguments"]["operation_id"] = ""
    passive = html_module.unescape(project_health.health(active)[0])
    assert "operation_id=''" in passive and "Subsequent returned step" in passive
    assert "operation_id=" not in project_health.action_call(active["safe_next_action"])


def test_all_supplied_health_counts_and_report_sources_remain_literal(recorded, store):
    value = services.project_health(recorded["running"]["id"], store=store)
    # Authored projection fixtures exercise fields whose existence is already
    # checked against native handoff/retry schemas in their service tests.
    value["evidence"] = {"posture_counts": {"unknown-token": 0, "inferred": 3}, "source_counts": {"note": 2}, "orphaned": 0}
    value["report_handoff"].update(exists=True, latest_report_id="report-fixture", incomplete_report_ids=["report-fixture"],
        required_source_ids=["synthesis:source"], reports=[{"report_id": "report-fixture", "status": "in_progress",
            "complete": False, "section_count": 2, "authored_section_count": 1, "authored_section_ids": ["sec1"],
            "incomplete_section_ids": ["sec2"], "body_empty": False, "lead_missing": True, "content_complete": False,
            "required_source_ids": ["synthesis:source"], "source_coverage_missing": ["synthesis:source"]}])
    value["recovery_signals"].update(retry_result="available", retry_receipt={"run_id": "run-fixture", "key": "step-fixture", "cursor": 2, "step_idx": 1})
    markup, _ = project_health.health(value)
    for text in ("unknown-token</dt><dd>0", "inferred</dt><dd>3", "note</dt><dd>2", "sec1", "sec2",
                 "synthesis:source", "lead_missing</dt><dd>true", "step-fixture", "cursor</dt><dd>2"):
        assert text in markup


@pytest.mark.parametrize("mutate", [
    lambda v: v.update(schema="sonaloop.project_health.v0"),
    lambda v: v.update(engine_finished="true"),
    lambda v: v["run_inventory"].update(active=True),
    lambda v: v["tasks"].update(next_ready=[{}]),
    lambda v: v["activity_lifecycle"].update(resumable=1),
    lambda v: v["integrity_findings"].append({"code": "broken", "message": {}}),
    lambda v: v["safe_next_action"].update(arguments={"invalid": float("nan")}),
    lambda v: v["evidence"].update(source_counts={"note": -1}),
    lambda v: v["report_handoff"].update(complete=1),
    lambda v: v["product_understanding"].update(capability_counts={"unknown": False}),
    lambda v: v["recovery_signals"].update(retry_receipt={"key": "missing-counts"}),
])
def test_malformed_health_falls_back_before_presentation(recorded, store, mutate):
    value = services.project_health(recorded["running"]["id"], store=store)
    mutate(value)
    with pytest.raises(ValueError):
        project_health.health(value)


def test_health_untrusted_prose_targets_arguments_and_count_labels_are_escaped(recorded, store):
    value = services.project_health(recorded["running"]["id"], store=store)
    hostile = '<img src=x onerror="bad()"><a href="javascript:bad()">Full qualifier</a>'
    value["integrity_findings"] = [{"code": "untrusted", "message": hostile, "severity": "warning", "target": hostile}]
    value["safe_next_action"]["arguments"]["opaque"] = hostile
    value["safe_next_action"]["reason"] = hostile
    value["trace"]["limitation"] = hostile * 90
    value["evidence"]["source_counts"] = {hostile: 0}
    markup, _ = project_health.health(value)
    assert markup.count("Full qualifier") >= 93 and "&lt;img" in markup
    assert "<img" not in markup and "<a " not in markup and "<script" not in markup


def test_real_product_diagnostics_use_shared_body_and_keep_controls(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.web import _runs_widget
    seen = []
    original = project_health.diagnostics_content
    def capture(value, **kwargs):
        markup = original(value, **kwargs)
        seen.append((deepcopy(value), kwargs, markup))
        return markup
    monkeypatch.setattr(project_health, "diagnostics_content", capture)
    response = TestClient(web.create_app()).get("/jobs/" + recorded["not-started"]["id"])
    assert response.status_code == 200 and seen
    assert any(markup in response.text and "prepared" in args for _, args, markup in seen)
    assert 'data-copy="start_run(' in response.text and 'data-runchip-toggle' in response.text
    assert 'aria-controls="runchip-fly"' in response.text and 'href="/runs"' in response.text
    assert _runs_widget.run_attention_text({"state": "stalled", "driver_state": "not_started"}) == project_health.attention_text({"state": "stalled", "driver_state": "not_started"})


def test_actual_fastmcp_health_preserves_schema_result_and_projects_once(recorded, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_plan
    original = original_server()
    server = build_server()
    old = next(tool for tool in asyncio.run(original.list_tools()) if tool.name == "project_health")
    new = next(tool for tool in asyncio.run(server.list_tools()) if tool.name == "project_health")
    assert new.inputSchema == old.inputSchema and new.outputSchema == old.outputSchema
    assert new.meta["ui"]["resourceUri"] == "ui://sonaloop/runs/v1"
    calls, envelopes = [], []
    native = services.project_health
    env = _tools_plan._env
    def project(*args, **kwargs):
        value = native(*args, **kwargs)
        calls.append(deepcopy(value))
        return value
    def capture(name, *args, **kwargs):
        value = env(name, *args, **kwargs)
        envelopes.append(deepcopy(value))
        return value
    monkeypatch.setattr(services, "project_health", project)
    monkeypatch.setattr(_tools_plan, "_env", capture)
    result = asyncio.run(server.call_tool("project_health", {"project_id": recorded["waiting"]["id"]}))
    assert not result.isError and len(calls) == len(envelopes) == 1
    text, structured = original._tool_manager._tools["project_health"].fn_metadata.convert_result(envelopes[0])
    assert result.content == text and result.structuredContent == structured
    assert result.meta["sonaloop/presentation"]["state"] == "ready"
    assert result.meta["sonaloop/presentation"]["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()

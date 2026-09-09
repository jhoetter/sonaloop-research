"""Project results use native temporary records and the real product header."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import discovery, projects, projects_rows


NAMES = {"start_project": projects.started, "query_projects": projects.queried,
         "supersede_project": projects.superseded, "archive_project": projects.archived,
         "delete_research_project": projects.deleted, "set_project_icon": projects.icon,
         "generate_project_icon": projects.icon}
STAMP = "2026-06-02T09:00:00+00:00"
SVG = '<svg viewBox="0 0 24 24"><path d="M4 12h16"/></svg>'


def forbidden(*args, **kwargs):
    pytest.fail("Project presentation attempted a native, media, file or clock operation")


@pytest.fixture
def recorded(store, monkeypatch):
    from conftest import make_profile
    from sonaloop.services import _engines, _research, _project_icons, _recovery
    for module in (_engines, _research, _project_icons, _recovery):
        monkeypatch.setattr(module, "utc_now_iso", lambda: STAMP)
    persona = services.record_persona("Authored project fixture", make_profile("Project reader"),
                                     generate_avatar=False, store=store)
    values = {name: services.start_project(name, "Clarify who owns the handover", icon="compass",
              operation_id="project-ui-" + name, store=store)
              for name in ("Earlier", "Successor", "Archive", "Delete", "Icon")}
    # A real deletion count beyond the container row; no provider or governed run.
    services.create_note(values["Delete"]["id"], "An abandoned observation", "Preserve literal counts", store=store)
    return values, persona["id"]


def native_inputs(recorded):
    values, pid = recorded
    return {"start_project": {"title": "A fresh question", "goal": "Who owns the unresolved handover?",
                "description": "Inspect the source before concluding.", "persona_ids": [pid],
                "icon": "target", "operation_id": "project-ui-new"},
        "query_projects": {"limit": 2, "offset": 1},
        "supersede_project": {"project_id": values["Successor"]["id"], "supersedes_project_id": values["Earlier"]["id"],
                              "operation_id": "project-ui-lineage", "reason": "The question was narrowed."},
        "archive_project": {"project_id": values["Archive"]["id"], "operation_id": "project-ui-archive",
                            "reason": "Retain earlier evidence."},
        "delete_research_project": {"project_id": values["Delete"]["slug"]},
        "set_project_icon": {"project_id": values["Icon"]["id"], "icon": "target"},
        "generate_project_icon": {"project_id": values["Icon"]["id"], "prompt": "Handover relationships"}}


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_plan, _tools_research, _tools_substrate
    server = FastMCP("original-projects")
    _tools_plan.register_plan(server)
    _tools_research.register_research(server)
    _tools_substrate.register_substrate(server)
    return server


def native_values(recorded):
    server = original_server()
    return {name: server._tool_manager._tools[name].fn(**arguments)["data"]
            for name, arguments in native_inputs(recorded).items()}


def test_original_native_fixtures_cover_seven_tools_and_replays(recorded, tmp_path):
    server = original_server()
    inputs = native_inputs(recorded)
    specs = [(name, name, args) for name, args in inputs.items()]
    specs += [(name + "-replay", name, inputs[name]) for name in ("start_project", "supersede_project", "archive_project")]
    specs += [("query-empty", "query_projects", {"q": "no-such-project-fixture", "limit": 1, "offset": 0}),
              ("icon-custom", "set_project_icon", {"project_id": recorded[0]["Icon"]["id"], "svg": SVG})]
    examples = []
    for scenario, name, arguments in specs:
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        html, state = NAMES[name](value)
        assert state == ("empty" if scenario == "query-empty" else "ready")
        assert len(json.dumps({"name": name, "value": value}, ensure_ascii=False).encode()) <= 8192
        examples.append({"scenario": scenario, "tool": name, "input": arguments, "value": value, "state": state})
    assert examples[0]["value"]["warnings"]
    deleted = next(item["value"] for item in examples if item["tool"] == "delete_research_project")
    assert deleted["project_id"] == recorded[0]["Delete"]["id"] and deleted["deleted"]["research_projects"] == 1
    path = Path(os.environ.get("RESEARCH_PROJECT_FIXTURE_PATH", tmp_path / "project-fixtures.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Original native synthetic Project7 fixtures:", path)


def test_all_seven_native_results_are_pure_and_unchanged(recorded, monkeypatch):
    from sonaloop.services import _project_icons, _recovery
    from sonaloop.web import ui
    values = native_values(recorded)
    before = deepcopy(values)
    for name, value in values.items():
        NAMES[name](value)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(ui, "avatar_group", forbidden)
        for name in NAMES:
            patch.setattr(services, name, forbidden)
        for name in ("get_research_project", "project_icon_svg", "available_project_icons"):
            patch.setattr(services, name, forbidden)
        patch.setattr(_project_icons, "utc_now_iso", forbidden)
        patch.setattr(_recovery, "utc_now_iso", forbidden)
        for name in ("open", "read_text", "read_bytes", "exists", "is_file"):
            patch.setattr(Path, name, forbidden)
        for name, value in values.items():
            html, state = NAMES[name](value)
            assert state == "ready"
            assert all(tag not in html for tag in ("<a ", "<svg", "<img", "<script", "<form", "<button", "<pre"))
    assert values == before


def test_start_replay_shows_current_native_record_and_complete_warning(recorded, store):
    arguments = native_inputs(recorded)["start_project"]
    original = services.start_project(**arguments, store=store)
    updated = {**store.get_research_project(original["id"]), "title": "Later retained title", "status": "paused",
               "description": "Full qualification. " * 120 + "Final limit."}
    store.upsert_research_project(updated)
    replay = services.start_project(**arguments, store=store)
    html, _ = projects.started(replay)
    assert "Later retained title" in html and "Final limit." in html and ">paused<" in html
    assert "Idempotent replay" in html and ">true<" in html and "does not establish a started or finished" in html
    assert all(warning in html for warning in replay["warnings"])
    assert store.get_research_project(original["id"])["title"] == "Later retained title"
    assert discovery.project_heading(original) == projects.project_heading(original)


def test_query_retains_zero_counts_archived_rows_and_offset(recorded, store):
    services.archive_project(recorded[0]["Archive"]["id"], "archive-query", "Keep it", store=store)
    value = services.query_projects(status="archived", limit=1, offset=0, store=store)
    html, state = projects.queried(value)
    assert state == "ready" and value["items"][0]["id"] in html and ">archived<" in html
    assert html.count(">0</dd>") == 3 and "Offset 0" in html
    empty = services.query_projects(limit=2, offset=99, store=store)
    html, state = projects.queried(empty)
    assert state == "empty" and "Offset 99" in html and str(empty["total"]) in html


def test_lifecycle_keeps_direction_and_does_not_turn_archive_into_deletion(recorded):
    values = native_values(recorded)
    lineage = values["supersede_project"]
    html, _ = projects.superseded(lineage)
    assert "Explicitly supersedes" in html and lineage["supersedes_project_id"] in html
    assert "The question was narrowed." in html and "Evidence preserved" in html
    assert "Superseded by" not in html and "Project container deleted" not in html
    archived = values["archive_project"]
    assert "reason" not in archived and "archived_at" not in archived
    html, _ = projects.archived(archived)
    assert "Archived; evidence is preserved." in html and "Retain earlier evidence." not in html
    deleted = values["delete_research_project"]
    html, _ = projects.deleted(deleted)
    assert "Project container deleted" in html
    for key, count in deleted["deleted"].items():
        assert f"<dt>{key}</dt><dd>{count}</dd>" in html
    html, _ = projects.deleted({"project_id": "missing", "deleted": {"research_projects": 0, "events": 0}})
    assert "No project-container deletion reported" in html and "Project container deleted" not in html


def test_icon_spec_preserves_source_without_loading_anything(recorded):
    values = native_values(recorded)
    value = values["generate_project_icon"]
    html, _ = projects.icon(value)
    assert "Handover relationships" in html and STAMP in html and value["icon"]["svg_path"] in html
    assert "&lt;svg" in html and "<svg" not in html and "Specification only" in html
    for key in ("name", "svg", "url", "svg_path", "prompt"):
        hostile = {"project_id": "fixture", "icon": {"kind": "custom", "svg": SVG,
                   key: '<img src=x onerror="bad()">'}}
        html, _ = projects.icon(hostile)
        assert "&lt;img" in html and "<img" not in html and "<a " not in html


def test_native_text_and_receipt_identities_cannot_create_markup(recorded):
    values = native_values(recorded)
    hostile = '<a href="javascript:bad()"><img src=x onerror="bad()"></a>'
    values["start_project"].update(title=hostile, goal=hostile, description=hostile, warnings=[hostile])
    values["query_projects"]["items"][0].update(title=hostile, methodology=hostile)
    values["supersede_project"].update(project_id=hostile, reason=hostile)
    values["archive_project"]["operation_id"] = hostile
    values["delete_research_project"]["deleted"][hostile] = 0
    for name in list(NAMES)[:5]:
        html, _ = NAMES[name](values[name])
        assert "&lt;a href=" in html and "<a " not in html and "<img" not in html


@pytest.mark.parametrize("name, change", [
    ("start_project", lambda v: v.update(warnings=[{}])),
    ("start_project", lambda v: v.update(idempotent_replay="true")),
    ("start_project", lambda v: v.update(persona_ids=[{}])),
    ("query_projects", lambda v: v.update(total=True)),
    ("query_projects", lambda v: v.update(next_offset="3")),
    ("query_projects", lambda v: v["items"][0].update(assets=-1)),
    ("supersede_project", lambda v: v.update(evidence_deleted=True)),
    ("supersede_project", lambda v: v.update(supersedes_project_id=v["project_id"])),
    ("supersede_project", lambda v: v.update(schema="unknown")),
    ("archive_project", lambda v: v.update(status="active")),
    ("archive_project", lambda v: v.update(idempotent=1)),
    ("delete_research_project", lambda v: v.update(deleted=True)),
    ("delete_research_project", lambda v: v["deleted"].update(research_projects=True)),
    ("set_project_icon", lambda v: v.update(icon={"kind": "remote", "url": "https://example.invalid/x"})),
    ("generate_project_icon", lambda v: v["icon"].update(svg={"markup": "invalid"})),
])
def test_malformed_native_values_fail_before_presentation(recorded, name, change):
    value = native_values(recorded)[name]
    change(value)
    with pytest.raises(ValueError):
        NAMES[name](value)


def test_actual_product_header_lineage_and_icon_share_bodies(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.web.pages import projects as page
    target = recorded[0]["Successor"]
    receipt = services.supersede_project(target["id"], recorded[0]["Earlier"]["id"], "lineage-product", "New question", store=store)
    services.archive_project(target["id"], "archive-product", "Retain", store=store)
    spec = services.set_project_icon(target["id"], svg=SVG, store=store)["icon"]
    seen = []
    original = projects.project_body
    def capture(value, **kwargs):
        body = original(value, **kwargs)
        seen.append((deepcopy(value), kwargs, body))
        return body
    monkeypatch.setattr(projects, "project_body", capture)
    response = TestClient(web.create_app()).get("/jobs/" + target["id"])
    assert response.status_code == 200 and len(seen) == 1 and seen[0][2] in response.text
    assert "prepared" in seen[0][1] and "Archived; evidence is preserved." in seen[0][2]
    assert f'href="/jobs/{receipt["supersedes_project_id"]}"' in seen[0][2] and ">Earlier</a>" in seen[0][2]
    assert projects.icon_content(spec) in response.text and 'name="confirm"' in response.text
    assert "project-custom-icon" in response.text and "&lt;svg" in response.text
    # Unresolvable lineage keeps literal identity and cannot obtain another title.
    unresolved = page._project_lineage_html({"supersedes_project_id": "inaccessible-project"}, store)
    assert "<code>inaccessible-project</code>" in unresolved and "<a " not in unresolved


def test_unknown_legacy_icon_spec_does_not_break_actual_product_page(recorded, store):
    from starlette.testclient import TestClient
    value = store.get_research_project(recorded[0]["Icon"]["id"])
    store.upsert_research_project({**value, "icon": {"kind": "legacy", "name": "compass"}})
    response = TestClient(web.create_app()).get("/jobs/" + value["id"])
    assert response.status_code == 200 and "Stored icon specification cannot be displayed." in response.text


def test_seven_actual_fastmcp_tools_preserve_schema_output_and_single_execution(recorded, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_plan, _tools_research, _tools_substrate
    original = original_server()
    server = build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in NAMES:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/projects/v1"
    captured = []
    env = _tools_plan._env
    def capture(name, *args, **kwargs):
        value = env(name, *args, **kwargs)
        captured.append((name, deepcopy(value)))
        return value
    for module in (_tools_plan, _tools_research, _tools_substrate):
        monkeypatch.setattr(module, "_env", capture)
    calls = {name: 0 for name in NAMES}
    def track(name):
        fn = getattr(services, name)
        def invoke(*args, **kwargs):
            calls[name] += 1
            return fn(*args, **kwargs)
        monkeypatch.setattr(services, name, invoke)
    for name in NAMES:
        track(name)
    for name, arguments in native_inputs(recorded).items():
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and captured[-1][0] == name
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(captured[-1][1])
        assert result.content == text and result.structuredContent == structured
        presentation = result.meta["sonaloop/presentation"]
        assert presentation["tool"] == name and presentation["state"] == "ready"
        assert presentation["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
    assert len(captured) == 7, "Presentation must not repeat any native operation"
    assert calls == {name: 1 for name in NAMES}


def test_presentation_failure_does_not_retry_native_icon_writer(recorded, monkeypatch):
    from sonaloop.mcp_server import build_server, _research_ui
    server = build_server()
    calls = []
    original = services.generate_project_icon
    def generate(*args, **kwargs):
        value = original(*args, **kwargs)
        calls.append(deepcopy(value))
        return value
    def unsupported(*args, **kwargs):
        raise ValueError("Synthetic presentation failure")
    monkeypatch.setattr(services, "generate_project_icon", generate)
    monkeypatch.setattr(_research_ui, "render_tool", unsupported)
    result = asyncio.run(server.call_tool("generate_project_icon", native_inputs(recorded)["generate_project_icon"]))
    assert not result.isError and len(calls) == 1 and result.structuredContent["data"] == calls[0]
    assert not result.meta or "sonaloop/presentation" not in result.meta

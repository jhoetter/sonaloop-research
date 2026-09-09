"""Native-output compatibility and shared passive rendering, without providers."""
import asyncio
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from sonaloop import services
from sonaloop.mcp_server import build_server
from sonaloop.mcp_server._research_ui import _decorate, present
from sonaloop.ui_components.library import note_content, section_content
from sonaloop.ui_components.registry import SURFACES


NOTE = {"id": "note_one", "title": "A <script>title</script>", "text": "**Actual** native note", "kind": "note"}
SECTION = {"id": "section_one", "title": "Research stage", "member_ids": ["note:note_one"], "note": "What we learned"}
HYPOTHESIS = {"id": "hyp_one", "text": "Handover gets faster", "prediction": {"metric": "minutes", "expected_value": 4}, "status": "open"}
DECISION = {"id": "dec_one", "title": "Name the handover owner", "decision": "Make responsibility explicit.", "status": "proposed", "based_on": [{"kind": "hypothesis", "id": "hyp_one"}]}
SURVEY = {"id": "survey_one", "title": "Handover feedback", "status": "draft", "questions": [{"id": "q1", "text": "What helps?", "kind": "text"}]}
COUNCIL = {"id": "council_one", "prompt": "What helps the handover?", "persona_ids": ["persona_one"],
           "statements": [{"persona_id": "persona_one", "text": "Knowing who owns the open issue."}], "summary": "Make ownership explicit."}


SYNTHESIS = {"id": "syn_fixture", "title": "Handover findings", "scope": "convergence", "status": "in_progress",
             "start_input": "Where is handover unclear?", "arc_narrative": "", "gesamtbild": "Show the current owner.",
             "positionierung": "", "created_at": "2026-09-09T01:00:00Z", "council_ids": [],
             "statements": [], "findings": [], "sections": []}
SESSION = {"id": "session_fixture", "persona_id": "persona_fixture", "subject": {"kind": "flow", "id": "flow_fixture", "label": "Handover"},
           "fidelity": "artifact", "steps": [{"index": 0, "action": {"type": "look", "target": "Owner", "detail": ""},
               "monologue": "Who owns this?", "state": {"screen": "Owner panel"}, "friction": {"level": "none", "note": ""},
               "verdict": {"would_continue": True, "reason": "The owner is visible."}}],
           "outcome": {"completed": True, "dropoff_step": None, "summary": "Found the owner", "predicted_behaviors": []}}


def test_cold_product_bootstrap_registers_shared_css_before_shell_digest():
    # A fresh process is essential: another test's first rendered card must not
    # accidentally prime the registry and hide a release-token change on navigation.
    result = subprocess.run([sys.executable, "-c", """
from sonaloop import web
from sonaloop.web._html import collect_css
from sonaloop.web._shell_version import shell_digest
from sonaloop.ui_components.library import note_content, section_content
from sonaloop.ui_components.discovery import project_heading, search_hit_content
assert '.sl-research-card' in collect_css()
before = shell_digest()
note_content({'text': 'Cold note'})
section_content({'title': 'Cold section', 'member_ids': []})
project_heading({'title': 'Cold project'})
search_hit_content('Cold hit')
assert shell_digest() == before
"""], cwd=Path(__file__).parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def call(server, name, args):
    return asyncio.run(server.call_tool(name, args))


def test_native_schema_text_and_structured_output_are_unchanged():
    from sonaloop.mcp_server._tools_sections import register_sections
    original = FastMCP("before")
    register_sections(original)
    decorated = build_server()
    after = {tool.name: tool for tool in asyncio.run(decorated.list_tools())}
    for tool in asyncio.run(original.list_tools()):
        assert after[tool.name].inputSchema == tool.inputSchema
        assert after[tool.name].outputSchema == tool.outputSchema
    tool = original._tool_manager._tools["list_notes"]
    value = {"tool": "list_notes", "data": {"items": [NOTE], "total": 1, "has_more": False, "next_cursor": None}, "_meta": {"latency_ms": 1.25}}
    before = copy.deepcopy(value)
    content, structured = tool.fn_metadata.convert_result(value)
    result = present("list_notes", value, tool.fn_metadata)
    assert result.content == content
    assert result.structuredContent == structured
    assert value == before
    presentation = result.meta["sonaloop/presentation"]
    assert presentation["text_sha256"] == hashlib.sha256("\n".join(item.text for item in content).encode()).hexdigest()
    assert "sonaloop/presentation" not in json.dumps(structured)
    assert "<script>" not in presentation["html"]
    assert str(note_content(NOTE)) in presentation["html"]


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_every_registered_surface_has_a_real_projection_and_resource(name):
    server = build_server()
    tool = server._tool_manager._tools[name]
    formats = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/council-formats.json").read_text())["cases"]
    format_case = next((case for case in formats if case["tool"] == name), None)
    if format_case:
        data = format_case["value"]
    elif name in {case["tool"] for case in json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/projects.json").read_text())}:
        cases = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/projects.json").read_text())
        data = next(case["value"] for case in cases if case["tool"] == name)
    elif SURFACES[name].family in {"preparation", "profiles", "cohorts", "records", "chats", "catalog", "researchplan"}:
        cases = json.loads((Path(__file__).parents[1] / f"tools/persona-ui/fixtures/{SURFACES[name].family}.json").read_text())
        data = next(case["value"] for case in cases if case["tool"] == name)
    elif name in {"start_run", "run_journal", "resume_project_run", "finish_run"}:
        cases = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/run-journal.json").read_text())
        data = next(case["value"] for case in cases if case["tool"] == name)
    elif name == "project_health":
        data = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/project-health.json").read_text())[0]["value"]
    elif SURFACES[name].family == "memory":
        cases = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/memory.json").read_text())["cases"]
        data = next(case["value"] for case in cases if case["tool"] == name)
    elif SURFACES[name].family in {"plans", "calendar"}:
        cases = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/calendar-plans.json").read_text())["cases"]
        data = next(case["value"] for case in cases if case["tool"] == name)
    elif SURFACES[name].family == "prototypes":
        from test_research_prototype_ui import record
        value = record()
        data = ([value] if name == "list_prototypes" else {"prototype": value} if name == "register_remote_prototype"
                else {"prototype_id": "p", "url": "http://127.0.0.1:17471/", "pid": 123} if name == "run_prototype"
                else {"stopped": False} if name == "stop_prototype" else {"deleted": 1} if name == "delete_prototype" else value)
    elif SURFACES[name].family == "references":
        reference = {"id": "r", "kind": "url", "title": "Reference", "url": "https://example.invalid/", "snapshot": {"ok": False, "mode": "skipped", "headings": [], "text": ""}}
        data = [reference] if name == "list_artifacts" else {"deleted": 1} if name == "delete_artifact" else reference
    elif SURFACES[name].family == "assets":
        asset = {"id": "asset_one", "filename": "notes.txt", "kind": "document", "media_type": "text/plain", "bytes": 6, "text_excerpt": "Notes."}
        data = [asset] if name == "list_assets" else {"deleted": 1} if name == "remove_asset" else asset
    elif name in {"record_synthesis", "get_synthesis", "record_synthesis_outline", "record_synthesis_section"}:
        data = SYNTHESIS
    elif name == "list_syntheses":
        data = [SYNTHESIS]
    elif name == "get_usability_session":
        data = SESSION
    elif name == "record_usability_session":
        data = {"usability_session": SESSION}
    elif name == "list_usability_sessions":
        data = {"sessions": [SESSION]}
    elif name == "record_prototype_session":
        data = {"prototype_session": {"id": "ps_fixture", "persona_id": "persona_fixture", "prototype_id": "prototype_fixture",
                                     "reaction": {"verdict": "Keep the owner visible", "steps": SESSION["steps"]}}}
    elif name in {"get_session_funnel", "flow_funnel"}:
        data = {"subject": {"kind": "flow", "key": "flow_fixture"}, "sessions": 1, "completed": 1,
                "rows": [{"step": 0, "entered": 1, "continued": 1, "dropped": 0, "drop_reasons": []}]}
    elif name in {"record_council", "get_council"}:
        data = COUNCIL
    elif name == "list_councils":
        data = {"items": [{"id": "council_one", "prompt": COUNCIL["prompt"], "created_at": "2026-09-08", "personas": 1, "turns": 1, "votes": {}}], "total": 1, "has_more": False}
    elif name == "record_survey":
        data = {"survey": SURVEY}
    elif name == "get_survey":
        data = {**SURVEY, "response_count": 0}
    elif name == "list_surveys":
        data = {"surveys": [SURVEY]}
    elif name == "survey_results":
        data = {"survey_id": "survey_one", "title": SURVEY["title"], "status": "draft", "responses": 0,
                "questions": [{"question_id": "q1", "text": "What helps?", "kind": "text", "answered": 0, "answers": []}]}
    elif name == "import_survey_responses":
        data = {"survey_id": "survey_one", "imported": 2, "total_responses": 2}
    elif name in {"record_hypothesis", "record_hypothesis_result", "drop_hypothesis"}:
        data = {"hypothesis": HYPOTHESIS}
    elif name == "get_hypothesis":
        data = HYPOTHESIS
    elif name == "list_hypotheses":
        data = {"hypotheses": [HYPOTHESIS]}
    elif name in {"record_decision", "update_decision"}:
        data = {"decision": DECISION}
    elif name == "get_decision":
        data = DECISION
    elif name == "list_decisions":
        data = {"decisions": [DECISION]}
    elif name == "search":
        data = {"results": [{"id": "project:p", "title": "Study", "text": "Actual snippet", "url": "/jobs/p"}]}
    elif name == "fetch":
        data = {"id": "project:p", "title": "Study", "text": "Actual fetched document", "url": "/jobs/p", "metadata": {"kind": "project"}}
    elif name == "create_research_project":
        data = {"id": "p", "title": "Study", "goal": "Learn", "description": "Team research"}
    elif name == "list_research_projects":
        data = [{"id": "p", "title": "Study", "goal": "Learn", "description": "Team research"}]
    elif name == "list_notes":
        data = {"items": [NOTE], "total": 1, "has_more": False}
    elif SURFACES[name].family == "notes":
        data = NOTE
    elif name == "list_sections":
        data = [SECTION]
    elif name == "get_section_members":
        data = {"section": SECTION, "project": {"id": "p"}, "members": [{"id": "note_one", "kind": "note", "title": "Evidence", "summary": "Observed", "href": "/notes/note_one"}]}
    else:
        data = SECTION
    result = present(name, data if name in {"search", "fetch"} else {"data": data}, tool.fn_metadata)
    assert result.meta["sonaloop/presentation"]["component_id"] == SURFACES[name].component_id
    assert tool.meta["ui"]["resourceUri"] == SURFACES[name].uri
    resources = {str(resource.uri): resource for resource in asyncio.run(server.list_resources())}
    assert resources[SURFACES[name].uri].meta["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}


def test_actual_native_note_and_section_share_product_fragments(store):
    project = services.create_research_project("UI qualification", "Hermetic fixture", store=store)
    server = build_server()
    created = call(server, "create_note", {"project_id": project["id"], "title": "An observation", "text": "No image or model provider is needed."})
    note = created.structuredContent["data"]
    assert created.meta["sonaloop/presentation"]["state"] == "ready"
    assert services.get_note(note["id"], store=store)["note"] == note
    listed = call(server, "list_notes", {"project_id": project["id"]})
    assert str(note_content(note)) in listed.meta["sonaloop/presentation"]["html"]
    section = services.create_section(project["id"], "Evidence", member_ids=[f"note:{note['id']}"], store=store)
    resolved = call(server, "get_section_members", {"section_id": section["id"]})
    native = resolved.structuredContent["data"]
    assert str(section_content(native["section"], native["members"])) in resolved.meta["sonaloop/presentation"]["html"]
    assert "An observation" in resolved.meta["sonaloop/presentation"]["html"]


def test_projection_failure_does_not_repeat_or_erase_native_write(monkeypatch):
    server = FastMCP("single invocation")
    calls = []
    @server.tool()
    def create_note() -> dict[str, object]:
        calls.append(1)
        return {"data": {"unusual_future_shape": True}}
    tool = server._tool_manager._tools["create_note"]
    _decorate(tool)
    result = call(server, "create_note", {})
    assert len(calls) == 1
    assert result.structuredContent == {"data": {"unusual_future_shape": True}}
    assert not result.isError
    assert result.meta is None


def test_renderers_do_not_resolve_references_or_open_a_store(monkeypatch):
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("A pure renderer tried to read runtime state")
    monkeypatch.setattr(Store, "__init__", forbidden)
    assert "Actual" in note_content(NOTE)
    assert "note:note_one" in section_content(SECTION)
    assert "Evidence" in section_content(SECTION, [{"title": "Evidence", "kind": "note", "summary": "Kept local"}])


def test_empty_pagination_is_explicit_and_large_projection_keeps_native_output():
    server = build_server()
    tool = server._tool_manager._tools["list_notes"]
    empty = present("list_notes", {"data": {"items": [], "total": 0}}, tool.fn_metadata)
    assert empty.meta["sonaloop/presentation"]["state"] == "empty"
    large = {"data": {"items": [{**NOTE, "text": "x" * 200_000}], "total": 1}}
    result = present("list_notes", large, tool.fn_metadata)
    assert result.meta is None
    assert result.structuredContent == large


def test_packaged_resource_manifest_hashes_and_pure_ssr_declaration():
    root = Path(__file__).parents[1]
    for family in {surface.family for surface in SURFACES.values()}:
        manifest = json.loads((root / f"sonaloop/mcp_server/ui/{family}.manifest.json").read_text())
        html = (root / "sonaloop/mcp_server/ui" / manifest["resource"]["file"]).read_bytes()
        assert hashlib.sha256(html).hexdigest() == manifest["resource"]["sha256"]
        assert manifest["resource"]["bytes"] == len(html)
        assert manifest["actions"] == []
        assert "script" not in manifest["product"]
        for path, expected in manifest["sources"].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, path


def test_product_routes_use_shared_note_section_project_and_search_content(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.ui_components.discovery import project_heading, search_hit_content
    project = services.create_research_project("Unique discovery study", "Learn what matters", store=store)
    note = services.create_note(project["id"], "**Observation** <img src=x onerror=alert(1)>", title="Unique <script>note</script>", store=store)
    section = services.create_section(project["id"], "Observations", member_ids=[f"note:{note['id']}"], store=store)
    client = TestClient(web.create_app())
    assert str(note_content(note)) in client.get(f"/notes/{note['id']}").text
    members = services.section_members(section["id"], store=store)["members"]
    assert str(section_content(section, members)) in client.get(f"/sections/{section['id']}").text
    project_html = client.get(f"/jobs/{project['id']}").text
    assert '<p class="lead">Learn what matters</p>' in project_html
    assert 'sl-project-title' in project_html
    response = client.get("/api/search?q=Unique").json()
    assert response["rows"]
    for row in response["rows"]:
        assert row["presentation_html"] == search_hit_content(row["title"], row.get("subtitle", ""), row.get("date", ""))
        assert "<script>" not in row["presentation_html"]


def test_search_connector_preserves_its_bare_contract_and_actual_results(store):
    project = services.create_research_project("Bare connector unique project", "Semantic search", store=store)
    server = build_server()
    result = call(server, "search", {"query": "Bare connector unique"})
    assert "results" in result.structuredContent
    assert "data" not in result.structuredContent
    hit = next(hit for hit in result.structuredContent["results"] if project["id"] in hit["id"])
    fetched = call(server, "fetch", {"id": hit["id"]})
    assert fetched.structuredContent["id"] == hit["id"]
    assert "data" not in fetched.structuredContent
    assert "Bare connector unique project" in fetched.meta["sonaloop/presentation"]["html"]


def test_async_and_failed_native_calls_are_not_repeated():
    server = FastMCP("async preservation")
    calls = []
    @server.tool()
    async def list_notes() -> dict[str, object]:
        calls.append(1)
        return {"data": {"items": [], "total": 0}}
    _decorate(server._tool_manager._tools["list_notes"])
    result = call(server, "list_notes", {})
    assert len(calls) == 1
    assert result.meta["sonaloop/presentation"]["state"] == "empty"
    @server.tool()
    def create_note() -> dict[str, object]:
        calls.append(2)
        raise ValueError("Native validation rejected this input")
    _decorate(server._tool_manager._tools["create_note"])
    with pytest.raises(Exception, match="Native validation"):
        call(server, "create_note", {})
    assert calls == [1, 2]


def test_supported_ledger_rows_equal_implemented_tool_resources():
    from sonaloop.ui_components.coverage import coverage_data
    ledger = coverage_data()
    assert {row["tool"] for row in ledger["tools"] if row["status"] == "supported"} == set(SURFACES)
    server = build_server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    covered = {row["tool"] for row in ledger["tools"] if row["status"] in {"supported", "existing"}}
    assert covered == {name for name, tool in tools.items() if (tool.meta or {}).get("ui", {}).get("resourceUri")}

"""Native-output compatibility and shared passive rendering, without providers."""
import asyncio
import copy
import hashlib
import json
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
    if name == "search":
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

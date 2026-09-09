"""Five genuine ideation outputs retain native metadata and shared bodies."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES

CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/ideation.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_ideation_public_entry_retains_exact_values_and_never_resolves(case, monkeypatch):
    from sonaloop import services, artifacts
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Public ideation attempted a tool, reference lookup or Store read")
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    for name in {row["tool"] for row in CASES} | {"get_note", "get_persona", "get_council"}:
        monkeypatch.setattr(services, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    public = public_component_value(name, native)
    assert public == native == case["public_value"]
    surface = SURFACES[name]
    assert render_component_props(surface.component_id, {"name": name, "value": public}) == surface.render(native)
    assert native == case["value"]
    with pytest.raises(ValueError):
        render_component_props("sonaloop.research.notes-view", {"name": name, "value": public})
    with pytest.raises(ValueError):
        render_component_props(surface.component_id, {"name": name, "value": {**public, "_meta": {}}})


def test_five_original_tool_schemas_annotations_and_converted_outputs_remain_exact():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_ideation
    from sonaloop.mcp_server._research_ui import present
    original = FastMCP("original-ideation-integration")
    _tools_ideation.register_ideation(original)
    before = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    after = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    assert len(CASES) == 11 and len({case["tool"] for case in CASES}) == 5
    for case in CASES:
        name = case["tool"]
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].annotations.readOnlyHint is (name in {"get_ideation", "list_ideas"})
        assert after[name].meta["ui"]["resourceUri"] == SURFACES[name].uri
        envelope = deepcopy(case["envelope"])
        retained = deepcopy(envelope)
        metadata = original._tool_manager._tools[name].fn_metadata
        content, structured = metadata.convert_result(envelope)
        result = present(name, envelope, metadata)
        assert result.content == content and result.structuredContent == structured and envelope == retained
        assert result.meta["sonaloop/presentation"]["state"] == case["state"]

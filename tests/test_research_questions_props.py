"""Question registry integrates the original native result and pure shared body."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES

CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/questions.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_question_public_entry_preserves_each_original_row_and_has_no_io(case, monkeypatch):
    from sonaloop import services
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Question Component attempted a native call or Store read")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("record_open_questions", "get_research_frontier", "get_project_graph"):
        monkeypatch.setattr(services, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    public = public_component_value(name, native)
    assert public == native == case["public_value"]
    surface = SURFACES[name]
    assert render_component_props(surface.component_id, {"name": name, "value": public}) == surface.render(native)
    assert native == case["value"]
    with pytest.raises(ValueError):
        render_component_props("sonaloop.research.ideation-view", {"name": name, "value": public})


def test_original_question_schemas_and_converted_output_have_only_additive_ui_metadata():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_research
    from sonaloop.mcp_server._research_ui import present
    original = FastMCP("original-question-integration")
    _tools_research.register_research(original)
    before = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    after = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    assert len(CASES) == 9 and {case["tool"] for case in CASES} == {"record_open_questions", "get_research_frontier"}
    for case in CASES:
        name = case["tool"]
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].annotations.readOnlyHint is (name == "get_research_frontier")
        assert after[name].meta["ui"]["resourceUri"] == SURFACES[name].uri
        envelope = deepcopy(case["envelope"]); retained = deepcopy(envelope)
        metadata = original._tool_manager._tools[name].fn_metadata
        content, structured = metadata.convert_result(envelope)
        result = present(name, envelope, metadata)
        assert result.content == content and result.structuredContent == structured and envelope == retained
        assert result.meta["sonaloop/presentation"]["state"] == case["state"]

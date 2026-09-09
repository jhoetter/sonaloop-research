"""Public Product Understanding registration binds actual native result shapes."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES


CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/understanding.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_public_understanding_has_exact_projection_and_no_execution(case, monkeypatch):
    from sonaloop import services
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Public Component attempted a native action or Store read")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("get_product_understanding", "record_product_understanding", "record_manifest_product_understanding"):
        monkeypatch.setattr(services, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    public = public_component_value(name, native)
    assert public == case["public_value"] and native == case["value"]
    surface = SURFACES[name]
    assert render_component_props(surface.component_id, {"name": name, "value": public}) == surface.render(native)
    assert "operation_id" not in public["value"] and "operation_fingerprint" not in public["value"]
    if "dispatch" in public["value"]:
        assert "dispatch_token" not in public["value"]["dispatch"]
        assert "key" not in public["value"]["dispatch"].get("receipt", {})
    for bad in (native, {**public, "view": "stored" if public["view"] == "record" else "record"},
                {**public, "arguments": {}}, {**public, "_meta": {}}):
        with pytest.raises(ValueError):
            render_component_props(surface.component_id, {"name": name, "value": bad})


def test_native_three_plus_two_schemas_and_converted_outputs_are_unchanged():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_methodology, _tools_plan
    from sonaloop.mcp_server._research_ui import present
    original = FastMCP("original-understanding-integration")
    _tools_methodology.register_methodologies(original)
    _tools_plan.register_plan(original)
    decorated = build_server()
    before = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    after = {tool.name: tool for tool in asyncio.run(decorated.list_tools())}
    fixtures = Path(__file__).parents[1] / "tools/persona-ui/fixtures"
    additional = [case for family in ("projects", "researchplan")
        for case in json.loads((fixtures / (family + ".json")).read_text())
        if case["tool"] in {"set_project_methodology", "iterate_task"}]
    cases = CASES + additional
    assert len(cases) == 12 and len({case["tool"] for case in cases}) == 5
    for case in cases:
        name = case["tool"]
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].meta["ui"]["resourceUri"] == SURFACES[name].uri
        assert after[name].annotations.readOnlyHint is (name == "get_product_understanding")
        envelope = {"ok": True, "tool": name, "data": deepcopy(case["value"]), "_meta": {"latency_ms": 0.5}}
        retained = deepcopy(envelope)
        fn = original._tool_manager._tools[name]
        content, structured = fn.fn_metadata.convert_result(envelope)
        result = present(name, envelope, fn.fn_metadata)
        assert result.content == content and result.structuredContent == structured and envelope == retained
        assert "sonaloop/presentation" not in json.dumps(result.structuredContent)
        assert result.meta["sonaloop/presentation"]["state"] == case["state"]

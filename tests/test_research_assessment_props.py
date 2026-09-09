"""Actual Assessment/Markdown results use the shared pure public entry point."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES

CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/assessment.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_assessment_public_projection_preserves_native_and_has_no_effect(case, monkeypatch):
    from sonaloop import services, plan
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Public Assessment attempted a read, computation or native action")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("assess_project", "export_plan_md", "inject_work", "run_step"):
        monkeypatch.setattr(services, name, forbidden)
    for name in ("get_plan", "ready_tasks", "is_complete", "verify_unmet"):
        monkeypatch.setattr(plan, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    surface = SURFACES[name]
    public = public_component_value(name, native)
    assert public == case["public_value"] and native == case["value"]
    assert render_component_props(surface.component_id, {"name": name, "value": public}) == surface.render(native)
    for bad in (native, {**public, "view": "document" if name == "assess_project" else "assessment"},
                {**public, "_meta": {}}, {**public, "operation_id": "not-a-public-prop"}):
        with pytest.raises(ValueError):
            render_component_props(surface.component_id, {"name": name, "value": bad})


def test_native_assessment_contracts_and_original_converted_outputs_remain_exact():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_plan
    from sonaloop.mcp_server._research_ui import present
    original = FastMCP("original-assessment-integration")
    _tools_plan.register_plan(original)
    before = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    after = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    assert len(CASES) == 10 and len({case["tool"] for case in CASES}) == 2
    for case in CASES:
        name = case["tool"]
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].annotations.readOnlyHint is True
        assert after[name].meta["ui"]["resourceUri"] == SURFACES[name].uri
        envelope = {"ok": True, "tool": name, "data": deepcopy(case["value"]), "_meta": {"latency_ms": 0.5}}
        retained = deepcopy(envelope)
        metadata = original._tool_manager._tools[name].fn_metadata
        content, structured = metadata.convert_result(envelope)
        result = present(name, envelope, metadata)
        assert result.content == content and result.structuredContent == structured and envelope == retained
        assert result.meta["sonaloop/presentation"]["state"] == case["state"]
    assert "inject_work" not in SURFACES and after["inject_work"].annotations.readOnlyHint is False
    assert not (after["inject_work"].meta or {}).get("ui")

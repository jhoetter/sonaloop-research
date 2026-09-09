"""Authored public Plan values preserve native result semantics without execution."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES


CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/researchplan.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_public_plan_is_explicit_projection_without_native_reconstruction(case, monkeypatch):
    from sonaloop import services
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Public Plan rendering attempted native I/O")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("get_plan", "add_task", "record_frame", "link_evidence", "record_judgment",
                 "assess_progress", "park_evidence", "unpark_evidence", "run_step"):
        monkeypatch.setattr(services, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    public = public_component_value(name, native)
    assert public == case["public_value"] and native == case["value"]
    surface = SURFACES[name]
    assert render_component_props(surface.component_id, {"name": name, "value": public}) == surface.render(native)
    with pytest.raises(ValueError):
        render_component_props(surface.component_id, {"name": name, "value": native})
    for bad in ({**public, "operation_id": "not-public"}, {**public, "arguments": {}}):
        with pytest.raises(ValueError):
            render_component_props(surface.component_id, {"name": name, "value": bad})


def test_each_plan_tool_requires_its_selected_public_view():
    examples = {case["public_value"]["view"]: case["public_value"] for case in CASES}
    expected = {"get_plan": "plan", "add_task": "task", "record_frame": "task",
                "link_evidence": "task", "record_judgment": "judgment", "assess_progress": "progress",
                "park_evidence": "parked", "unpark_evidence": "unparked"}
    for name, wanted in expected.items():
        for view, value in examples.items():
            if view != wanted:
                with pytest.raises(ValueError, match="does not belong"):
                    render_component_props("sonaloop.research.researchplan-view", {"name": name, "value": value})


def test_public_plan_keeps_linked_and_checkpointed_judgment_states_distinct():
    cases = {case["scenario"]: case for case in CASES}
    linked = cases["researchplan-governed-judgment"]["public_value"]["value"]["dispatch"]
    checkpointed = cases["researchplan-judgment-replayed"]["public_value"]["value"]["dispatch"]
    replay = cases["researchplan-judgment-checkpoint-replayed"]["public_value"]["value"]["dispatch"]
    assert linked["state"] == "linked" and linked["checkpointed"] is False and "receipt" not in linked
    assert checkpointed["checkpointed"] is True and checkpointed["receipt"]["deduplicated"] is False
    assert replay["checkpointed"] is True and replay["receipt"]["deduplicated"] is True
    for value in (linked, checkpointed, replay):
        assert "operation_id" not in value and "dispatch_token" not in value
        assert "key" not in value.get("receipt", {})

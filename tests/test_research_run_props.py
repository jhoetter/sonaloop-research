"""The explicit public Run projection never reconstructs a native response."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES


CASES = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/run-journal.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["scenario"])
def test_run_public_mapping_matches_native_without_executing_or_rehydrating(case, monkeypatch):
    from sonaloop import services
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Public Run presentation attempted native I/O")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("start_run", "run_journal", "resume_project_run", "finish_run", "run_step"):
        monkeypatch.setattr(services, name, forbidden)
    name, native = case["tool"], deepcopy(case["value"])
    public = public_component_value(name, native)
    assert public == case["public_value"] and native == case["value"]
    assert render_component_props(SURFACES[name].component_id, {"name": name, "value": public}) == SURFACES[name].render(native)
    with pytest.raises(ValueError):
        render_component_props(SURFACES[name].component_id, {"name": name, "value": native})
    for bad in ({**public, "arguments": {}}, {**public, "operation_id": "not-a-public-prop"}):
        with pytest.raises(ValueError):
            render_component_props(SURFACES[name].component_id, {"name": name, "value": bad})


def test_run_selector_requires_its_exact_authored_view_even_when_other_view_is_valid():
    value = next(item["public_value"] for item in CASES if item["tool"] == "finish_run")
    assert value["view"] == "finished"
    for name in ("start_run", "run_journal", "resume_project_run"):
        with pytest.raises(ValueError, match="does not belong"):
            render_component_props("sonaloop.research.runs-view", {"name": name, "value": value})

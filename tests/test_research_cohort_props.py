"""Public cohort props omit one authority field while native results stay exact."""
from copy import deepcopy
import json
from pathlib import Path

from sonaloop.ui_components.component_props import public_component_value, render_component_props
from sonaloop.ui_components.registry import SURFACES


def test_exact_cohort_public_mapping_preserves_result_and_renderer():
    fixtures = json.loads((Path(__file__).parents[1] / "tools/persona-ui/fixtures/cohorts.json").read_text())
    for item in fixtures:
        value = deepcopy(item["value"])
        before = deepcopy(value)
        public = public_component_value(item["tool"], value)
        dispatch = value.get("dispatch")
        if isinstance(dispatch, dict) and "dispatch_token" in dispatch:
            assert "dispatch_token" not in public["dispatch"]
            assert set(dispatch) - set(public["dispatch"]) == {"dispatch_token"}
        assert value == before
        surface = SURFACES[item["tool"]]
        assert render_component_props(surface.component_id, {"name": item["tool"], "value": public}) == surface.render(value)


def test_public_cohort_mapping_does_not_recursively_drop_domain_keys():
    value = {"dispatch": {"dispatch_token": "inert-fixture", "state": "open"},
        "domain": {"dispatch_token": "a domain key is not this authority boundary"}}
    before = deepcopy(value)
    public = public_component_value("select_reaction_test_cohort", value)
    assert public["domain"] == value["domain"] and value == before
    assert public_component_value("get_persona", value) is value

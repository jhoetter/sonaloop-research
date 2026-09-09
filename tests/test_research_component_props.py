"""Public authored Component examples reuse native projections without execution."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sonaloop.ui_components.component_props import render_component_props, public_component_value
from sonaloop.ui_components.registry import SURFACES

ROOT = Path(__file__).parents[1]
DIRECTORY = ROOT / "sonaloop/ui_components/declarations"
PASSIVE_DECLARATIONS = [DIRECTORY / f"{family}.json" for family in sorted({surface.family for surface in SURFACES.values()})]


@pytest.mark.parametrize("path", PASSIVE_DECLARATIONS, ids=lambda path: path.stem)
def test_public_scenarios_validate_and_render_without_native_authority(path, monkeypatch):
    from sonaloop.storage import Store
    from sonaloop import services
    def forbidden(*args, **kwargs):
        pytest.fail("Public Component rendering invoked native services or storage")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("record_synthesis", "record_usability_session", "record_council", "create_note"):
        monkeypatch.setattr(services, name, forbidden)
    declaration = json.loads(path.read_text())
    assert declaration["schemaVersion"] == "sonaloop.customer-component.v1"
    assert len(declaration["requiredStates"]) == 6
    validator = Draft202012Validator(declaration["propsSchema"])
    for scenario in declaration["scenarios"]:
        validator.validate(scenario["props"])
        html, state = render_component_props(f"sonaloop.research.{path.stem}-view", scenario["props"])
        assert state == scenario["state"] and str(html).strip()
    for state in declaration["requiredStates"]:
        if state["state"] in {"loading", "error"}:
            assert state["disposition"] == "applicable" and state["scenarioIds"] == []
        if state["state"] in {"focus", "disabled"}:
            assert state["disposition"] == "not_applicable" and state["reason"]
    assert declaration["accessibility"]["keyboard"] == "not_reviewed"
    assert declaration["accessibility"]["screenReader"] == "not_reviewed"


def test_editable_public_text_is_actual_escaped_renderer_input():
    declaration = json.loads((DIRECTORY / "notes.json").read_text())
    props = deepcopy(declaration["scenarios"][0]["props"])
    props["value"]["items"][0]["title"] = "Edited public example"
    props["value"]["items"][0]["text"] = "Literal <script>private()</script> value."
    Draft202012Validator(declaration["propsSchema"]).validate(props)
    html, _ = render_component_props("sonaloop.research.notes-view", props)
    assert "Edited public example" in html and "<script>" not in html
    props["value"]["items"][0]["title"] = 123
    assert not Draft202012Validator(declaration["propsSchema"]).is_valid(props)


def test_public_projection_cannot_select_another_component_or_grant_execution():
    props = json.loads((DIRECTORY / "notes.json").read_text())["scenarios"][0]["props"]
    with pytest.raises(ValueError, match="does not belong"):
        render_component_props("sonaloop.research.sessions-view", props)
    for mutate in (lambda item: item.update(operation_id="not-authority"),
                   lambda item: item["value"].update(_meta={"token": "not-authority"}),
                   lambda item: item.update(name="delete_persona")):
        value = deepcopy(props)
        mutate(value)
        with pytest.raises(ValueError):
            render_component_props("sonaloop.research.notes-view", value)


def test_public_props_enforce_bytes_depth_and_finite_numbers():
    for value in ({"text": "x" * 9000}, {"value": float("nan")}, {"_meta": {}}):
        with pytest.raises(ValueError):
            render_component_props("sonaloop.research.notes-view", {"name": "list_notes", "value": value})
    nested = []
    for _ in range(14):
        nested = [nested]
    with pytest.raises(ValueError, match="traversal"):
        render_component_props("sonaloop.research.notes-view", {"name": "list_notes", "value": nested})


def test_remote_registration_public_alias_preserves_native_render_without_reserved_keys():
    from test_research_prototype_ui import record
    from sonaloop.ui_components.prototypes import registered_remote
    native = {"prototype": record(), "note": {"id": "note", "title": "Concept", "text": "Actual note."},
              "dispatch": {"dispatch_token": "not-a-public-prop"}}
    before = deepcopy(native)
    public = public_component_value("register_remote_prototype", native)
    assert set(public) == {"artifact", "note"} and native == before
    assert render_component_props("sonaloop.research.prototypes-view", {
        "name": "register_remote_prototype", "value": public}) == registered_remote(native)
    for value in (native, {**public, "dispatch": {}}, {**public, "artifact": {**record(), "_meta": {}}}):
        with pytest.raises(ValueError):
            render_component_props("sonaloop.research.prototypes-view", {
                "name": "register_remote_prototype", "value": value})


@pytest.mark.parametrize("family,name", [("sessions", "get_usability_session"), ("councils", "get_council"),
    ("syntheses", "get_synthesis"), ("surveys", "survey_results")])
def test_schema_keeps_required_fields_bound_to_the_selected_projection(family, name):
    declaration = json.loads((DIRECTORY / f"{family}.json").read_text())
    validator = Draft202012Validator(declaration["propsSchema"])
    assert not validator.is_valid({"name": name, "value": {}})
    assert not validator.is_valid({"name": name, "value": {"items": []}})
    assert not validator.is_valid({"name": name, "value": {"sessions": []}})


def test_large_family_uses_bounded_disjoint_selectors_without_weakening_required_fields():
    declaration = json.loads((DIRECTORY / "councils.json").read_text())
    names = {scenario["props"]["name"] for scenario in declaration["scenarios"]}
    assert len(names) > 8
    def inspect(value):
        if isinstance(value, list):
            for item in value: inspect(item)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in {"anyOf", "oneOf", "allOf"}:
                    assert 0 < len(child) <= 8
                inspect(child)
    inspect(declaration["propsSchema"])
    validator = Draft202012Validator(declaration["propsSchema"])
    for name in names:
        assert not validator.is_valid({"name": name, "value": {}}), name
    for name in ("record_head_to_head", "get_price_ladder", "query_councils"):
        props = next(row["props"] for row in declaration["scenarios"] if row["props"]["name"] == name)
        assert validator.is_valid(props)
        assert not validator.is_valid({**props, "name": "get_council"})

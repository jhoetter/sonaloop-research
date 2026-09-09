"""Actual methodology binding and iteration receipts, without replaying writers."""
from copy import deepcopy
import html
import json
import os
from pathlib import Path
import socket

import pytest

from sonaloop import services, plan as native
from sonaloop.storage import Store
from sonaloop.ui_components import projects, research_plan as ui, research_plan_rows as rows


def forbidden(*args, **kwargs):
    pytest.fail("Presentation attempted a native, filesystem, media or provider operation")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_methodology, _tools_plan
    server = FastMCP("original-plan-followup")
    _tools_methodology.register_methodologies(server)
    _tools_plan.register_plan(server)
    return server


@pytest.fixture
def examples(store):
    server, results = original_server(), []
    project = services.start_project("Method and iteration", "Examine an unresolved handover", store=store)
    def call(name, arguments, scenario):
        result = server._tool_manager._tools[name].fn(**arguments)
        assert result["ok"], result
        value = deepcopy(result["data"])
        public = ui.iteration_view(value) if name == "iterate_task" else deepcopy(value)
        markup, state = ui.iteration(value) if name == "iterate_task" else projects.methodology(value)
        assert state == "ready"
        results.append({"scenario": scenario, "tool": name, "input": arguments,
                        "value": value, "public_value": public, "state": state})
        return value
    for key in ("reaction_test", "dschool_micro"):
        call("set_project_methodology", {"project_id": project["id"], "methodology_key": key},
             "projects-methodology-" + key.replace("_", "-"))
    plan = native.get_plan(project["id"], store=store)
    for task in plan["tasks"]:
        task["status"] = "done"
    native.save_plan(plan, store=store)
    args = {"project_id": project["id"], "task_id": "verify__prototype_test",
            "note": "Inspect the rejected flow; keep the original evidence in its earlier round."}
    call("iterate_task", args, "researchplan-iteration-second")
    # Repeating this existing writer really creates another round. It has no
    # operation ID and cannot be represented as a deduplicated replay.
    call("iterate_task", args, "researchplan-iteration-next")
    return results


def test_native_followup_fixtures_are_exact_and_exportable(examples, tmp_path):
    from jsonschema import Draft202012Validator
    assert {item["tool"] for item in examples} == {"set_project_methodology", "iterate_task"}
    for item in examples:
        assert len(json.dumps({"name": item["tool"], "value": item["public_value"]},
                              ensure_ascii=False).encode()) < 8192
        if item["tool"] == "iterate_task":
            Draft202012Validator(ui.public_schema("iteration")).validate(item["public_value"])
            assert ui.render_view(item["public_value"]) == ui.iteration(item["value"])
        else:
            assert item["public_value"] == item["value"]
    target = Path(os.environ.get("RESEARCH_PLAN_FOLLOWUP_FIXTURE_PATH", tmp_path / "followup.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Original native Plan followup fixtures:", target, "count:", len(examples))


def test_methodology_renders_returned_project_without_claiming_plan_tasks(examples, store):
    first, second = examples[:2]
    assert first["value"]["methodology"] == "reaction_test"
    assert second["value"]["methodology"] == "dschool_micro"
    assert first["value"]["id"] == second["value"]["id"]
    assert "tasks" not in first["value"] and "idempotent_replay" not in second["value"]
    actual_plan = native.get_plan(second["value"]["id"], store=store)
    markup, _ = projects.methodology(first["value"])
    assert "reaction_test" in markup and "dschool_micro" not in markup
    assert "Tasks are available in the research plan" in markup and "Methodology saved" in markup
    assert all(task["id"] not in markup for task in actual_plan["tasks"])
    assert projects.project_body(first["value"], level="h3", description=True, passive=True) in markup
    integrity = first["value"]["integrity"]
    assert all(key in markup and str(value).lower() in markup for key, value in integrity.items())


def test_iteration_record_and_real_clones_are_separate_from_stored_history(examples, store):
    first, second = examples[2:]
    assert first["value"]["round"] == 2 and second["value"]["round"] == 3
    assert not set(first["value"]["tasks"]) & set(second["value"]["tasks"])
    pid = first["input"]["project_id"]
    plan = native.get_plan(pid, store=store)
    assert len(plan["iterations"]) == 2
    assert all("cloned" not in record for record in plan["iterations"])
    for index, item in enumerate((first, second)):
        value, public = item["value"], item["public_value"]
        assert value["tasks"] == [task["id"] for task in value["cloned"]]
        assert value["entry"] in value["tasks"]
        assert all(task["status"] == "todo" and task["frame"] is None and task["produces"] == []
                   for task in value["cloned"])
        assert all("deduplicated" not in task for task in value["cloned"])
        markup, _ = ui.iteration(value)
        shared = rows.iteration_content(plan["iterations"][index])
        assert shared in markup and shared in rows.history_content(ui.plan_view(plan)["value"])
        assert "Tasks from this round. Calling iteration again can create another round." in markup
        assert "__r" + str(value["round"]) in markup
        assert ui.render_view(public)[0] == markup
    # Later task state does not rewrite a retained invocation's returned clones.
    plan["tasks"][-1]["title"] = "A later task title"
    native.save_plan(plan, store=store)
    assert "A later task title" not in ui.iteration(first["value"])[0]


def test_both_followup_bodies_are_pure_and_leave_inputs_unchanged(examples, monkeypatch):
    before = deepcopy(examples)
    for item in examples:
        (ui.iteration if item["tool"] == "iterate_task" else projects.methodology)(item["value"])
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        for name in ("iterate_task", "set_project_methodology", "get_plan", "get_research_project"):
            patch.setattr(services, name, forbidden)
        for name in ("get_plan", "save_plan"):
            patch.setattr(native, name, forbidden)
        for name in ("open", "read_bytes", "read_text", "exists", "is_file"):
            patch.setattr(Path, name, forbidden)
        for item in examples:
            markup, state = (ui.iteration if item["tool"] == "iterate_task" else projects.methodology)(item["value"])
            assert state == "ready"
            assert not any(tag in markup for tag in ("<script", "<a ", "<form", "<input", "<button", "<img"))
    assert examples == before


@pytest.mark.parametrize("change", ["missing-clones", "wrong-order", "wrong-entry", "duplicate-clone", "unknown-task-field"])
def test_iteration_shape_mismatch_does_not_invent_a_usable_result(examples, change):
    value = deepcopy(examples[2]["value"])
    if change == "missing-clones":
        del value["cloned"]
    elif change == "wrong-order":
        value["cloned"].reverse()
    elif change == "wrong-entry":
        value["entry"] = "not-returned"
    elif change == "duplicate-clone":
        value["cloned"].append(deepcopy(value["cloned"][0]))
        value["tasks"].append(value["tasks"][0])
    else:
        value["cloned"][0]["requires"]["unsupported"] = "cannot silently erase nested fields"
    with pytest.raises(ValueError):
        ui.iteration(value)


@pytest.mark.parametrize("change", ["missing-methodology", "empty-methodology", "bad-integrity", "boolean-schema"])
def test_methodology_rejects_unsupported_native_records(examples, change):
    value = deepcopy(examples[0]["value"])
    if change == "missing-methodology":
        del value["methodology"]
    elif change == "empty-methodology":
        value["methodology"] = ""
    elif change == "boolean-schema":
        value["integrity"]["schema"] = False
    else:
        value["integrity"]["unknown"] = {"nested": "unsupported"}
    with pytest.raises(ValueError):
        projects.methodology(value)


def test_followup_escapes_authored_prose_without_fetching_it(examples):
    attack = '<img src="https://example.invalid/secret" onerror="alert(1)">'
    iteration = deepcopy(examples[2]["value"])
    iteration["note"] = attack
    iteration["cloned"][0]["title"] = attack
    project = deepcopy(examples[0]["value"])
    project["title"], project["goal"] = attack, attack
    for markup in (ui.iteration(iteration)[0], projects.methodology(project)[0]):
        assert attack not in markup and html.escape(attack) in markup
        assert "<img" not in markup and "<script" not in markup


def test_actual_product_plan_uses_persisted_iteration_body(examples, store):
    from sonaloop.web._graph import _plan_html
    pid = examples[2]["input"]["project_id"]
    plan = native.get_plan(pid, store=store)
    product = _plan_html(plan, store)
    public = ui.plan_view(plan)["value"]
    assert rows.history_content(public) in product
    assert all(rows.iteration_content(record) in product for record in plan["iterations"])
    assert "Tasks created for this round" not in product


def test_native_registered_methodology_forms_remain_complete(examples):
    iteration = examples[2]["value"]
    markup, _ = ui.iteration(iteration)
    registered = [form for task in iteration["cloned"]
                  for form in task["presentation"].get("registered_forms", [])]
    assert registered
    for form in registered:
        assert set(form) == {"primitive", "form", "primitive_label", "form_label", "label", "description"}
        assert all(html.escape(value) in markup for value in form.values())
    bad = deepcopy(iteration)
    target = next(task for task in bad["cloned"] if task["presentation"].get("registered_forms"))
    target["presentation"]["registered_forms"][0]["action"] = "must-not-become-a-control"
    with pytest.raises(ValueError):
        ui.iteration(bad)


def test_native_methodology_form_declaration_objects_keep_their_actual_tags():
    from sonaloop import methodology
    spec = deepcopy(methodology._load_builtin_specs()["dschool_micro"])
    step = next(step for step in spec["steps"] if step.get("presentation", {}).get("forms"))
    first = step["presentation"]["forms"][0]
    primitive, form = first.split("/", 1)
    step["presentation"]["forms"] = [{"primitive": primitive, "form": form}, {"primitive": primitive, "id": form}]
    # The existing native normalizer explicitly accepts both declaration spellings.
    normalized = methodology._norm_step(step)
    assert len(normalized["presentation"]["registered_forms"]) == 1
    spec["steps"][spec["steps"].index(step)] = normalized
    plan = native.seed_plan_from_methodology("form-declaration", "Supplied forms", spec)
    value = ui.plan_view(plan)
    markup = ui.render_view(value)[0]
    assert html.escape(primitive) in markup and html.escape(form) in markup
    matching = [task for task in value["value"]["tasks"] if task["presentation"].get("forms") == normalized["presentation"]["forms"]]
    assert matching and "<button" not in markup and "<form" not in markup

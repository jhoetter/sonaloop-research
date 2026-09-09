"""Native graph/result values remain real, scoped and free of renderer reads."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from sonaloop import services
from sonaloop.storage import Store
from sonaloop.ui_components import project_graph, predictions


@pytest.fixture
def seeded(store, monkeypatch):
    from conftest import make_profile
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    persona = services.record_persona("Synthetic graph reader", make_profile("Graph reader"), generate_avatar=False, store=store)
    project = services.start_project("Handover ownership", "Can the next shift identify the owner?",
                                    persona_ids=[persona["id"]], operation_id="graph-ui-project", store=store)
    council = services.record_council(project["id"], "Who owns the next action?", [persona["id"]],
        statements=[{"persona_id": persona["id"], "text": "The next owner is unclear.", "stance": {"value": -1}}],
        predictions=[{"persona_id": persona["id"], "action": "Ask for the owner", "step": 0,
                      "subject": "Handover", "likelihood": .6, "trigger": "No owner is named", "refs": []}],
        key="graph-ui-council", store=store)
    synthesis = services.record_synthesis("Name the next owner", "What makes the next step clear?",
        council_ids=[council["id"]], payload={"gesamtbild": "Naming the owner helps the next shift."},
        project_id=project["id"], key="graph-ui-synthesis", store=store)
    services.create_note(project["id"], "An unresolved handover", "The team cannot find the owner.", store=store)
    services.record_open_questions(project["id"], ["Who updates the owner?"], store=store)
    return project, council, synthesis


def test_native_graph_preserves_every_node_edge_count_and_literal_stance(seeded, store):
    value = services.get_project_graph(seeded[0]["id"], store=store)
    before = deepcopy(value)
    html, state = project_graph.graph(value)
    assert state == "ready" and value == before
    for node in value["nodes"]:
        assert node["study_id"] in html and node["title"] in html
    for edge in value["edges"]:
        assert edge["from_study"] in html and edge["to_study"] in html
    assert value["edges"] and "<dt>-1</dt><dd>1</dd>" in html
    assert "Product-only session and decision enrichment is not loaded" in html


def test_unknown_phase_and_count_stub_mismatch_are_not_normalized(seeded, store):
    value = services.get_project_graph(seeded[0]["id"], store=store)
    node = next(row for row in value["nodes"] if row["kind"] == "council")
    node.update(phase="Unrecognized native phase", voices=0)
    html, _ = project_graph.graph(value)
    assert "Unrecognized native phase" in html and node["study_id"] in html
    assert "<dt>voices</dt><dd>0</dd>" in html and node["personas"][0]["id"] in html


def test_product_outline_uses_exact_shared_cells_with_prepared_media(seeded, store, monkeypatch):
    from sonaloop.web import _graph_outline
    from sonaloop.web._html import h
    graph = services.get_project_graph(seeded[0]["id"], store=store)
    before = _graph_outline._outline_html(graph)
    calls = []
    def capture(title, **kwargs):
        cells = project_graph.outline_cells(title, **kwargs)
        calls.append((title, kwargs, cells))
        return cells
    monkeypatch.setattr(_graph_outline, "outline_cells", capture)
    after = _graph_outline._outline_html(graph)
    assert before == after and len(calls) == len(graph["nodes"]) + len(graph["open_questions"])
    assert all("timestamp" in kw and "lead" in kw for _, kw, _ in calls)
    hostile = project_graph.outline_cells('<img src=x onerror="bad()">')
    assert "&lt;img" in str(h("div", {}, hostile)) and "<img" not in str(h("div", {}, hostile))


def test_graph_and_predictions_do_not_query_store_media_or_services(seeded, store, monkeypatch):
    value = services.get_project_graph(seeded[0]["id"], store=store)
    predicted = services.aggregate_predictions(seeded[0]["id"], store=store)
    from sonaloop.web import ui, _presence
    def forbidden(*args, **kwargs):
        pytest.fail("Pure result rendering attempted a runtime/media operation")
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(ui, "avatar_group", forbidden)
    monkeypatch.setattr(_presence, "file_card", forbidden)
    for name in ("get_project_graph", "get_study_result", "aggregate_predictions"):
        monkeypatch.setattr(services, name, forbidden)
    before = deepcopy((value, predicted))
    assert project_graph.graph(value)[1] == "ready"
    assert predictions.predictions(predicted)[1] == "ready"
    assert (value, predicted) == before


def test_predictions_keep_record_counts_zero_likelihood_and_null_distinct(seeded, store):
    value = services.aggregate_predictions(seeded[0]["id"], store=store)
    value["groups"][0].update(count=3, likelihood_mean=0)
    value.update(total=3)
    html, state = predictions.predictions(value)
    assert state == "ready" and "<dd>0</dd>" in html and "records, not unique people" in html
    value["groups"][0]["likelihood_mean"] = None
    html, _ = predictions.predictions(value)
    assert "<dd>—</dd>" in html


def test_fixture_export_from_original_native_readers(seeded, store, tmp_path):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_research, _tools_substrate, _tools_predictions
    server = FastMCP("original-graph-result")
    for registration in (_tools_research.register_research, _tools_substrate.register_substrate, _tools_predictions.register_predictions):
        registration(server)
    cases = []
    for name in ("get_project_graph", "get_study_result", "aggregate_predictions"):
        arguments = {"project_id": seeded[0]["id"]}
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"]
        cases.append({"scenario": name, "tool": name, "input": arguments, "value": envelope["data"]})
    empty = services.create_research_project("No observations yet", goal="A new question", store=store)
    for name in ("get_project_graph", "get_study_result", "aggregate_predictions"):
        arguments = {"project_id": empty["id"]}
        envelope = server._tool_manager._tools[name].fn(**arguments)
        cases.append({"scenario": name + "-empty", "tool": name, "input": arguments, "value": envelope["data"]})
    path = Path(os.environ.get("RESEARCH_GRAPH_FIXTURE_PATH", tmp_path / "graph-fixtures.json"))
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2))
    print("Original native graph/results fixtures:", path)


def test_study_native_projection_and_real_product_route_share_body(seeded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.ui_components import project_results
    value = services.get_study_result(seeded[0]["id"], store=store)
    html, state = project_results.study(value)
    assert state == "ready" and seeded[1]["prompt"] in html and seeded[2]["title"] in html
    seen = []
    render = project_results.study
    def capture(value):
        result = render(value); seen.append((deepcopy(value), result[0])); return result
    monkeypatch.setattr(project_results, "study", capture)
    client = TestClient(web.create_app())
    response = client.get(f'/jobs/{seeded[0]["id"]}/results')
    assert response.status_code == 200 and len(seen) == 1 and str(seen[0][1]) in response.text
    assert seen[0][0]["project"]["id"] == seeded[0]["id"]
    assert "not observed behavior" in response.text and "Name the next owner" in response.text


def test_native_partial_projection_is_unavailable_and_never_refetched(seeded, store, monkeypatch):
    from sonaloop.services import _substrate
    from sonaloop.ui_components import project_results
    calls = []
    def absent(*args, **kwargs):
        calls.append(True); raise RuntimeError("Synthetic projection failure")
    for name in ("project_run_state", "project_health", "aggregate_predictions"):
        monkeypatch.setattr(_substrate, name, absent)
    value = services.get_study_result(seeded[0]["id"], store=store)
    assert len(calls) == 3 and all(value[key] is None for key in ("run_state", "project_health", "predictions"))
    before = deepcopy(value)
    def forbidden(*args, **kwargs):
        pytest.fail("Missing native projection must not be retried by the view")
    monkeypatch.setattr(Store, "__init__", forbidden)
    for name in ("project_run_state", "project_health", "aggregate_predictions", "get_study_result"):
        monkeypatch.setattr(services, name, forbidden)
    html, state = project_results.study(value)
    assert state == "ready" and value == before
    assert str(html).count("Not supplied; no successful result is inferred.") == 3
    assert seeded[2]["title"] in html


def test_legacy_supplied_native_record_gets_truthful_product_render_fallback(seeded, store):
    from starlette.testclient import TestClient
    from sonaloop import web
    store.upsert_synthesis({"id": "legacy-result", "title": "Legacy supplied answer",
        "project_id": seeded[0]["id"], "created_at": "2026-01-01", "council_ids": [seeded[1]["id"]]})
    value = services.get_study_result(seeded[0]["id"], store=store)
    assert any(x["id"] == "legacy-result" for x in value["syntheses"])
    response = TestClient(web.create_app()).get(f'/jobs/{seeded[0]["id"]}/results')
    assert response.status_code == 200
    assert "This native result cannot be displayed completely." in response.text
    assert "Not supplied; no successful result is inferred." not in response.text


def test_three_actual_mcp_readers_preserve_schemas_values_and_execute_once(seeded, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_research, _tools_substrate, _tools_predictions
    original = FastMCP("original-graph-readers")
    for register in (_tools_research.register_research, _tools_substrate.register_substrate, _tools_predictions.register_predictions):
        register(original)
    server = build_server()
    old = {x.name: x for x in asyncio.run(original.list_tools())}
    new = {x.name: x for x in asyncio.run(server.list_tools())}
    names = ("get_project_graph", "get_study_result", "aggregate_predictions")
    for name in names:
        assert old[name].inputSchema == new[name].inputSchema and old[name].outputSchema == new[name].outputSchema
        invoke = getattr(services, name); returned = []
        def once(*args, **kwargs):
            value = invoke(*args, **kwargs); returned.append(deepcopy(value)); return value
        with monkeypatch.context() as patch:
            patch.setattr(services, name, once)
            result = asyncio.run(server.call_tool(name, {"project_id": seeded[0]["id"]}))
        assert not result.isError and len(returned) == 1
        # Native MCP serializes integer stance-count keys into JSON object keys.
        assert result.structuredContent["data"] == json.loads(json.dumps(returned[0]))
        assert result.meta["sonaloop/presentation"]["tool"] == name
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/projects/v1"

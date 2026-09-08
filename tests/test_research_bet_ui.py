"""Native hypothesis/decision results reuse the product bodies without extra reads."""
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from sonaloop import artifacts, services
from sonaloop.mcp_server import build_server
from sonaloop.mcp_server._research_ui import present
from sonaloop.ui_components import bets


HYPOTHESIS = {"id": "hyp_fixture", "text": "A named owner reduces handover time",
              "prediction": {"metric": "minutes", "expected_value": 4, "tolerance": 1, "confidence": .8},
              "status": "validated", "result": {"observed_value": 4.5, "note": "Observed during the pilot",
                                                   "source": {"kind": "external", "text": "Synthetic observation"}},
              "derived_from": [{"kind": "council", "id": "council_unresolved"}]}
DECISION = {"id": "dec_fixture", "title": "Name a handover owner", "decision": "Display responsibility before the next shift.",
            "status": "adopted", "based_on": [{"kind": "hypothesis", "id": "hyp_fixture"}],
            "rejected": [{"kind": "council", "id": "council_unresolved", "note": "No explicit owner"}],
            "supersedes": "dec_previous"}


def _call(server, name, **arguments):
    return asyncio.run(server.call_tool(name, arguments))


def _html(result):
    return result.meta["sonaloop/presentation"]["html"]


@pytest.mark.parametrize("module", ["hypotheses", "decisions"])
def test_native_tool_schemas_are_preserved_for_bet_families(module):
    from importlib import import_module
    original = FastMCP("original")
    getattr(import_module(f"sonaloop.mcp_server._tools_{module}"), f"register_{module}")(original)
    decorated = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    for tool in asyncio.run(original.list_tools()):
        assert decorated[tool.name].inputSchema == tool.inputSchema
        assert decorated[tool.name].outputSchema == tool.outputSchema


def test_bet_cards_keep_values_status_references_and_full_text_without_resolution(monkeypatch):
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Rendering tried to access native data")
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    hypothesis, state = bets.hypothesis(HYPOTHESIS)
    assert state == "ready"
    for text in ("minutes", "4 ±1", "80%", "4.5", "Observed during the pilot", "Synthetic observation", "council_unresolved"):
        assert text in hypothesis
    # A compact App has no clamp interaction. A long decision must remain complete.
    decision, state = bets.decision({**DECISION, "decision": "Long reason. " * 100 + "Final consequence."})
    assert state == "ready"
    for text in ("hyp_fixture", "council_unresolved", "No explicit owner", "dec_previous", "Final consequence."):
        assert text in decision
    assert "sl-clamp" not in decision and "<button" not in decision


@pytest.mark.parametrize("render,value", [(bets.hypothesis, HYPOTHESIS), (bets.decision, DECISION)])
def test_untrusted_artifact_text_is_escaped(render, value):
    hostile = {**value, "text": "<script>bad()</script>", "title": '<img src=x onerror="bad()">',
               "decision": "<script>bad()</script>"}
    html, _ = render(hostile)
    assert "<script>" not in html and "<img" not in html
    assert "&lt;" in html


@pytest.mark.parametrize("family,render", [("hypotheses", bets.hypotheses), ("decisions", bets.decisions)])
def test_empty_native_collections_do_not_invent_artifacts(family, render):
    html, state = render({family: []})
    assert state == "empty" and "sl-research-empty" in html
    assert "sl-research-card" not in html


def test_successor_result_keeps_both_actual_decisions():
    predecessor = {**DECISION, "status": "superseded", "superseded_by": "dec_next"}
    successor = {**DECISION, "id": "dec_next", "title": "Successor decision", "supersedes": DECISION["id"]}
    html, state = bets.decision_write({"decision": predecessor, "successor": successor})
    assert state == "ready" and str(html).count('<article class="sl-research-card">') == 2
    assert "Successor decision" in html and "Name a handover owner" in html


def test_passive_references_keep_full_qualifiers_and_quoted_source_addresses(monkeypatch):
    from sonaloop.web._render import render_ref
    def forbidden(*args, **kwargs):
        pytest.fail("Passive references must not resolve even if a caller supplies a Store")
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    text = "An observation with substantial context. " * 12 + "Only applies during the pilot."
    reference = {"kind": "council", "id": "council_real", "anchor": "statement_3", "quote": text}
    html = render_ref(reference, object(), passive=True)
    assert text in html and "council:council_real#statement_3" in html
    assert "href=" not in html and "title=" not in html
    decision, _ = bets.decision({**DECISION, "based_on": [reference]})
    assert text in decision and "council:council_real#statement_3" in decision
    with pytest.raises(ValueError, match="checkable"):
        bets.hypothesis({**HYPOTHESIS, "prediction": {}})


def test_invalid_projection_keeps_the_successful_native_result():
    server = build_server()
    native = {"data": {"hypothesis": {"id": "future", "future_shape": True}}, "warnings": ["Keep native semantics"]}
    result = present("record_hypothesis", native, server._tool_manager._tools["record_hypothesis"].fn_metadata)
    assert result.structuredContent == native
    assert not result.isError and result.meta is None


def test_actual_native_bet_and_decision_lifecycle_and_product_reuse(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web.pages.hypotheses import _hypothesis_reads
    from sonaloop.web.pages.decisions import _decision_reads
    project = services.create_research_project("Bet UI qualification", "Hermetic native store", store=store)
    server = build_server()
    written = _call(server, "record_hypothesis", project_id=project["id"], text=HYPOTHESIS["text"], prediction=HYPOTHESIS["prediction"])
    hypothesis = written.structuredContent["data"]["hypothesis"]
    assert hypothesis["status"] == "open" and "minutes" in _html(written)
    observed = _call(server, "record_hypothesis_result", hypothesis_id=hypothesis["id"], observed_value=4.5,
                     source={"kind": "external", "text": "Synthetic observation"}, note="Observed during the pilot")
    assert observed.structuredContent["data"]["status"] == "validated"
    current = _call(server, "get_hypothesis", hypothesis_id=hypothesis["id"])
    hypothesis = current.structuredContent["data"]
    assert "4.5" in _html(current)
    assert hypothesis["id"] in _call(server, "list_hypotheses", project_id=project["id"]).content[0].text
    dropped = _call(server, "record_hypothesis", project_id=project["id"], text="Question became moot", prediction=HYPOTHESIS["prediction"])
    dropped = _call(server, "drop_hypothesis", hypothesis_id=dropped.structuredContent["data"]["hypothesis"]["id"], note="No longer relevant")
    assert dropped.structuredContent["data"]["hypothesis"]["status"] == "dropped"
    assert "No longer relevant" in _html(dropped)
    decision = _call(server, "record_decision", project_id=project["id"], title=DECISION["title"], decision=DECISION["decision"],
                     based_on=[{"kind": "hypothesis", "id": hypothesis["id"]}]).structuredContent["data"]["decision"]
    adopted = _call(server, "update_decision", decision_id=decision["id"], status="adopted")
    assert adopted.structuredContent["data"]["decision"]["status"] == "adopted"
    current_decision = _call(server, "get_decision", decision_id=decision["id"])
    decision = current_decision.structuredContent["data"]
    assert DECISION["decision"] in _html(current_decision)
    assert DECISION["title"] in _html(_call(server, "list_decisions", project_id=project["id"]))
    client = TestClient(web.create_app())
    product_hypothesis = client.get(f"/hypotheses/{hypothesis['id']}").text
    for fragment in _hypothesis_reads(hypothesis, store)[:2]:
        if fragment:
            assert str(fragment) in product_hypothesis
            assert str(fragment) in _html(current)
    product_decision = client.get(f"/decisions/{decision['id']}").text
    body = _decision_reads(decision, store, {})[0]
    assert str(body) in product_decision and str(body) in _html(current_decision)
    with pytest.raises(Exception, match="only an open bet"):
        _call(server, "drop_hypothesis", hypothesis_id=hypothesis["id"])

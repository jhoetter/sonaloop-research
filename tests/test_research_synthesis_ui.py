"""Actual report bodies, explicit presentation seams, and native MCP envelopes."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from sonaloop import artifacts, services, web
from sonaloop.models import Synthesis
from sonaloop.storage import Store
from sonaloop.ui_components import reports, syntheses
from sonaloop.web import _report, _synthesis


def record(scope="convergence"):
    value = Synthesis(id="synthesis_fixture", title="Who owns the handover?", start_input="What survives a shift change?",
        council_ids=["source_one"], arc_narrative="The concern remains visible.\n\nFinal arc qualifier.",
        gesamtbild="Ownership is unclear. The handover needs context.\n\nOnly during the pilot.",
        positionierung="Keep the final **scope qualifier**.", references=[{"council_id": "source_one", "role": "counterexample"}],
        citations=[{"kind": "council", "ref": "source_one#statement_3", "quote": "Only on the late shift."}],
        created_at="2026-09-09T01:00:00Z", scope=scope, status="in_progress",
        findings=[{"id": "f1", "kind": "recommendation", "text": "Keep a named owner.", "score": {"effort": 1, "value": 4},
                   "refs": [{"kind": "council", "id": "source_one", "anchor": "st3", "quote": "Final source qualifier."}]},
                  {"id": "f2", "kind": "new_customer_kind", "text": "An unfamiliar finding still matters."}],
        statements=[{"persona_id": "persona_fixture", "text": "I need the **final context**.",
                     "stance": {"value": -1, "label": "skeptical"}, "meta": {"claim_posture": "simulated"},
                     "refs": [{"kind": "council", "id": "source_one", "anchor": "st3", "quote": "Full quoted evidence."}]}],
    ).to_dict()
    if scope == "project":
        value.update(lead="The complete **report lead**.",
            limitations=[{"original_status": "overridden", "rationale": "Only the supplied pilot is represented."}],
            graph_snapshot={"nodes": [{"study_id": "council:source_one", "title": "Frozen source title"}]},
            sections=[{"id": "section_one", "heading": "What the next shift needs", "markdown":
                "Before the second figure.\n\n![[fig:2]]\n\nAfter the second figure.\n\n:::risk\nFull callout qualifier.\n:::\n\n![[fig:1]]",
                "source_study_ids": ["council:source_one"],
                "citations": [{"study_id": "council:source_one", "quote": "Full section citation."}],
                "figures": [{"kind": "future_media", "id": "unresolved_first", "caption": "First slot caption"},
                            {"kind": "asset", "id": "asset_second", "caption": "Second slot caption"}]},
                      {"id": "pending", "heading": "Not yet authored", "markdown": "", "figures": [], "citations": [], "source_study_ids": []}])
    return value


def forbidden(*args, **kwargs):
    pytest.fail("Passive/shared body attempted Store, media, chart derivation or filesystem access")


@pytest.mark.parametrize("scope", ["convergence", "project"])
def test_passive_complete_native_content_never_resolves_runtime_data(scope, monkeypatch):
    value = record(scope)
    value["gesamtbild"] += "\n\n" + "Long executive context. " * 100 + "Final executive qualifier."
    value["statements"][0]["text"] += " Long voice context. " * 100 + "Final voice qualifier."
    before = deepcopy(value)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(artifacts, "finding_kind", forbidden)
        patch.setattr(artifacts, "synthesis_sentiment_counts", forbidden)
        patch.setattr(_report, "_ref_titler", forbidden)
        patch.setattr(_report, "_resolve_figure", forbidden)
        patch.setattr(_report.ui, "avatar_group", forbidden)
        patch.setattr(_synthesis, "_charts_row", forbidden)
        patch.setattr(_synthesis, "_sentiment_section", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "is_file", forbidden)
        html, state = syntheses.synthesis(value)
        assert _report.render_report(value, object(), passive=True) in html
    assert value == before and state == "ready"
    for text in ("Final executive qualifier.", "Final voice qualifier.", "Final arc qualifier.", "scope qualifier",
                 "new_customer_kind", "An unfamiliar finding still matters.", "council:source_one#st3",
                 "council:source_one#statement_3", "Full quoted evidence.", "Final source qualifier.", "counterexample"):
        assert text in html
    assert not any(token in html for token in ("<img", "<button", "<details", "<svg", "sl-clamp", "claim-notice--verified"))
    assert "sentiment-detail" not in html and "stacked" not in html


def test_project_preserves_figure_positions_caption_sources_and_unwritten_sections():
    html, _ = syntheses.synthesis(record("project"))
    assert html.index("Before the second figure") < html.index("asset:asset_second") < html.index("After the second figure")
    assert html.index("Full callout qualifier") < html.index("future_media:unresolved_first")
    for text in ("First slot caption", "Second slot caption", "Full section citation.", "Frozen source title — council:source_one",
                 "Only the supplied pilot is represented.", "not yet authored", "report lead"):
        assert text in html
    html = _report._body("Missing ![[fig:8]] stays addressable.", [], passive=True)
    assert "![[fig:8]]" in html
    figure = _report._passive_figure({"kind": "chart", "series": [{"label": "Pilot", "value": 2}]}, 1)
    assert "![[fig:1]] · chart" in figure["html"] and "chart:1" not in figure["html"]


def test_passive_figures_show_semantic_values_or_literal_references(monkeypatch):
    monkeypatch.setattr(_report, "_resolve_figure", forbidden)
    value = record("project")
    value["sections"][0]["figures"] = [
        {"kind": "chart", "of": "stats", "source_id": "synthesis:recorded_source", "caption": "Exact supplied pilot values",
         "series": [{"label": "No responses", "value": 0}, {"label": "Change", "value": -7.25},
                    {"label": "<iframe>", "value": "72% · pilot only"}],
         "unknown_extension": {"opaque": "Do not turn arbitrary metadata into UI"}},
        {"kind": "chart", "of": "line", "caption": "An authored trend reference",
         "series": [{"label": "Future chart shape", "points": [2, 7]}]},
    ]
    html, _ = syntheses.synthesis(value)
    assert '<th scope="row">No responses</th><td>0</td>' in html
    assert '<th scope="row">Change</th><td>-7.25</td>' in html
    assert "&lt;iframe&gt;" in html and "72% · pilot only" in html
    assert "synthesis:recorded_source" in html and "chart:synthesis:recorded_source" not in html
    assert "Exact supplied pilot values" in html and "An authored trend reference" in html
    assert "Figure reference only" in html and "<code>line</code>" in html
    assert "unknown_extension" not in html and "Do not turn arbitrary metadata" not in html
    assert "<pre" not in html and "<iframe>" not in html and "<svg" not in html and "<img" not in html


def test_product_figure_resolution_keeps_original_inline_slot_numbers(store, monkeypatch):
    value = record("project")
    monkeypatch.setattr(_report, "_resolve_figure", lambda figure, *args, **kwargs:
        None if figure["id"] == "unresolved_first" else {"url": "/fixture/second.png", "caption": "Actual second figure"})
    original = reports.report_body
    captured = []
    def inspect(report, prepared, **kwargs):
        captured.append(prepared)
        assert prepared.figures[0][0] is None and prepared.figures[0][1]["url"] == "/fixture/second.png"
        with monkeypatch.context() as patch:
            patch.setattr(Store, "get_persona", forbidden)
            patch.setattr(_report, "_resolve_figure", forbidden)
            patch.setattr(_report, "_ref_titler", forbidden)
            patch.setattr(Path, "open", forbidden)
            return original(report, prepared, **kwargs)
    monkeypatch.setattr(reports, "report_body", inspect)
    html = _report.render_report(value, store)
    assert len(captured) == 1
    assert html.index("Before the second figure") < html.index('src="/fixture/second.png"') < html.index("After the second figure")
    assert html.count('src="/fixture/second.png"') == 1


def test_pending_section_keeps_its_supplied_figures_and_unpaired_prompts():
    value = record("project")
    value["sections"][0]["markdown"] = ""
    value["prompts"] = [{"id": "q1", "kind": "question", "text": "An unanswered native prompt."},
                        {"id": "q2", "kind": "question", "text": "Another unanswered native prompt."}]
    value["statements"] = []
    html, _ = syntheses.synthesis(value)
    assert "First slot caption" in html and "Second slot caption" in html
    assert "An unanswered native prompt." in html and "Another unanswered native prompt." in html
    assert "sl-research-voices" not in html and "sl-research-statement" not in html


def test_product_convergence_body_consumes_only_prepared_context(store, monkeypatch):
    value = record()
    original = syntheses.synthesis_body
    entered = []
    def inspect(record, prepared, **kwargs):
        entered.append(prepared)
        assert "Keep a named owner." in prepared.recommendations
        assert "final context" in prepared.voices
        with monkeypatch.context() as patch:
            patch.setattr(Store, "get_council_session", forbidden)
            patch.setattr(Store, "get_persona", forbidden)
            patch.setattr(artifacts, "resolve_ref", forbidden)
            patch.setattr(artifacts, "finding_kind", forbidden)
            patch.setattr(Path, "open", forbidden)
            return original(record, prepared, **kwargs)
    monkeypatch.setattr(syntheses, "synthesis_body", inspect)
    html, _ = _synthesis._synthesis_html(store, value)
    assert len(entered) == 1 and "Only during the pilot." in html


@pytest.mark.parametrize("scope", ["convergence", "project"])
def test_actual_product_route_uses_shared_body_and_preserves_controls(scope, store, monkeypatch):
    from starlette.testclient import TestClient
    value = record(scope)
    value["gesamtbild"] += "\n\n" + "More product context. " * 90
    store.upsert_synthesis(value)
    captured = []
    original = reports.report_body
    def inspect(record, prepared, **kwargs):
        html = original(record, prepared, **kwargs)
        captured.append(html[0] if kwargs.get("with_toc") else html)
        return html
    monkeypatch.setattr(reports, "report_body", inspect)
    page = TestClient(web.create_app()).get(f'/syntheses/{value["id"]}')
    assert page.status_code == 200 and len(captured) == 1
    assert str(captured[0]) in page.text
    assert "sl-export-form" in page.text and 'action="/syntheses/synthesis_fixture/export/pdf"' in page.text
    if scope == "convergence":
        assert 'class="sl-clamp"' in page.text and '<details class="block" id="bogen">' in page.text


def test_empty_list_and_missing_voices_do_not_invent_research():
    html, state = syntheses.syntheses([])
    assert state == "empty" and "sl-research-empty" in html
    value = record()
    value.update(statements=[], findings=[], gesamtbild="", positionierung="", arc_narrative="")
    html, state = syntheses.synthesis(value)
    assert state == "ready" and "sl-research-voices" not in html
    assert "claim-notice" not in html and "Completed" not in html
    html, state = syntheses.syntheses([record(), record("project")])
    assert state == "ready" and str(html).count("sl-research-card") == 2


@pytest.mark.parametrize("change", [{"status": None}, {"status": "unknown"}, {"scope": "custom"},
    {"status": []}, {"claim_posture": {"verified": "false", "counts": {}}},
    {"references": [{"text": "Unknown historical reference"}]},
    {"statements": [{"text": "No supplied persona"}]}, {"findings": ["Legacy shape"]},
    {"sections": [{"heading": "Missing citation identity", "citations": [{"quote": "Unknown source"}]}]}])
def test_unknown_or_malformed_full_records_fall_back(change):
    with pytest.raises(ValueError):
        syntheses.synthesis({**record(), **change})


@pytest.mark.parametrize("value", [None, [], {"id": "summary", "title": "Only a summary"}])
def test_summary_shapes_are_not_full_reports(value):
    with pytest.raises(ValueError):
        syntheses.synthesis(value)


def test_trust_claims_figures_and_titles_remain_escaped_and_recorded(monkeypatch):
    value = record("project")
    value["title"] = '<img src=x onerror="bad()">'
    value["claim_posture"] = {"verified": False, "counts": {"simulated": 1}, "prose_uncovered": True,
        "claims": [{"id": "claim1", "posture": "simulated", "refs": [{"kind": "external", "text": "Only this native qualification."}]}]}
    value["sections"][0]["figures"][0].update(kind="chart", caption="<script>bad()</script>", series=[{"label": "<iframe>", "value": 7}])
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    html, _ = syntheses.synthesis(value)
    assert "claim-notice--unverified" in html and "Only this native qualification." in html
    assert "<img" not in html and "<script>" not in html and "<iframe>" not in html
    assert "&lt;script&gt;" in html and "&lt;iframe&gt;" in html


def test_actual_mcp_synthesis_and_report_writes_preserve_native_sdk_envelopes(store, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_council, _tools_research
    original = FastMCP("original-synthesis")
    _tools_council.register_council(original)
    _tools_research.register_research(original)
    server = build_server()
    names = ("record_synthesis", "get_synthesis", "list_syntheses", "record_synthesis_outline", "record_synthesis_section")
    baseline = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    decorated = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in names:
        assert decorated[name].inputSchema == baseline[name].inputSchema
        assert decorated[name].outputSchema == baseline[name].outputSchema
        assert decorated[name].meta["ui"]["resourceUri"] == "ui://sonaloop/syntheses/v1"
    captured = []
    native_env = _tools_council._env
    def capture(name, *args, **kwargs):
        envelope = native_env(name, *args, **kwargs)
        captured.append((name, deepcopy(envelope)))
        return envelope
    monkeypatch.setattr(_tools_council, "_env", capture)
    monkeypatch.setattr(_tools_research, "_env", capture)
    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and captured[-1][0] == name
        expected_content, expected_structured = original._tool_manager._tools[name].fn_metadata.convert_result(captured[-1][1])
        assert result.content == expected_content
        assert result.structuredContent == expected_structured == json.loads(result.content[0].text)
        presentation = result.meta["sonaloop/presentation"]
        assert presentation["tool"] == name and presentation["state"] == "ready"
        assert presentation["component_id"] == "sonaloop.research.syntheses-view"
        assert presentation["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
        assert "sonaloop/presentation" not in result.content[0].text
        return result.structuredContent["data"], presentation["html"]
    project = services.create_research_project("Native synthesis fixture", "Isolated qualification", store=store)
    written, html = call("record_synthesis", title="A native finding", start_input="What did we learn?", project_id=project["id"],
        key="native-synthesis-fixture", payload={"gesamtbild": "The final handover context matters.",
            "findings": [{"kind": "recommendation", "text": "Keep the owner visible."}],
            "statements": [{"persona_id": "fixture_persona", "text": "Only during the pilot."}]})
    fetched, fetched_html = call("get_synthesis", synthesis_id=written["id"])
    assert all(written[key] == value for key, value in fetched.items())
    assert html == fetched_html and "Only during the pilot." in html
    listed, _ = call("list_syntheses")
    assert isinstance(listed, list) and listed[0]["id"] == written["id"]
    outline, html = call("record_synthesis_outline", project_id=project["id"], outline={
        "build_order_narrative": "The complete native report lead.",
        "sections": [{"heading": "Handover", "intent": "Keep evidence visible", "theme_tags": [], "source_study_ids": []}]},
        operation_id="native-report-fixture")
    assert outline["scope"] == "project" and outline["status"] == "in_progress"
    assert "not yet authored" in html
    full, html = call("record_synthesis_section", project_id=project["id"], report_id=outline["id"],
        section_id=outline["sections"][0]["id"], content={"markdown": "The exact authored section.\n\nFinal report qualifier.",
            "citations": [{"study_id": f'synthesis:{written["id"]}', "quote": "Only during the pilot."}]})
    assert full["sections"][0]["markdown"].endswith("Final report qualifier.")
    assert "Final report qualifier." in html and written["id"] in html
    assert [name for name, _ in captured] == list(names)

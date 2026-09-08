"""Shared survey contents reflect actual native aggregates without hidden reads."""
import asyncio
import json

import pytest

from sonaloop import artifacts, services
from sonaloop.ui_components import surveys


QUESTION = {"id": "q1", "text": "What helps the next shift?", "kind": "single", "options": ["Named owner", "Longer email"]}
SURVEY = {"id": "survey_fixture", "title": "Handover feedback", "intro": "A short anonymous survey.",
          "status": "draft", "questions": [QUESTION], "derived_from": []}
AGGREGATE = {"survey_id": "survey_fixture", "title": SURVEY["title"], "status": "open", "responses": 3,
             "respondents": 3, "questions": [{"question_id": "q1", "text": QUESTION["text"], "kind": "single",
                                              "answered": 3, "counts": {"Named owner": 2, "Longer email": 1}}]}


def test_instrument_does_not_invent_response_count_or_results():
    instrument, state = surveys.survey(SURVEY)
    assert state == "ready" and "Named owner" in instrument and "Longer email" in instrument
    assert "0 responses" not in instrument and "<meter" not in instrument
    actual, _ = surveys.survey({**SURVEY, "response_count": 0})
    assert "0 responses" in actual


def test_results_share_the_exact_product_question_body_and_quantities():
    from sonaloop.web.pages.surveys import _question_row
    result = AGGREGATE["questions"][0]
    content = surveys.question_content(QUESTION, result)
    assert content in _question_row(QUESTION, result, None)
    html, state = surveys.survey_results(AGGREGATE)
    assert content in html and state == "ready"
    assert 'value="0.666666666667"' in html and 'value="0.333333333333"' in html
    assert 'aria-label="Named owner"' in html
    assert str(surveys.count_row("Rare choice", 1, 10_000_000)).find('value="0.0000001"') > 0


def test_question_keeps_all_supplied_free_text_and_reports_native_truncation():
    question = {"id": "q2", "text": "Why?", "kind": "text"}
    answers = [f"Response {i}" for i in range(10)] + ["Long context " * 30 + "Only during training."]
    html = surveys.question_content(question, {"answered": 14, "answers": answers})
    assert str(html).count("<blockquote>") == len(answers)
    assert answers[-1] in html and "11 / 14" in html


def test_canonical_comparison_keeps_counts_sources_and_unknown_state_does_not_become_zero():
    counts = {term["term"]: 0 for term in artifacts.stance_terms()}
    counts["support"] = 2
    comparison = {"predicted": {"n": 2, "counts": counts, "refs": [{"kind": "council", "id": "c1", "anchor": "s1"}]},
                  "actual": {"n": 0, "counts": {term: 0 for term in counts}}}
    html = surveys.predicted_actual(comparison)
    assert "Council prediction (2)" in html and "Real answers (0)" in html
    assert "council:c1#s1" in html and "<table>" in html
    for counts in [{"future_scale": 0}, {}]:
        with pytest.raises(ValueError, match="comparison vocabulary"):
            surveys.predicted_actual({**comparison, "actual": {"n": 0, "counts": counts}})
    with pytest.raises(ValueError, match="native comparison"):
        surveys.predicted_actual({"actual": comparison["actual"]})


def test_survey_rendering_is_escaped_and_has_no_store_or_ref_resolution(monkeypatch):
    from sonaloop.storage import Store
    def forbidden(*args, **kwargs):
        pytest.fail("Survey rendering accessed native runtime data")
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    html, _ = surveys.survey({**SURVEY, "title": "<script>bad()</script>",
                              "derived_from": [{"kind": "council", "id": "c1", "quote": "<img src=x>"}]})
    assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html
    assert "council:c1" in html
    assert "2 responses processed" in surveys.imported({"survey_id": "s1", "imported": 2, "total_responses": 4})[0]


@pytest.mark.parametrize("count,total", [(-1, 2), (1, -2), (1.5, 3), (True, 3), (1, None)])
def test_invalid_counts_do_not_become_plausible_bars(count, total):
    with pytest.raises(ValueError, match="bounded"):
        surveys.count_row("Option", count, total)


def test_actual_native_survey_import_results_and_shared_product_route(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    project = services.create_research_project("Survey UI qualification", "Native temporary store", store=store)
    written = services.record_survey(project["id"], SURVEY["title"], [QUESTION], intro=SURVEY["intro"], store=store)
    survey = written["survey"]
    assert "0 responses" not in surveys.survey_write(written)[0]
    responses = [{"respondent_key": "fixture-1", "answers": [{"question_id": "q1", "value": "Named owner"}]},
                 {"respondent_key": "fixture-2", "answers": [{"question_id": "q1", "value": "Longer email"}]}]
    imported = services.import_survey_responses(survey["id"], responses, store=store)
    html, _ = surveys.imported(imported)
    assert "2 responses processed" in html and "2 responses" in html
    replay = services.import_survey_responses(survey["id"], responses, store=store)
    assert replay["total_responses"] == 2
    current = services.get_survey(survey["id"], store=store)
    assert "2 responses" in surveys.survey(current)[0]
    result = services.survey_results(survey["id"], store=store)
    assert result["questions"][0]["counts"] == {"Named owner": 1, "Longer email": 1}
    content = surveys.question_content(current["questions"][0], result["questions"][0])
    assert content in surveys.survey_results(result)[0]
    page = TestClient(web.create_app()).get(f"/surveys/{survey['id']}?lang=en").text
    assert str(content) in page
    assert str(surveys.response_summary(2)) in page
    assert surveys.surveys({"surveys": services.list_surveys(project["id"], store=store)})[1] == "ready"
    assert surveys.surveys({"surveys": []})[1] == "empty"


def test_native_survey_mcp_schemas_and_all_five_actual_ui_results(store):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server
    from sonaloop.mcp_server._tools_surveys import register_surveys
    original = FastMCP("original")
    register_surveys(original)
    server = build_server()
    declared = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for tool in asyncio.run(original.list_tools()):
        assert declared[tool.name].inputSchema == tool.inputSchema
        assert declared[tool.name].outputSchema == tool.outputSchema
    project = services.create_research_project("Native survey MCP", "Temporary qualification", store=store)
    results = []
    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and result.meta["sonaloop/presentation"]["tool"] == name
        assert result.meta["sonaloop/presentation"]["component_id"] == "sonaloop.research.surveys-view"
        # SDK-generated native text and structured envelope remain the same data;
        # private HTML never appears in either native output channel.
        assert json.loads(result.content[0].text) == result.structuredContent
        assert "sonaloop/presentation" not in result.content[0].text
        results.append(result)
        return result.structuredContent["data"]
    written = call("record_survey", project_id=project["id"], title=SURVEY["title"], questions=[QUESTION])
    identity = written["survey"]["id"]
    assert "0 responses" not in results[-1].meta["sonaloop/presentation"]["html"]
    assert call("get_survey", survey_id=identity)["response_count"] == 0
    assert call("list_surveys", project_id=project["id"])["surveys"][0]["id"] == identity
    batch = [{"respondent_key": "fixture-native", "answers": [{"question_id": "q1", "value": "Named owner"}]}]
    assert call("import_survey_responses", survey_id=identity, responses=batch)["total_responses"] == 1
    actual = call("survey_results", survey_id=identity)
    assert actual["responses"] == 1 and actual["questions"][0]["counts"]["Named owner"] == 1
    assert 'value="1"' in results[-1].meta["sonaloop/presentation"]["html"]


def test_native_repeated_multi_choice_remains_readable_without_false_proportion(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    project = services.create_research_project("Repeated selections", "Native accepted input", store=store)
    question = {**QUESTION, "kind": "multi"}
    survey = services.record_survey(project["id"], "Multi-choice survey", [question], store=store)["survey"]
    services.import_survey_responses(survey["id"], [
        {"respondent_key": "fixture-repeated", "answers": [{"question_id": "q1", "value": ["Named owner", "Named owner"]}]}], store=store)
    result = services.survey_results(survey["id"], store=store)
    assert result["questions"][0]["answered"] == 1
    assert result["questions"][0]["counts"]["Named owner"] == 2
    content = surveys.question_content(question, result["questions"][0])
    assert "Named owner: 2" in content and "answered count (2 / 1)" in content
    assert 'value="2"' not in content
    assert content in surveys.survey_results(result)[0]
    page = TestClient(web.create_app()).get(f"/surveys/{survey['id']}?lang=en")
    assert page.status_code == 200 and str(content) in page.text

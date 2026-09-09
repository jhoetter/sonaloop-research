"""Actual cohort-native results and read-only shared Product presentation."""
import asyncio
from copy import deepcopy
import hashlib
import html
import json
import os
from pathlib import Path
import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from conftest import create_persona
from test_cohort_integrity import _deepen, _product_preflight, _start
from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import cohort, cohort_preflight


TOOLS = {"evaluate_cohort_diversity": cohort.diversity, "record_cohort_critic": cohort.critic,
         "cohort_memory_depth": cohort.depth, "assess_coverage": cohort.coverage,
         "select_reaction_test_cohort": cohort.selection, "record_cohort_preflight": cohort_preflight.preflight,
         "get_cohort_preflight": cohort_preflight.preflight}


def forbidden(*args, **kwargs):
    pytest.fail("Cohort presentation attempted native writes, provider, media, file or network access")


@pytest.fixture(autouse=True)
def provider_denied(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_eval, _tools_personas, _tools_plan
    server = FastMCP("original-cohort")
    _tools_eval.register_eval(server)
    _tools_personas.register_personas(server)
    _tools_plan.register_plan(server)
    return server


@pytest.fixture
def examples(store):
    server, result = original_server(), []
    def call(tool, arguments, scenario):
        envelope = server._tool_manager._tools[tool].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        markup, state = TOOLS[tool](value)
        assert markup and state == "ready"
        result.append({"scenario": scenario, "tool": tool, "input": arguments, "value": value, "state": state})
        return value
    p1 = create_persona(store, "Cohort A", pains=["Supplier handoffs"], goals=["Maintain routines"])
    call("evaluate_cohort_diversity", {"persona_ids": [p1]}, "cohort-diversity-na")
    p2 = create_persona(store, "Cohort B", pains=["Supplier handoffs"], goals=["Maintain routines"])
    call("evaluate_cohort_diversity", {"persona_ids": [p1, p2]}, "cohort-diversity-duplicates")
    call("record_cohort_critic", {"verdict": {"outliers": [], "cohort_note": "No outliers reported."}}, "cohort-critic-green")
    call("record_cohort_critic", {"verdict": {"outliers": [{"persona_id": p2, "persona_name": "Cohort B",
         "dimension": "distinctiveness", "severity": 5, "reason": "Shares the same routine constraints."}],
         "cohort_note": "One recorded outlier."}}, "cohort-critic-outlier")
    call("cohort_memory_depth", {"persona_ids": [p1, p2]}, "cohort-depth-zero")
    project = services.start_project("Cohort fixture", "Understand routine choices", "Reaction Test", [],
                                     operation_id="cohort-ui-project", store=store)
    call("assess_coverage", {"project": project["id"]}, "cohort-coverage-empty")
    run = services.start_run(project["id"], operation_id="cohort-ui-run", store=store)
    _product_preflight(store, project["id"], run["run_id"])
    frame = services.run_step(run["run_id"], store=store)
    selection_args = {"project_id": project["id"], "persona_ids": [p1, p2],
        "selection_rationale": "Compare the existing routine perspectives.",
        "operation_id": "cohort-ui-selection", "dispatch_token": frame["dispatch_token"]}
    call("select_reaction_test_cohort", selection_args, "cohort-selected-not-checkpointed")
    call("select_reaction_test_cohort", selection_args, "cohort-selection-replayed")
    call("assess_coverage", {"project": project["id"], "job": "positioning"}, "cohort-coverage-declared")
    services.record_frame(project["id"], frame["step_id"], ["What would make a new workflow unnecessary?"],
        memory_refs=["memory:synthetic-context"], dispatch_token=frame["dispatch_token"], store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    representation = [{"persona_id": p1, "posture": "target", "rationale": "Existing operating role"},
                      {"persona_id": p2, "posture": "skeptical", "rationale": "Questions the added value"}]
    args = {"project_id": project["id"], "representation": representation, "dispatch_token": dispatch["dispatch_token"]}
    failed = call("record_cohort_preflight", args, "cohort-preflight-reselection")
    call("get_cohort_preflight", {"project_id": project["id"]}, "cohort-preflight-get")
    repair = services.run_step(run["run_id"], store=store)
    override = call("record_cohort_preflight", {**args, "dispatch_token": repair["dispatch_token"],
        "override_rationale": "Retain this explicit synthetic limitation for the inspection fixture."}, "cohort-preflight-override")
    assert override["status"] == "overridden"
    call("get_cohort_preflight", {"project_id": project["id"]}, "cohort-preflight-limitations")
    call("get_cohort_preflight", {"project_id": project["id"], "version_id": failed["id"]}, "cohort-preflight-historical")
    # Native pass from explicitly seeded, independent synthetic context. The
    # native gate runs; this does not claim these fixtures are observed people.
    q1 = create_persona(store, "Independent A", pains=["Supplier reply delays"], goals=["Keep weekly routines"])
    q2 = create_persona(store, "Independent B", pains=["Invoice dates"], goals=["Review delivery records"])
    _deepen(store, q1, prefix="cohort_ui_a"); _deepen(store, q2, prefix="cohort_ui_b")
    passed_project, _, passed_dispatch, _ = _start(store, "ui-pass", [q1, q2])
    call("cohort_memory_depth", {"persona_ids": [q1, q2]}, "cohort-depth-deep")
    passed = call("record_cohort_preflight", {"project_id": passed_project["id"], "representation": [
        {"persona_id": q1, "posture": "target", "rationale": "Independent operating role"},
        {"persona_id": q2, "posture": "indifferent", "rationale": "Existing routine is sufficient",
         "basis_quote": "existing manual checklist is sufficient",
         "evidence_refs": [{"kind": "evidence", "id": "evidence_cohort_ui_b"}]}],
        "dispatch_token": passed_dispatch["dispatch_token"]}, "cohort-preflight-pass")
    assert passed["status"] == "pass"
    return result


def case(examples, scenario):
    return next(item["value"] for item in examples if item["scenario"] == scenario)


def test_actual_seven_native_shapes_and_private_fixture_export(examples, tmp_path, store):
    assert {item["tool"] for item in examples} == set(TOOLS)
    na = case(examples, "cohort-diversity-na")
    assert na["status"] == "na" and na["green"] is True
    assert not any(row["id"] == na["id"] for row in store.list_eval_reports())
    assert case(examples, "cohort-diversity-duplicates")["duplicate_pairs"]
    assert case(examples, "cohort-coverage-empty")["panel_size"] == 0
    path = Path(os.environ.get("RESEARCH_COHORT_FIXTURE_PATH", tmp_path / "cohort-fixtures.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    sizes = {item["scenario"]: len(json.dumps({"name": item["tool"], "value": item["value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for item in examples}
    print("Native cohort fixture path:", path, "sizes:", sizes)


def test_pure_views_do_not_lookup_reassess_freshness_or_fetch(examples, monkeypatch):
    from sonaloop import cohort_integrity, evaluation
    from sonaloop.web import _components
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(cohort_integrity, "preflight_satisfies_project", forbidden)
        patch.setattr(cohort_integrity, "evaluate_cohort", forbidden)
        patch.setattr(evaluation, "evaluate_cohort_diversity", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "exists", forbidden)
        for name in TOOLS:
            patch.setattr(services, name, forbidden)
        for item in examples:
            TOOLS[item["tool"]](item["value"])
    assert examples == before


def test_selection_status_is_exact_and_dispatch_grants_are_not_presented(examples):
    value = deepcopy(case(examples, "cohort-selected-not-checkpointed"))
    secret = "opaque-execution-grant-never-display"
    value["operation_id"] = secret
    value["dispatch"]["dispatch_token"] = secret
    value["next"]["arguments"] = {"confirmation_token": secret}
    markup, _ = cohort.selection(value)
    assert secret not in markup and "<dt>gate_passed</dt><dd>false</dd>" in markup
    assert "<dt>checkpointed</dt><dd>false</dd>" in markup
    assert value["selection_rationale"] in markup and "<button" not in markup and "<a " not in markup


def test_recorded_pass_is_not_reclassified_and_getter_history_is_real(examples):
    value = deepcopy(case(examples, "cohort-preflight-pass"))
    value["depth"]["totals"]["thin"] = 2
    value["evaluated_at"] = "1999-01-01T00:00:00Z"
    markup, _ = cohort_preflight.preflight(value)
    assert "<dt>status</dt><dd>pass</dd>" in markup and "1999-01-01" in markup
    assert "<dt>thin</dt><dd>2</dd>" in markup
    history = case(examples, "cohort-preflight-historical")
    assert history["version"] == 1 and len(history["history"]) == 2
    markup, _ = cohort_preflight.preflight(history)
    assert all(item["id"] in markup for item in history["history"])
    assert "<dt>status</dt><dd>needs_reselection</dd>" in markup
    override = case(examples, "cohort-preflight-limitations")
    assert override["limitations"][0]["rationale"] in cohort_preflight.preflight(override)[0]


def test_complete_native_preflight_fields_and_escaped_provenance_are_retained(examples):
    value = deepcopy(case(examples, "cohort-preflight-pass"))
    hostile = '<img src=x onerror="bad()"><script>Complete provenance</script>'
    value["depth"]["personas"][0]["source_provenance"]["profile"] = {"grounding": {"quote": hostile}}
    value["representation"]["declarations"][1]["basis_quote"] += hostile
    value["leakage"]["semantic"].update(provided=True, feature_version="authored-fixture", model_id="no-provider",
        scores=[{"persona_id": value["cohort_ids"][0], "input_digest": "supplied-digest", "score": 0}])
    markup, _ = cohort_preflight.preflight(value)
    for expected in ("no-provider", "supplied-digest", "<dt>score</dt><dd>0</dd>", "independent_facts",
                     "shared_token_count", "frame_hypotheses_digest", "evidence_cohort_ui_b"):
        assert expected in markup
    assert html.escape(hostile) in markup and "<img" not in markup and "<script" not in markup
    assert "<pre" not in markup and "<details open" not in markup


def test_empty_sections_and_disclosures_are_omitted_and_provenance_grants_stay_private(examples):
    from sonaloop.ui_components.cohort_rows import t
    for item in examples:
        markup, _ = TOOLS[item["tool"]](item["value"])
        assert "<ul></ul>" not in markup and '<dl class="sl-research-fields"></dl>' not in markup
    na = cohort.diversity(case(examples, "cohort-diversity-na"))[0]
    green = cohort.critic(case(examples, "cohort-critic-green"))[0]
    assert f'<h3>{t("rcg_duplicate_pairs")}</h3>' not in na
    assert f'<h3>{t("rcg_outliers")}</h3>' not in green
    value = deepcopy(case(examples, "cohort-preflight-pass"))
    value.update(history=[], limitations=[])
    secret = "fixture-authority-must-not-appear"
    profile = value["depth"]["personas"][0]["source_provenance"]["profile"]
    profile["recorded_source"] = "Preserve this supplied source description"
    profile["credentials"] = {key: secret for key in ("dispatch_token", "approval_token", "access_token", "refresh_token", "preview_token")}
    before = deepcopy(value)
    markup, _ = cohort_preflight.preflight(value)
    assert secret not in markup and "Preserve this supplied source description" in markup
    assert f'<summary>{t("rcg_history")}</summary>' not in markup
    assert f'<summary>{t("rcg_limitations")}</summary>' not in markup
    assert value == before


@pytest.mark.parametrize("scenario,mutate", [
    ("cohort-diversity-na", lambda v: v.update(green="true")),
    ("cohort-diversity-duplicates", lambda v: v["metrics"].update(mean_pairwise_similarity=float("nan"))),
    ("cohort-critic-outlier", lambda v: v["outliers"][0].update(severity=True)),
    ("cohort-depth-zero", lambda v: v.update(facts=-1)),
    ("cohort-coverage-declared", lambda v: v["dimensions"][0].update(counts={"bad": False})),
    ("cohort-selected-not-checkpointed", lambda v: v["dispatch"].update(checkpointed="false")),
    ("cohort-preflight-pass", lambda v: v["representation"].update(satisfied=1)),
    ("cohort-preflight-pass", lambda v: v["depth"]["personas"][0]["depth"].update(independent_facts=-1)),
    ("cohort-preflight-pass", lambda v: v.update(schema="unknown")),
])
def test_malformed_fields_fall_back_without_deriving_verdicts(examples, scenario, mutate):
    row = next(item for item in examples if item["scenario"] == scenario)
    value = deepcopy(row["value"])
    mutate(value)
    with pytest.raises(ValueError):
        TOOLS[row["tool"]](value)


def test_existing_product_integrity_uses_prepared_shared_body_and_unchanged_structure(examples, store, monkeypatch):
    from sonaloop.web import _cohort_integrity_view as product
    value = case(examples, "cohort-preflight-pass")
    project = store.get_research_project(value["project_id"])
    seen = []
    native = cohort_preflight.integrity_content
    def observe(*args, **kwargs):
        markup = native(*args, **kwargs)
        seen.append((deepcopy(kwargs["prepared"]), markup))
        return markup
    monkeypatch.setattr(cohort_preflight, "integrity_content", observe)
    markup = product.render_cohort_integrity(project, store, embedded=True)
    assert markup and markup == seen[-1][1]
    assert seen[-1][0]["status"] == "pass" and seen[-1][0]["stale"] is False
    assert 'class="sl-integrity sl-integrity--cohort sl-integrity--embedded"' in markup
    assert 'id="cohort-integrity"' in markup and 'class="sl-integrity-metrics"' in markup
    assert 'class="sl-integrity-list"' in markup and 'class="sl-integrity-summary"' in markup
    assert value["policy_version"] in markup and "Independent A" in markup
    page = TestClient(web.create_app()).get(f'/jobs/{project["id"]}')
    assert page.status_code == 200 and markup in page.text
    changed = deepcopy(project)
    changed["goal"] += " Changed stimulus"
    stale = product.render_cohort_integrity(changed, store)
    assert stale and seen[-1][0]["stale"] is True and seen[-1][0]["status"] == "stale"
    # Historical/passive status is unaffected by the Product's current check.
    assert "<dt>status</dt><dd>pass</dd>" in cohort_preflight.preflight(value)[0]


def test_readonly_product_routes_show_stored_reports_and_actual_project_values(examples, store, monkeypatch):
    from sonaloop.web.pages import _cohort_results as product
    app = FastAPI()
    product.register_cohort_results(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    for name in ("evaluate_cohort_diversity", "record_cohort_critic", "select_reaction_test_cohort", "record_cohort_preflight"):
        monkeypatch.setattr(services, name, forbidden)
    client = TestClient(app)
    reports = client.get("/cohorts")
    assert reports.status_code == 200
    assert cohort.diversity(case(examples, "cohort-diversity-duplicates"))[0] in reports.text
    assert cohort.critic(case(examples, "cohort-critic-outlier"))[0] in reports.text
    assert case(examples, "cohort-diversity-na")["id"] not in reports.text
    historical = case(examples, "cohort-preflight-historical")
    response = client.get(f'/jobs/{historical["project_id"]}/cohort?version_id={historical["id"]}')
    assert response.status_code == 200 and cohort_preflight.preflight(historical)[0] in response.text
    selection = case(examples, "cohort-selected-not-checkpointed")
    assert cohort.selection_content(selection["persona_ids"], selection["selection_rationale"]) in response.text


def test_empty_project_never_substitutes_workspace_depth(store, monkeypatch):
    from sonaloop.web.pages import _cohort_results as product
    create_persona(store, "Unrelated workspace persona")
    project = services.start_project("Empty panel", "Explicit empty cohort", persona_ids=[], store=store)
    app = FastAPI()
    product.register_cohort_results(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    monkeypatch.setattr(services, "cohort_memory_depth", forbidden)
    response = TestClient(app).get(f'/jobs/{project["id"]}/cohort')
    assert response.status_code == 200 and "<dt>panel_size</dt><dd>0</dd>" in response.text
    assert "Unrelated workspace persona" not in response.text


@pytest.mark.parametrize("project_id", ["missing-project", "foreign-project"])
def test_missing_or_foreign_project_stops_before_cohort_reads(project_id, monkeypatch):
    from sonaloop.web.pages import _cohort_results as product
    reads = []
    class ScopedStore:
        def get_research_project_for_active_workspace(self, identifier):
            reads.append(identifier)
            return None

        def get_research_project(self, identifier):
            pytest.fail("Cohort page bypassed the active-workspace project boundary")

    app = FastAPI()
    product.register_cohort_results(app)
    monkeypatch.setattr(product, "Store", ScopedStore)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    for name in ("get_cohort_preflight", "cohort_memory_depth", "assess_coverage"):
        monkeypatch.setattr(services, name, forbidden)
    response = TestClient(app).get(f"/jobs/{project_id}/cohort")
    assert response.status_code == 404 and reads == [project_id]


def test_actual_fastmcp_seven_schemas_and_single_execution(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_eval, _tools_personas, _tools_plan
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/cohorts/v1"
    envelopes = []
    for module in (_tools_eval, _tools_personas, _tools_plan):
        env = module._env
        def capture(*args, _env=env, **kwargs):
            value = _env(*args, **kwargs)
            envelopes.append(deepcopy(value))
            return value
        monkeypatch.setattr(module, "_env", capture)
    for name in TOOLS:
        row = next(item for item in examples if item["tool"] == name)
        calls, native = [], getattr(services, name)
        def counted(*args, **kwargs):
            value = native(*args, **kwargs)
            calls.append(deepcopy(value))
            return value
        with monkeypatch.context() as patch:
            patch.setattr(services, name, counted)
            before = len(envelopes)
            result = asyncio.run(server.call_tool(name, row["input"]))
        assert not result.isError and len(calls) == 1 and len(envelopes) == before + 1
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1])
        assert result.content == text and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["state"] == "ready"
        assert result.meta["sonaloop/presentation"]["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()

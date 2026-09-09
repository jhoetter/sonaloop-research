"""Shared native Session traces and funnel quantities stay readable without media."""
import asyncio
import base64
from copy import deepcopy
import json

import pytest

from sonaloop import artifacts, services
from sonaloop.ui_components import sessions, session_funnels, session_steps


STEP = {"index": 0, "action": {"type": "look", "target": "Owner", "detail": "Read the handover panel"},
        "monologue": "I can find the person responsible.", "state": {"screen": "Owner panel"},
        "friction": {"level": "none", "note": ""}, "verdict": {"would_continue": True, "reason": "Owner is visible"}}
SESSION = {"id": "session_fixture", "persona_id": "persona_fixture",
           "subject": {"kind": "flow", "id": "flow_fixture", "label": "Handover"}, "fidelity": "artifact",
           "date": "2026-09-09", "steps": [STEP], "statements": [],
           "outcome": {"completed": True, "dropoff_step": None, "summary": "Found the owner", "predicted_behaviors": []}}
FUNNEL = {"subject": {"kind": "flow", "key": "flow_fixture"}, "sessions": 3, "completed": 1,
          "rows": [{"step": 0, "entered": 3, "continued": 2, "dropped": 1, "drop_reasons": ["No owner was named"]},
                   {"step": 1, "entered": 2, "continued": 1, "dropped": 1, "drop_reasons": ["The next action was unclear"]}]}


def test_product_step_uses_the_same_prepared_core_and_preserves_resolved_media(monkeypatch):
    from sonaloop.web.pages import sessions as page
    calls = []
    def capture(row, **kwargs):
        calls.append(row)
        return session_steps.step_content(row, **kwargs)
    monkeypatch.setattr(page, "step_content", capture)
    monkeypatch.setattr(page, "_screenshot_url", lambda *_: "/sessions-files/fixture/step.png")
    step = deepcopy(STEP)
    step["state"]["screenshot"] = "step.png"
    html = page._step_html(SESSION, step)
    assert len(calls) == 1 and html == session_steps.step_content(calls[0])
    assert '<img class="sess-shot" src="/sessions-files/fixture/step.png"' in html
    assert STEP["monologue"] in html and STEP["action"]["target"] in html


def test_passive_trace_retains_full_text_and_explicit_references_without_store_or_media(monkeypatch):
    from sonaloop.storage import Store
    from sonaloop.web.pages import sessions as page
    def forbidden(*args, **kwargs):
        pytest.fail("Passive Session accessed native runtime data or media")
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    for name in ("_screenshot_url", "_artifact_screen", "_focus_crop", "_persona_chip", "_subject_link"):
        monkeypatch.setattr(page, name, forbidden)
    record = deepcopy(SESSION)
    record["steps"][0]["state"].update(screenshot="private/actual-step.png", url="https://example.test/owner",
        focus={"x": 10, "y": 20, "width": 30, "height": 40, "label": "Owner hypothesis"})
    record["steps"][0]["monologue"] = "Detailed context. " * 100 + "Only applies during onboarding."
    html, state = sessions.session(record)
    assert state == "ready" and record["steps"][0]["monologue"] in html
    for value in ("private/actual-step.png", "https://example.test/owner", "Owner hypothesis", "x: 10%", "not eye-tracking"):
        assert value in html
    assert "screenshot pixels are not displayed" in html and "<img" not in html and "href=" not in html
    assert "No screen saved" not in html and "Grounding" not in html, "Missing native verification is not guessed"


def test_dropoff_keeps_step_reason_and_distinct_outcome_summary():
    record = deepcopy(SESSION)
    record["outcome"].update(completed=False, dropoff_step=0, summary="The handover was abandoned")
    record["steps"][0]["verdict"] = {"would_continue": False, "reason": "The owner was missing"}
    html, _ = sessions.session(record)
    assert "Dropped at step 0" in html and "The owner was missing" in html and "The handover was abandoned" in html


@pytest.mark.parametrize("mutate", [lambda r: r["outcome"].pop("completed"),
    lambda r: r["outcome"].update(completed=False, dropoff_step=None),
    lambda r: r["outcome"].update(dropoff_step=0), lambda r: r["steps"][0].update(index=True)])
def test_unknown_or_contradictory_native_outcomes_do_not_become_success_or_drop(mutate):
    value = deepcopy(SESSION)
    mutate(value)
    with pytest.raises(ValueError):
        sessions.session(value)


def test_prediction_body_is_shared_and_keeps_native_likelihood_sources_and_step(monkeypatch):
    from sonaloop.web.pages.sessions import _predicted_behaviors_html
    value = {"action": "Ask the owner", "trigger": "Next shift", "step": 0, "likelihood": {"value": .7, "label": "likely"},
             "refs": [{"kind": "session", "id": "session_fixture", "anchor": "step:0", "quote": "Only during onboarding."}]}
    passive = sessions.predictions([value])
    assert "70% · likely" in passive and "Step 0" in passive
    assert "session:session_fixture#step:0" in passive and "Only during onboarding." in passive
    legacy = sessions.predictions([{**value, "likelihood": "likely"}])
    assert "70% · likely" in legacy
    product = _predicted_behaviors_html([{**value, "refs": []}], None)
    assert "Ask the owner" in product and "Next shift" in product and "70 %" in product
    assert "Unknown token" in sessions.predictions([{**value, "likelihood": "Unknown token"}])


def test_legacy_prototype_timeline_keeps_authored_steps_without_invented_pixel_paths():
    reaction = {"verdict": "This helps during onboarding.", "liked": ["Named owner"], "friction": ["Missing next action"],
                "timeline": [{"step": 4, "action": "Read the summary", "monolog": "What should I do next?", "beobachtung": "A summary panel"}]}
    record = {"id": "ps_fixture", "persona_id": "persona_fixture", "prototype_id": "prototype_fixture",
              "reaction": reaction, "grounded_verified": False, "prototype_version": "v0.7",
              "observed_state_refs": ["Saved owner panel"]}
    html, state = sessions.prototype_session_write({"prototype_session": record})
    assert state == "ready" and "This helps during onboarding." in html
    for text in ("Named owner", "Missing next action", "Read the summary", "What should I do next?", "A summary panel", "Recorded version", "v0.7", "Saved owner panel"):
        assert text in html
    assert "would drop" not in html and "step-4.png" not in html and "<img" not in html
    assert session_steps.timeline_steps(reaction["timeline"])[0]["index"] == 4


def test_native_funnel_counts_reasons_and_empty_state_are_not_recomputed():
    from sonaloop.web.pages import sessions as page
    html, state = session_funnels.funnel(FUNNEL)
    product = page._funnel_html(FUNNEL)
    assert state == "ready"
    for text in ("Step 0", "Step 1", "No owner was named", "The next action was unclear", "3 entered · 1 dropped"):
        assert text in html and text in product
    assert 'value="0.666666666667"' in html and 'value="0.5"' in html
    assert "Completed: 1 / 3" in html
    assert session_funnels.funnel({**FUNNEL, "rows": [], "sessions": 0, "completed": 0})[1] == "empty"
    invalid = deepcopy(FUNNEL)
    invalid["rows"][0]["dropped"] = 2
    with pytest.raises(ValueError, match="counts"):
        session_funnels.funnel(invalid)


def test_untrusted_step_and_result_values_remain_escaped():
    value = deepcopy(SESSION)
    value["steps"][0]["monologue"] = "<script>bad()</script>"
    value["steps"][0]["state"]["screenshot"] = '<img src=x onerror="bad()">'
    html, _ = sessions.session(value)
    assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html


def test_actual_native_session_tools_preserve_schemas_and_sdk_envelopes(store, monkeypatch, tmp_path):
    from mcp.server.fastmcp import FastMCP
    from conftest import make_profile
    from sonaloop import prototypes
    from sonaloop.mcp_server import build_server, _tools_usability, _tools_prototypes, _tools_flows
    original = FastMCP("original-sessions")
    for module, register in ((_tools_usability, "register_usability"), (_tools_prototypes, "register_prototypes"), (_tools_flows, "register_flows")):
        getattr(module, register)(original)
    server = build_server()
    names = {"record_usability_session", "get_usability_session", "list_usability_sessions", "record_prototype_session", "get_session_funnel", "flow_funnel"}
    original_tools = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    actual_tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in names:
        assert actual_tools[name].inputSchema == original_tools[name].inputSchema
        assert actual_tools[name].outputSchema == original_tools[name].outputSchema
    envelopes = []
    def capture(native):
        def wrapped(name, *args, **kwargs):
            value = native(name, *args, **kwargs)
            envelopes.append((name, deepcopy(value)))
            return value
        return wrapped
    for module in (_tools_usability, _tools_prototypes, _tools_flows):
        monkeypatch.setattr(module, "_env", capture(module._env))
    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and envelopes[-1][0] == name
        native_content, native_structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1][1])
        assert result.content == native_content and result.structuredContent == native_structured
        assert json.loads(result.content[0].text) == native_structured
        assert result.meta["sonaloop/presentation"]["component_id"] == "sonaloop.research.sessions-view"
        return result.structuredContent["data"], result.meta["sonaloop/presentation"]["html"]
    project = services.create_research_project("Session UI", "Isolated native results", store=store)
    persona = services.record_persona("Synthetic session reviewer", make_profile("Fixture reviewer"), generate_avatar=False, store=store)
    # Existing flow service needs an admitted screenshot reference. Its test-only
    # bytes stay in the temporary native asset store and are never fetched by UI.
    image = tmp_path / "screen.png"
    image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
    asset = services.attach_asset(project["id"], path=str(image), title="Owner screen", store=store)
    flow = services.define_flow(project["id"], "Handover", [{"asset_id": asset["id"]}], store=store)
    data, html = call("record_usability_session", persona_id=persona["id"], subject={"kind": "flow", "id": flow["id"], "label": "Handover"},
                      fidelity="artifact", date="2026-09-09", steps=[STEP], outcome=SESSION["outcome"], project_id=project["id"], key="fixture-walk")
    identity = data["usability_session"]["id"]
    assert STEP["monologue"] in html
    assert call("get_usability_session", session_id=identity)[0]["id"] == identity
    assert call("list_usability_sessions", project_id=project["id"])[0]["sessions"][0]["id"] == identity
    assert call("get_session_funnel", subject_kind="flow", subject_id_or_url=flow["id"])[0]["completed"] == 1
    assert call("flow_funnel", project_id=project["id"], flow_id=flow["id"])[0]["flow"]["id"] == flow["id"]
    prototype = prototypes.register_prototype("fixture-prototype", "Fixture prototype", "prototypes/fixture", project_id=project["id"], store=store)
    reaction = {"verdict": "The owner is clear", "observed_state_refs": ["Owner panel"], "steps": [STEP]}
    recorded, html = call("record_prototype_session", persona_id=persona["id"], prototype_id=prototype["id"], session_id="fixture-no-browser",
                          date="2026-09-09", reaction=reaction, key="fixture-reaction")
    assert recorded["grounded_verified"] is False and "The owner is clear" in html
    assert {name for name, _ in envelopes} == names

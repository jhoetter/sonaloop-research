"""Native Persona records, passive purity and the actual Product read adapter."""
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
from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import persona_records as views
from sonaloop.ui_components import persona_record_rows as rows


TOOLS = {"record_persona_revision": views.revision, "list_persona_revisions": views.revisions,
         "record_persona_voice_check": views.voice_check, "attach_evidence": views.evidence}


def forbidden(*args, **kwargs):
    pytest.fail("Persona record presentation attempted native, provider, media or network access")


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
    from sonaloop.mcp_server import _tools_eval, _tools_personas
    server = FastMCP("original-persona-records")
    _tools_eval.register_eval(server)
    _tools_personas.register_personas(server)
    return server


@pytest.fixture
def examples(store):
    server, result = original_server(), []
    pid = create_persona(store, "Records fixture")
    def call(tool, arguments, scenario):
        envelope = server._tool_manager._tools[tool].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        markup, state = TOOLS[tool](value)
        assert markup and state in {"ready", "empty"}
        result.append({"scenario": scenario, "tool": tool, "input": arguments, "value": value, "state": state})
        return value
    source = call("attach_evidence", {"persona_id": pid, "source_type": "url",
        "content_or_path": "https://example.invalid/interview", "notes": "Supplied interview location."}, "records-source-url")
    call("attach_evidence", {"persona_id": pid, "source_type": "document",
        "content_or_path": "notes/field-interview.md"}, "records-source-path")
    call("attach_evidence", {"persona_id": pid, "source_type": "note",
        "content_or_path": "The weekly checklist remains useful.\nNo new process was requested.", "notes": ""}, "records-source-text")
    call("list_persona_revisions", {"persona_id": pid}, "records-revisions-empty")
    call("record_persona_revision", {"persona_id": pid, "revision": {
        "effective_on": "2026-06-02", "rationale": "A supplied interview describes the changed routine.",
        "changes": {"goals_add": ["Review the checklist weekly"], "goals_remove": ["Records fixture goal"],
                    "constraints_add": ["Friday review slot"], "constraints_remove": ["limited time"],
                    "pains_add": ["Late supplier replies"], "pains_remove": ["Old manual filing"],
                    "tools_add": ["Paper checklist"], "tools_remove": ["Unused spreadsheet"],
                    "personality": {"working_style": "Keeps a weekly list", "communication_style": "Asks concrete questions",
                                    "risk_tolerance": "Cautious with workflow changes", "character_notes": "Prefers familiar routines"},
                    "notes": "Only the reported revision is presented."},
        "refs": [{"kind": "evidence", "id": source["id"]}]}}, "records-revision-changes")
    call("record_persona_revision", {"persona_id": pid, "revision": {
        "effective_on": "2026-06-03", "rationale": "No additional identity change is supported.",
        "changes": {}, "refs": []}}, "records-revision-no-change")
    call("list_persona_revisions", {"persona_id": pid}, "records-revisions-history")
    scores = {key: 4 for key in ("authenticity", "register_match", "knowledge_grounding", "attribution_separation")}
    call("record_persona_voice_check", {"persona_id": pid, "text": "I will keep my familiar checklist.",
        "verdict": {"scores": scores, "issues": [], "rewrite": None}}, "records-voice-green")
    call("record_persona_voice_check", {"persona_id": pid, "text": "This information architecture increases cognitive load.",
        "verdict": {"scores": {**scores, "authenticity": 0, "register_match": 1},
                    "issues": [{"kind": "analyst_register", "detail": "The wording diagnoses a design instead of describing a routine."}],
                    "rewrite": "Where should I start? I cannot find my checklist."}}, "records-voice-red")
    return result


def case(examples, scenario):
    return next(item["value"] for item in examples if item["scenario"] == scenario)


def test_actual_four_native_shapes_and_fixture_export(examples, tmp_path, store):
    assert {item["tool"] for item in examples} == set(TOOLS)
    assert case(examples, "records-revisions-empty") == []
    history = case(examples, "records-revisions-history")
    assert len(history) == 2 and history[0]["changes"]["tools_add"] == ["Paper checklist"]
    assert case(examples, "records-voice-green")["green"] is True
    assert case(examples, "records-voice-red")["green"] is False
    for item in (row for row in examples if row["tool"] == "record_persona_voice_check"):
        assert item["input"]["text"] not in json.dumps(item["value"])
        assert item["value"]["text_sha256"] == hashlib.sha256(item["input"]["text"].encode()).hexdigest()
        assert item["value"] in store.list_eval_reports(item["value"]["persona_id"])
    target = Path(os.environ.get("RESEARCH_PERSONA_RECORD_FIXTURE_PATH", tmp_path / "persona-records.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    sizes = {item["scenario"]: len(json.dumps({"name": item["tool"], "value": item["value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for item in examples}
    assert max(sizes.values()) <= 8192
    print("Native Persona record fixtures:", target, "sizes:", sizes)


def test_pure_bodies_never_resolve_revise_check_or_read_sources(examples, monkeypatch):
    from sonaloop import config
    from sonaloop.web import _components
    original = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        for name in (*TOOLS, "validate_persona_output", "prepare_persona_agent_context", "get_persona_soul"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            TOOLS[item["tool"]](item["value"])
    assert examples == original


def test_full_revision_changes_and_literal_reference_are_shared(examples):
    value = case(examples, "records-revision-changes")
    markup, state = views.revision(value)
    assert state == "ready" and rows.revision_content(value) in markup
    for key, change in value["changes"].items():
        items = change.values() if isinstance(change, dict) else change if isinstance(change, list) else [change]
        assert all(html.escape(item) in markup for item in items), key
    assert f'evidence:{value["refs"][0]["id"]}' in markup
    assert value["effective_on"] in markup and value["rationale"] in markup


def test_voice_status_is_supplied_and_candidate_is_not_reconstructed(examples):
    value = deepcopy(case(examples, "records-voice-red"))
    value["green"] = True  # A renderer must not re-run the native verdict rules.
    markup, _ = views.voice_check(value)
    assert "<dd>true</dd>" in markup and "0 / 5" in markup
    assert all(signal["phrase"] in markup for signal in value["deterministic_signals"])
    assert value["rewrite"] in markup and value["text_sha256"] in markup
    candidate = next(item["input"]["text"] for item in examples if item["scenario"] == "records-voice-red")
    assert candidate not in markup and rows.voice_content(value) in markup


def test_untrusted_prose_urls_and_known_grants_never_become_actions(examples):
    hostile = '<script>alert("x")</script><img src="file:///private.png" onerror="run()">'
    secret = "opaque-execution-grant"
    for scenario, render, field in (("records-source-url", views.evidence, "content_or_path"),
                                    ("records-revision-changes", views.revision, "rationale"),
                                    ("records-voice-red", views.voice_check, "rewrite")):
        value = deepcopy(case(examples, scenario))
        value[field] = hostile * 30
        for key in ("dispatch_token", "confirmation_token", "approval_token", "access_token", "refresh_token", "preview_token", "execution_grant"):
            value[key] = secret
        value["next"] = {"tool": "delete_persona", "arguments": {"confirmation_token": secret}}
        markup, _ = render(value)
        assert html.escape(hostile) * 30 in markup and secret not in markup
        assert all(tag not in markup for tag in ("<script", "<img", "<a ", "<button", "<form"))
    markup, _ = views.evidence(case(examples, "records-source-url"))
    assert "https://example.invalid/interview" in markup and "href=" not in markup


@pytest.mark.parametrize("scenario,field,bad", [
    ("records-revision-changes", "changes", {"unknown_change": ["not native"]}),
    ("records-revision-changes", "changes", {"goals_add": "not a list"}),
    ("records-revision-changes", "refs", [{"kind": "persona", "id": "wrong-kind"}]),
    ("records-voice-red", "scores", {"authenticity": True}),
    ("records-voice-red", "green", "false"),
    ("records-voice-red", "issues", ["not a recorded issue"]),
    ("records-voice-red", "text_sha256", "g" * 64),
    ("records-source-text", "notes", {}),
    ("records-source-text", "persona_id", None),
])
def test_malformed_native_records_fail_before_presentation(examples, scenario, field, bad):
    item = next(row for row in examples if row["scenario"] == scenario)
    value = deepcopy(item["value"])
    value[field] = bad
    with pytest.raises(ValueError):
        TOOLS[item["tool"]](value)


def test_empty_results_and_optional_sections_are_explicit(examples):
    markup, state = views.revisions([])
    assert state == "empty" and "sl-research-empty" in markup and "<h2" not in markup
    for scenario, render in (("records-revision-no-change", views.revision), ("records-voice-green", views.voice_check),
                              ("records-source-path", views.evidence)):
        markup, _ = render(case(examples, scenario))
        assert "<ul></ul>" not in markup and "<dl class=\"sl-research-fields\"></dl>" not in markup
        assert "<h3></h3>" not in markup


def product_client(monkeypatch):
    from sonaloop.web.pages import _persona_records as product
    app = FastAPI()
    product.register_persona_records(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    return TestClient(app)


def test_product_reads_stored_scoped_records_and_reuses_exact_bodies(examples, store, monkeypatch):
    pid = case(examples, "records-voice-green")["persona_id"]
    other = create_persona(store, "Other records owner")
    services.attach_evidence(other, "note", "Foreign source must stay out", store=store)
    store.insert_eval_report({"id": "other-report-kind", "persona_id": pid, "kind": "unrelated_eval",
        "green": True, "created_at": "2026-06-01", "content": "Unrelated report must stay out"})
    store.commit()
    before = list(store.conn.iterdump())
    for name in (*TOOLS, "get_persona", "get_persona_soul", "prepare_persona_agent_context"):
        monkeypatch.setattr(services, name, forbidden)
    response = product_client(monkeypatch).get(f"/personas/{pid}/records")
    assert response.status_code == 200
    for item in examples:
        if item["tool"] != "list_persona_revisions":
            assert TOOLS[item["tool"]](item["value"])[0] in response.text
    assert "Foreign source must stay out" not in response.text and "Unrelated report must stay out" not in response.text
    assert list(store.conn.iterdump()) == before


def test_product_missing_persona_does_not_query_unscoped_history(monkeypatch):
    for name in ("list_persona_revisions", "list_evidence", "list_eval_reports"):
        monkeypatch.setattr(Store, name, forbidden)
    response = product_client(monkeypatch).get("/personas/unknown-persona/records")
    assert response.status_code == 404 and "sl-research-persona-record" not in response.text


def test_product_bad_stored_record_does_not_hide_other_sources(examples, store, monkeypatch):
    pid = case(examples, "records-voice-green")["persona_id"]
    broken = deepcopy(case(examples, "records-voice-green"))
    broken.update(id="broken-legacy-voice", scores={})
    store.insert_eval_report(broken)
    store.commit()
    response = product_client(monkeypatch).get(f"/personas/{pid}/records")
    assert response.status_code == 200 and case(examples, "records-source-text")["content_or_path"] in response.text
    assert views.voice_check(case(examples, "records-voice-green"))[0] in response.text


def test_real_registered_product_route(examples):
    pid = case(examples, "records-voice-green")["persona_id"]
    response = TestClient(web.app).get(f"/personas/{pid}/records")
    assert response.status_code == 200 and rows.revision_content(case(examples, "records-revision-changes")) in response.text
    assert rows.voice_content(case(examples, "records-voice-green")) in response.text


def test_actual_fastmcp_four_schemas_and_single_execution(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_eval, _tools_personas
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/records/v1"
    envelopes = []
    for module in (_tools_eval, _tools_personas):
        env = module._env
        def capture(*args, _env=env, **kwargs):
            value = _env(*args, **kwargs)
            envelopes.append(deepcopy(value))
            return value
        monkeypatch.setattr(module, "_env", capture)
    for name in TOOLS:
        item = next(row for row in examples if row["tool"] == name)
        calls, native = [], getattr(services, name)
        def counted(*args, **kwargs):
            value = native(*args, **kwargs)
            calls.append(deepcopy(value))
            return value
        with monkeypatch.context() as patch:
            patch.setattr(services, name, counted)
            before = len(envelopes)
            result = asyncio.run(server.call_tool(name, item["input"]))
        assert not result.isError and len(calls) == 1 and len(envelopes) == before + 1
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1])
        assert result.content == text and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["state"] == TOOLS[name](calls[0])[1]
        assert result.meta["sonaloop/presentation"]["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()

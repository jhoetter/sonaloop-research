"""Native Questions results and the existing scoped Product question inspector."""
import builtins
from copy import deepcopy
import gc
import html
import io
import json
import os
from pathlib import Path
import shutil
import socket

from fastapi.testclient import TestClient
import pytest

from sonaloop import artifacts, config, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import project_graph as ui


RENDERERS = {"record_open_questions": ui.recorded_questions, "get_research_frontier": ui.frontier}


def forbidden(*args, **kwargs):
    pytest.fail("Question rendering attempted source, provider, telemetry or network access")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch, tmp_path):
    from sonaloop import avatar, embeddings, telemetry
    from sonaloop.services import _hooks
    from sonaloop.storage import _base
    monkeypatch.setattr(_base, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.setattr(web, "load_env", lambda: None)
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(telemetry, "_SINKS", {"forbidden": forbidden})
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)
    yield
    gc.collect()
    shutil.rmtree(tmp_path)


@pytest.fixture
def store():
    with Store() as value:
        yield value


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_research
    server = FastMCP("original-questions")
    _tools_research.register_research(server)
    return server


@pytest.fixture
def examples(store):
    server, cases = original_server(), []
    def call(name, scenario, **arguments):
        envelope = server._tool_manager._tools[name].fn(**arguments)
        cases.append({"scenario": scenario, "tool": name, "input": deepcopy(arguments),
                      "value": deepcopy(envelope["data"]), "envelope": deepcopy(envelope)})
        return envelope["data"]
    project = services.create_research_project("Questions fixture", "Inspect unresolved handovers", store=store)["id"]
    call("get_research_frontier", "frontier-unrecorded", project_id=project)
    created = call("record_open_questions", "questions-duplicates-and-blank", project_id=project,
        questions=["Who owns the handover?", "\t ", "Who owns the handover?", "What context is missing?"])
    call("get_research_frontier", "frontier-open", project_id=project)
    call("record_open_questions", "questions-retry-study", project_id=project,
         questions=["Who owns the handover?"], study_id="council:literal-source")
    call("record_open_questions", "questions-empty", project_id=project, questions=["", " \n "])
    answered = store.list_open_questions(project)[0]
    store.upsert_open_question({**answered, "status": "answered"})
    call("get_research_frontier", "frontier-answer-excluded", project_id=project)
    other = services.create_research_project("Other questions", "Keep scopes separate", store=store)["id"]
    call("record_open_questions", "questions-other-project", project_id=other, questions=["Who owns the handover?"], study_id="")
    call("get_research_frontier", "frontier-other-project", project_id=other)
    for row in store.list_open_questions(project):
        store.upsert_open_question({**row, "status": "resolved"})
    call("get_research_frontier", "frontier-resolved", project_id=project)
    assert len(created["open_questions"]) == 3
    return cases


def case(examples, name):
    return next(row for row in examples if row["scenario"] == name)


def test_original_native_envelopes_and_public_values_stay_exact(examples, tmp_path):
    server = original_server()
    for item in examples:
        before = deepcopy(item["value"])
        item["public_value"] = deepcopy(item["value"])
        markup, state = RENDERERS[item["tool"]](item["value"])
        assert (markup, state) == RENDERERS[item["tool"]](item["public_value"])
        assert item["value"] == before == item["public_value"]
        assert item["envelope"]["ok"] and item["envelope"]["data"] == before
        assert item["envelope"]["_meta"]["tool"] == item["tool"]
        content, structured = server._tool_manager._tools[item["tool"]].fn_metadata.convert_result(item["envelope"])
        assert structured == json.loads(content[0].text) == item["envelope"]
        item["state"] = state
    path = Path(os.environ.get("RESEARCH_QUESTIONS_AUDIT_PATH", tmp_path / "native-first.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))


def test_actual_duplicates_retry_scope_and_frontier_notes(examples, store):
    first = case(examples, "questions-duplicates-and-blank")["value"]["open_questions"]
    repeated = case(examples, "questions-retry-study")["value"]["open_questions"][0]
    assert first[0]["id"] == first[1]["id"] == repeated["id"]
    assert first[0]["created_at"] != repeated["created_at"]
    assert repeated["study_id"] == "council:literal-source" and first[0]["study_id"] is None
    assert len(store.list_open_questions(first[0]["project_id"])) == 2
    markup = ui.recorded_questions({"open_questions": first})[0]
    assert markup.count("Who owns the handover?") == 2
    assert f'<p class="sl-research-status">{ui.t("oq_status_open")}</p>' in markup
    assert '<dt>status</dt><dd>open</dd>' in markup
    assert case(examples, "frontier-open")["value"]["open_question_count"] == 2
    after = case(examples, "frontier-answer-excluded")["value"]
    assert after["open_question_count"] == 1 and after["open_questions"][0]["text"] == "What context is missing?"
    foreign = case(examples, "questions-other-project")["value"]["open_questions"][0]
    assert foreign["id"] != first[0]["id"] and foreign["study_id"] == ""
    for scenario in ("frontier-unrecorded", "frontier-resolved"):
        value = case(examples, scenario)["value"]
        assert value["open_question_count"] == 0 and "or unrecorded" in value["notes"][0]
        markup, state = ui.frontier(value)
        assert state == "empty" and html.escape(value["notes"][0]) in markup
    assert ui.recorded_questions({"open_questions": []})[1] == "empty"


def test_native_long_text_keeps_original_id_semantics(store):
    pid = services.create_research_project("Long questions", "Retain the native text cap", store=store)["id"]
    first, second = services.record_open_questions(pid, ["A" * 600 + "first", "A" * 600 + "second"], store=store)
    assert first["text"] == second["text"] == "A" * 600 and first["id"] != second["id"]
    markup = ui.recorded_questions({"open_questions": [first, second]})[0]
    assert markup.count("A" * 600) == 2 and first["id"] in markup and second["id"] in markup


def test_existing_product_inspector_and_native_bodies_match(examples, store, monkeypatch):
    pid = case(examples, "frontier-open")["value"]["project_id"]
    question = store.list_open_questions(pid)[0]
    render, calls = ui.question_content, []
    def observed(value, **kwargs):
        body = render(value, **kwargs)
        calls.append((deepcopy(value), kwargs, body))
        return body
    monkeypatch.setattr(ui, "question_content", observed)
    monkeypatch.setattr(services, "get_research_frontier", forbidden)
    monkeypatch.setattr(services, "record_open_questions", forbidden)
    before = list(store.conn.iterdump())
    response = TestClient(web.create_app()).get('/open-questions/' + question["id"])
    assert response.status_code == 200 and len(calls) == 1
    assert calls[0][0] == question and calls[0][1]["passive"] is False
    assert calls[0][2] == render(question) and calls[0][2] in response.text
    assert render(question) in ui.questions_content([question])
    assert render(question) in ui.recorded_questions({"open_questions": [question]})[0]
    assert f'href="/jobs/{pid}"' in response.text and "sec-question" in response.text
    assert before == list(store.conn.iterdump())


def test_product_missing_question_is_checked_before_the_shared_body(store, monkeypatch):
    from sonaloop.web.pages import library
    monkeypatch.setattr(library, "_find_open_question", lambda *_: (None, None))
    monkeypatch.setattr(ui, "question_content", forbidden)
    monkeypatch.setattr(services, "get_research_frontier", forbidden)
    response = TestClient(web.create_app()).get('/open-questions/inaccessible-question')
    assert response.status_code == 200 and '<div class="sl-research-question-content">' not in response.text
    # This proves the existing scoped Product read boundary, not Postgres RLS.


def test_legacy_product_text_control_and_fallback_are_preserved(examples, store):
    pid = case(examples, "frontier-open")["value"]["project_id"]
    row = store.list_open_questions(pid)[0]
    row["text"] = "Long stored question. " * 80
    store.upsert_open_question(row)
    response = TestClient(web.create_app()).get('/open-questions/' + row["id"])
    assert response.status_code == 200 and "sl-clamp-toggle" in response.text
    assert html.escape(row["text"]) in response.text and '<button' not in ui.question_content(row)
    row["created_at"] = False
    store.upsert_open_question(row)
    response = TestClient(web.create_app()).get('/open-questions/' + row["id"])
    assert response.status_code == 200 and "sl-clamp-toggle" in response.text
    assert '<div class="sl-research-question-content">' not in response.text and html.escape(row["text"]) in response.text


def test_passive_bodies_never_read_or_write(examples, monkeypatch):
    from sonaloop.web import _render
    for item in examples:
        RENDERERS[item["tool"]](item["value"])
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(_render, "render_ref", forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        for module in (builtins, io):
            patch.setattr(module, "open", forbidden)
        for name in ("open", "read_text", "read_bytes", "exists", "is_file"):
            patch.setattr(Path, name, forbidden)
        for name in (*RENDERERS, "get_project_graph", "get_study_result"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            markup, _ = RENDERERS[item["tool"]](item["value"])
            assert not any(tag in markup for tag in ("<img", "<script", "<iframe", "<button", "<form", "<pre"))
            assert "<details open" not in markup
    assert examples == before


def test_supplied_count_status_null_and_hostile_text_are_literal(examples):
    value = deepcopy(case(examples, "frontier-open")["value"])
    value["open_question_count"] = 41
    value["open_questions"][0]["status"] = "unrecognized native state"
    hostile = '<script>bad()</script><img src="https://invalid.test/pixel" onerror="bad()">'
    value["open_questions"][0]["text"] = hostile * 25
    value["notes"] = [hostile, "A literal dispatch_token field in authored text"]
    markup, _ = ui.frontier(value)
    assert "<dd>41</dd>" in markup and "unrecognized native state" in markup and "<dd>null</dd>" in markup
    assert html.escape(hostile * 25) in markup and html.escape(hostile) in markup
    assert "literal dispatch_token" in markup and not any(tag in markup for tag in ("<script", "<img", "<button"))
    assert '<h2>Research frontier</h2>' in markup


def test_hmw_and_unsupported_shapes_do_not_invent_status_or_counts(examples):
    with pytest.raises(ValueError):
        ui.question_content({"id": "hmw", "question": "How might we?"})
    question = deepcopy(case(examples, "frontier-open")["value"]["open_questions"][0])
    with pytest.raises(ValueError):
        ui.question_content(question, prepared_text="public HTML is forbidden")
    for bad in (None, [], {}, {"open_questions": [], "count": 4}):
        with pytest.raises(ValueError):
            ui.recorded_questions(bad)
    for bad_count in (True, -1, 1.5, "2"):
        value = deepcopy(case(examples, "frontier-open")["value"])
        value["open_question_count"] = bad_count
        with pytest.raises(ValueError):
            ui.frontier(value)
    question["extra"] = {"new": "shape"}
    with pytest.raises(ValueError):
        ui.recorded_questions({"open_questions": [question]})


def test_original_native_signatures_and_annotations_are_unchanged():
    import inspect
    from sonaloop.mcp_server._annotations import TOOL_ANNOTATIONS
    server = original_server()
    expected = {"record_open_questions": ("project_id", "questions", "study_id"),
                "get_research_frontier": ("project_id",)}
    for name, parameters in expected.items():
        assert tuple(inspect.signature(server._tool_manager._tools[name].fn).parameters) == parameters
        assert TOOL_ANNOTATIONS[name]["readOnlyHint"] is (name == "get_research_frontier")

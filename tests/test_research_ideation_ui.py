"""Actual five-tool results and shared Note/Council rendering, in private Stores."""
from copy import deepcopy
import gc
import html
import io
import builtins
import json
import os
from pathlib import Path
import shutil
import socket

from fastapi.testclient import TestClient
import pytest

from sonaloop import artifacts, config, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import ideation as ui, library
from conftest import make_profile


RENDERERS = {"record_hmw_reframe": ui.reframe, "record_ideas": ui.ideas,
    "list_ideas": ui.ideas, "record_ideation_summary": ui.recorded, "get_ideation": ui.stored}


def forbidden(*args, **kwargs):
    pytest.fail("Ideation rendering attempted source, provider or network access")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch, tmp_path):
    from sonaloop import avatar, embeddings, telemetry
    from sonaloop.services import _hooks
    from sonaloop.storage import _base
    monkeypatch.setattr(_base, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(telemetry, "_SINKS", {"forbidden": forbidden})
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.setattr(web, "load_env", lambda: None)
    monkeypatch.setattr(web, "DATA_DIR", tmp_path / "data")
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
    from sonaloop.mcp_server import _tools_ideation
    server = FastMCP("original-ideation")
    _tools_ideation.register_ideation(server)
    return server


@pytest.fixture
def examples(store):
    server, examples = original_server(), []
    def call(name, scenario, **arguments):
        envelope = server._tool_manager._tools[name].fn(**arguments)
        examples.append({"scenario": scenario, "tool": name, "input": deepcopy(arguments),
                         "value": deepcopy(envelope["data"]), "envelope": deepcopy(envelope)})
        return envelope["data"]
    person = services.record_persona("Synthetic handover owner", make_profile("Synthetic voice"),
                                    generate_avatar=False, store=store)["id"]
    pid = services.create_research_project("Ideation fixture", "Clarify a handover", persona_ids=[person], store=store)["id"]
    reframe = call("record_hmw_reframe", "reframe-hypothesis", project_id=pid, problem="The next owner lacks context.",
        hmws=[{"question": "How might we name the next owner?", "prediction": {
                "metric": "handover_delay", "expected_direction": "decrease"}},
              "How might we preserve pending work?", "How might we show unresolved risk?"])
    questions = reframe["hmw"]
    args = {"project_id": pid, "ideas": [
        {"text": "Show the pending owner", "persona_id": person, "hmw_ref": questions[0]["id"], "cluster": "ownership"},
        {"text": "Keep a shared handover note", "persona_id": person, "hmw_ref": questions[1]["id"], "cluster": ""}]}
    ideas = call("record_ideas", "ideas-recorded", **args)["ideas"]
    call("record_ideas", "ideas-recorded-replay", **args)
    call("list_ideas", "ideas-listed", project_id=pid)
    call("list_ideas", "ideas-empty-filter", project_id=pid, cluster="absent-cluster")
    call("list_ideas", "ideas-filtered", project_id=pid, hmw_ref=questions[0]["id"], persona_id=person, cluster="ownership")
    ref = {"kind": "persona", "id": person, "anchor": "detail", "role": "derived_from",
           "quote": "A supplied quotation", "text": "A supplied reference text"}
    args = {"project_id": pid, "problem": "The next owner lacks context.", "key": "synthetic-ideation-key",
        "shortlist": [{"idea_id": ideas[1]["id"], "rationale": "The shared note preserves unfinished work."},
                      {"idea_id": ideas[0]["id"], "rationale": "Then identify who takes over."}],
        "statements": [{"persona_id": person, "text": "I need the unresolved work before accepting a handover.",
                        "stance": {"value": 1}, "about": {"kind": "prompt", "id": "hmw:0"},
                        "relevance": "Keeps the next shift informed", "shift": {"from": 0, "to": 1},
                        "refs": [ref], "meta": {"authored_empty": "", "authored_null": None,
                                                "dispatch_token": "literal authored field"}}],
        "summary": "Start with pending work.", "exec_summary": "Preserve context before naming the next owner."}
    council = call("record_ideation_summary", "summary-recorded", **args)
    call("record_ideation_summary", "summary-replay", **args)
    call("get_ideation", "summary-stored", session_id=council["id"])
    quiet = call("record_ideation_summary", "summary-no-statements", **{**args,
        "key": "synthetic-quiet-ideation-key", "statements": [], "summary": "", "exec_summary": ""})
    call("get_ideation", "summary-no-statements-stored", session_id=quiet["id"])
    return examples


def case(examples, scenario):
    return next(row for row in examples if row["scenario"] == scenario)


def test_actual_native_envelopes_public_bytes_and_private_fixture(examples, tmp_path):
    server = original_server()
    for item in examples:
        before = deepcopy(item["value"])
        item["public_value"] = ui.public_value(item["tool"], item["value"])
        rendered = RENDERERS[item["tool"]](item["value"])
        assert rendered == RENDERERS[item["tool"]](item["public_value"])
        assert item["value"] == before == item["public_value"]
        assert item["envelope"]["data"] == before and item["envelope"]["_meta"]["tool"] == item["tool"]
        content, structured = server._tool_manager._tools[item["tool"]].fn_metadata.convert_result(item["envelope"])
        assert structured == json.loads(content[0].text) == item["envelope"]
        item["state"] = rendered[1]
    writer = case(examples, "summary-recorded")["value"]
    assert writer["dispatch_provenance"] == {"state": "legacy"}
    assert writer["dispatch"] == {"state": "legacy", "checkpointed": False,
                                  "provenance": "not governed by an active dispatch"}
    path = Path(os.environ.get("RESEARCH_IDEATION_AUDIT_PATH", tmp_path / "native-first.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))


def test_writer_getter_differences_rank_and_null_are_not_fabricated(examples):
    written = case(examples, "ideas-recorded")["value"]
    listed = case(examples, "ideas-listed")["value"]
    assert all(row["kind"] == "idea" and "hmw_question" in row for row in written["ideas"])
    assert all("hmw_question" not in row for row in listed["ideas"])
    assert "How might we name the next owner?" in ui.ideas(written)[0]
    assert "How might we name the next owner?" not in ui.ideas(listed)[0]
    assert ui.ideas(case(examples, "ideas-empty-filter")["value"])[1] == "empty"
    writer = case(examples, "summary-recorded")["value"]
    getter = case(examples, "summary-stored")["value"]
    assert "statements" in writer and "statements" not in getter and "ideation" not in getter
    assert getter["shortlist"][0]["rank"] == 1 and getter["shortlist"][0]["cluster"] is None
    markup = ui.stored(getter)[0]
    assert "sl-research-council-voices" not in markup and "null" in markup
    assert markup.index("Keep a shared handover note") < markup.index("Show the pending owner")
    assert "sl-research-council-voices" in ui.recorded(writer)[0]
    reframe = case(examples, "reframe-hypothesis")["value"]
    assert reframe["hmw"][0]["hypothesis_id"] in ui.reframe(reframe)[0]
    assert all("status" not in row for row in reframe["hmw"])


def test_native_retry_and_scope_remain_the_native_contract(examples, store):
    first = case(examples, "summary-recorded")["value"]
    again = case(examples, "summary-replay")["value"]
    assert first["id"] == again["id"] and first["created_at"] == again["created_at"]
    assert len(store.list_council_sessions()) == 2
    initial = case(examples, "ideas-recorded")["value"]["ideas"]
    repeated = case(examples, "ideas-recorded-replay")["value"]["ideas"]
    assert {row["id"] for row in initial}.isdisjoint(row["id"] for row in repeated)
    assert [row["text"] for row in initial] == [row["text"] for row in repeated]
    assert len(services.list_ideas(first["project_id"], store=store)) == 4
    other = services.create_research_project("Other project", "Another scope", store=store)["id"]
    assert services.list_ideas(other, store=store) == []
    with pytest.raises(ValueError, match="recorded idea of this project"):
        # Give the second project a pool, then try a first-project shortlist.
        q = services.record_hmw_reframe(other, "Other", ["One?", "Two?", "Three?"], store=store)["hmw"][0]["id"]
        services.record_ideas(other, [{"text": "Other idea", "persona_id": first["persona_ids"][0], "hmw_ref": q}], store=store)
        services.record_ideation_summary(other, "Other", [{"idea_id": first["ideation"]["shortlist"][0]["idea_id"],
                                                         "rationale": "Foreign"}], store=store)


def test_shared_hmw_note_and_council_bodies_are_exact(examples, store, monkeypatch):
    writer = case(examples, "summary-replay")["value"]
    expected = ui.ideation_content(writer["ideation"])
    assert expected in ui.recorded(writer)[0]
    assert expected in ui.stored(case(examples, "summary-stored")["value"])[0]
    assert ui.hmw_content(writer["ideation"]["hmw"]) in expected
    before = list(store.conn.iterdump())
    response = TestClient(web.create_app()).get('/councils/' + writer["id"])
    assert response.status_code == 200 and expected in response.text
    assert response.text.count('<h2>Ideation</h2>') == 1
    note = case(examples, "ideas-listed")["value"]["ideas"][0]
    response = TestClient(web.create_app()).get('/notes/' + note["id"])
    assert response.status_code == 200 and library.note_content(note) in response.text
    assert 'Source attribution' in response.text and note["data"]["hmw_ref"] in response.text
    assert before == list(store.conn.iterdump())


def test_optional_product_extensions_keep_original_text_and_transcript(examples, store):
    note = {"kind": "idea", "text": "Original idea remains readable", "data": {"persona_id": {"bad": "shape"}}}
    assert "Original idea remains readable" in library.note_content(note)
    assert "sl-research-format-unavailable" in library.note_content(note)
    ordinary = {"text": "Ordinary document", "data": {"persona_id": "not an idea"}}
    assert "Source attribution" not in library.note_content(ordinary)
    council = deepcopy(case(examples, "summary-recorded")["value"])
    council["ideation"]["unknown_extension"] = {"new": "shape"}
    store.insert_council_session(council)
    response = TestClient(web.create_app()).get('/councils/' + council["id"])
    assert response.status_code == 200 and "sl-research-format-unavailable" in response.text
    assert "I need the unresolved work" in response.text


def test_passive_rendering_has_no_io_and_all_reference_text_is_preserved(examples, monkeypatch):
    from sonaloop.web import _render
    for row in examples:
        RENDERERS[row["tool"]](row["value"])
    before = deepcopy(examples)
    original_ref = _render.render_ref
    calls = []
    def passive_ref(value, store=None, **kwargs):
        assert store is None and kwargs.get("passive") is True
        calls.append(deepcopy(value))
        return original_ref(value, store=store, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(_render, "_avatar", forbidden)
        patch.setattr(_render, "render_ref", passive_ref)
        for module in (builtins, io):
            patch.setattr(module, "open", forbidden)
        for name in ("open", "read_text", "read_bytes", "exists", "is_file"):
            patch.setattr(Path, name, forbidden)
        for name in (*RENDERERS, "get_note", "list_notes", "record_council", "get_council"):
            patch.setattr(services, name, forbidden)
        for row in examples:
            markup, _ = RENDERERS[row["tool"]](row["value"])
            assert all(tag not in markup for tag in ("<img", "<script", "<iframe", "<button", "<form"))
            assert '<details open' not in markup
    assert calls and examples == before
    markup = ui.recorded(case(examples, "summary-recorded")["value"])[0]
    assert all(text in markup for text in ("detail", "derived_from", "A supplied quotation", "A supplied reference text"))
    assert "literal authored field" in markup and "authored_null" in markup


def test_native_contexts_are_not_filtered_and_unknown_context_falls_back(examples):
    writer = deepcopy(case(examples, "summary-recorded")["value"])
    assert ui.public_value("record_ideation_summary", writer) == writer
    for path in ("dispatch", "dispatch_provenance"):
        changed = deepcopy(writer)
        changed[path]["dispatch_token"] = "new execution shape"
        with pytest.raises(ValueError, match="context"):
            ui.recorded(changed)
        assert changed[path]["dispatch_token"] == "new execution shape"


def test_hostile_full_text_and_empty_public_blocks(examples):
    hostile = '<script>bad()</script><img src="https://invalid.test/pixel" onerror="bad()">'
    value = deepcopy(case(examples, "summary-stored")["value"])
    value["problem"] = hostile * 40
    value["shortlist"][0]["rationale"] = hostile
    value["shortlist"][0]["text"] = hostile
    value["shortlist"][0]["cluster"] = hostile
    value["cite_as"]["quote"] = hostile
    rendered = ui.stored(value)[0]
    assert html.escape(hostile * 40) in rendered and html.escape(hostile) in rendered
    assert all(tag not in rendered for tag in ("<script", "<img", "<iframe"))
    value["hmw"], value["ideas"], value["shortlist"] = [], [], []
    rendered = ui.stored(value)[0]
    for text in ("No questions supplied.", "No ideas supplied.", "No ranked ideas supplied."):
        assert text in rendered
    assert "<pre" not in rendered


def test_invalid_supplied_shapes_fail_without_partial_results(examples):
    for value in (None, [], {}, {"hmw": False}):
        with pytest.raises(ValueError):
            ui.reframe(value)
    note = deepcopy(case(examples, "ideas-recorded")["value"])
    note["ideas"][0]["data"]["persona_id"] = ["malformed"]
    with pytest.raises(ValueError):
        ui.ideas(note)
    summary = deepcopy(case(examples, "summary-stored")["value"])
    summary["shortlist"][0]["rank"] = True
    with pytest.raises(ValueError):
        ui.stored(summary)
    summary["shortlist"][0]["rank"] = 1
    summary["hmw"][0]["status"] = "invented"
    with pytest.raises(ValueError):
        ui.stored(summary)


def test_actual_native_signatures_and_annotations_are_unchanged():
    import inspect
    from sonaloop.mcp_server._annotations import TOOL_ANNOTATIONS
    server = original_server()
    expected = {"record_hmw_reframe": ("project_id", "problem", "hmws"), "record_ideas": ("project_id", "ideas"),
        "list_ideas": ("project_id", "hmw_ref", "persona_id", "cluster"),
        "record_ideation_summary": ("project_id", "problem", "shortlist", "statements", "summary", "exec_summary", "selection_reason", "key"),
        "get_ideation": ("session_id",)}
    for name, parameters in expected.items():
        assert tuple(inspect.signature(server._tool_manager._tools[name].fn).parameters) == parameters
        assert TOOL_ANNOTATIONS[name]["readOnlyHint"] is (name in {"list_ideas", "get_ideation"})

"""Actual isolated memory results, product sharing, temporal truth and passive I/O."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from sonaloop import config, memory as native_memory, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import memory, memory_rows


STAMP = "2026-01-01T09:00:00"
NAMES = {"list_active_projects": memory.active_projects, "search_entities": memory.entities,
         "resolve_entity": memory.entity, "get_project": memory.project, "get_state_at": memory.state_at,
         "get_timeline": memory.timeline, "get_open_loops": memory.threads, "recall_memory": memory.recall,
         "get_persona_memory": memory.document, "export_persona_memory": memory.exported}


def forbidden(*args, **kwargs):
    pytest.fail("Passive memory rendering attempted native, file, media, provider or clock I/O")


@pytest.fixture
def recorded(store):
    from conftest import make_profile
    persona = services.record_persona("Memory fixture reader", make_profile("Memory reader"),
                                      generate_avatar=False, store=store)
    pid = persona["id"]
    entity = {"id": "ent_renewal", "persona_id": pid, "kind": "project", "name": "Renewal",
              "status": "approved", "aliases": ["Annual renewal"], "first_seen": "2026-01-01",
              "last_seen": "2026-02-01", "created_at": STAMP, "updated_at": STAMP}
    store.upsert_entity(entity)
    store.upsert_entity({**entity, "id": "ent_contact", "kind": "person", "name": "Jo", "status": None, "aliases": []})
    source = {"kind": "note", "id": "note_fixture", "anchor": "line:2", "quote": "Keep the original qualifier.",
              "text": "Supplied source context.", "role": "grounds"}
    for fid, fact, status, valid, invalid in (("fact_old", "Renewal pending", "pending", "2026-01-01", "2026-02-01"),
                                           ("fact_new", "Renewal approved", "approved", "2026-02-01", None)):
        store.insert_entity_fact({"id": fid, "persona_id": pid, "entity_id": entity["id"], "fact": fact,
            "status": status, "t_valid": valid, "t_invalid": invalid, "importance": 3, "source_event_id": None,
            "source_kind": "derived_fact", "source_refs": [source], "confidence": 0,
            "review_status": "disputed", "created_at": STAMP})
    for tid, text, opened, closed in (("thread_resolved", "Confirm the previous owner", "2026-01-02", "2026-02-02"),
                                     ("thread_open", "Confirm the next owner", "2026-01-20", None)):
        store.upsert_thread({"id": tid, "persona_id": pid, "entity_id": entity["id"], "text": text,
            "status": "resolved" if closed else "open", "opened_on": opened, "closed_on": closed,
            "created_at": STAMP, "updated_at": STAMP})
    for eid, day in (("evt_before", "2026-01-15"), ("evt_after", "2026-02-15")):
        store.insert_experience_event({"id": eid, "persona_id": pid, "timestamp": day + "T09:00:00",
            "event_type": "focus", "task": "Review renewal", "summary": "The renewal is being reviewed.", "tool": "E-Mail",
            "participants": [], "collaboration_mode": "solo", "what_happened": "Checked the renewal.",
            "conversation": [], "key_quotes": [], "actions_done": [], "artifacts_touched": [],
            "persona_thought": "The record needs an owner.", "decision": None, "open_loops": [],
            "impact": {}, "pain_points": [], "goal_refs": [], "calendar_event_id": None, "created_at": STAMP})
        store.link_event_entity(eid, entity["id"], pid)
    store.upsert_digest({"id": "digest_fixture", "persona_id": pid, "scope": "month", "period_start": "2026-01-01",
        "period_end": "2026-01-31", "created_at": STAMP, "text": "The handover remains unresolved.",
        "themes": ["Ownership"], "project_arcs": [{"name": "Renewal", "arc": "Pending to approved"}], "trends": ["Less uncertainty"]})
    store.insert_world_context({"id": "world_fixture", "category": "work", "fact": "Office closed for the holiday.",
        "t_valid": "2026-01-01", "t_invalid": None, "relevance_tags": ["office"], "created_at": STAMP})
    store.commit()
    return pid, entity


def native_inputs(recorded):
    pid, entity = recorded
    return {"list_active_projects": {"persona_id": pid}, "search_entities": {"persona_id": pid, "kind": "project", "name": "renewal"},
        "resolve_entity": {"persona_id": pid, "mention": "Annual renewal", "kind": "project"},
        "get_project": {"persona_id": pid, "entity_id": entity["id"], "as_of": "2026-01-15"},
        "get_state_at": {"persona_id": pid, "as_of": "2026-01-15"},
        "get_timeline": {"persona_id": pid, "start": "2026-01-01", "end": "2026-12-31", "max_facts": 1, "max_events": 1},
        "get_open_loops": {"persona_id": pid, "status": None},
        "recall_memory": {"persona_id": pid, "query": "Renewal", "as_of": "2026-01-15", "k": 8},
        "get_persona_memory": {"persona_id": pid},
        "export_persona_memory": {"persona_id": pid, "out_path": "exports/memory-fixture.md"}}


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_simulation
    server = FastMCP("original-memory-fixtures")
    _tools_simulation.register_simulation(server)
    return server


def native_values(recorded):
    server = original_server()
    return {name: server._tool_manager._tools[name].fn(**arguments)["data"]
            for name, arguments in native_inputs(recorded).items()}


def test_original_native_fixture_export_with_null_empty_caps_and_history(recorded, tmp_path):
    server = original_server()
    cases = [(name, name, arguments) for name, arguments in native_inputs(recorded).items()]
    pid = recorded[0]
    cases.extend([
        ("entity-null", "resolve_entity", {"persona_id": pid, "mention": "Unmentioned object", "kind": "tool"}),
        ("entities-empty", "search_entities", {"persona_id": pid, "kind": "tool"}),
        ("timeline-empty", "get_timeline", {"persona_id": pid, "start": "2027-01-01"}),
        ("threads-empty", "get_open_loops", {"persona_id": pid, "status": "unknown"}),
        ("recall-empty", "recall_memory", {"persona_id": pid, "query": "Renewal", "as_of": "2025-01-01"}),
        ("state-empty", "get_state_at", {"persona_id": pid, "as_of": "2025-01-01"}),
    ])
    examples = []
    for scenario, name, arguments in cases:
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        html, state = NAMES[name](value)
        assert state == ("empty" if scenario.endswith(("-empty", "-null")) else "ready")
        assert len(json.dumps({"name": name, "value": value}, ensure_ascii=False).encode()) <= 8192
        examples.append({"scenario": scenario, "tool": name, "input": arguments, "value": value, "state": state})
    path = Path(os.environ.get("RESEARCH_MEMORY_FIXTURE_PATH", tmp_path / "memory-fixtures.json"))
    path.write_text(json.dumps(examples, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print("Original native Memory10 fixtures:", path)


def test_all_ten_native_views_are_pure_and_preserve_input(recorded, monkeypatch):
    values = native_values(recorded)
    before = deepcopy(values)
    from sonaloop.web import _components, _render
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(native_memory, "embed_texts", forbidden)
        patch.setattr(native_memory, "utc_now_iso", forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        patch.setattr(_render._A, "resolve_ref", forbidden)
        for name, value in values.items():
            html, state = NAMES[name](value)
            assert state == "ready" and html
            assert all(tag not in html for tag in ("<img", "<form", "<iframe", "<script"))
    assert values == before


def test_current_project_and_historical_state_remain_distinct(recorded):
    values = native_values(recorded)
    project, _ = memory.project(values["get_project"])
    assert "approved" in project and "Renewal pending" in project and "Renewal approved" not in project
    assert "not a historical snapshot" in project and "<dd>false</dd>" in project
    state, _ = memory.state_at(values["get_state_at"])
    assert "pending" in state and "approved" not in state
    assert "thread_resolved" in state and "resolved" in state and "2026-02-02" in state
    assert "thread_open" not in state and "World context" in state and "world_fixture" in state


def test_native_cap_note_and_totals_are_visible_without_fetching(recorded):
    value = native_values(recorded)["get_timeline"]
    html, _ = memory.timeline(value)
    assert value["facts_total"] == 2 and value["events_total"] == 2
    assert value["note"] in html and html.count("sl-research-memory-event") == 1
    assert "fact_new" in html and "fact_old" not in html and "<dd>2</dd>" in html
    assert "evt_after" not in html, "Native lean timeline events do not include IDs"


def test_passive_retains_all_threads_full_facts_provenance_and_zero(recorded, store):
    pid = recorded[0]
    value = services.get_timeline(pid, max_facts=0, max_events=0, store=store)
    value["facts"][0]["fact"] = "Qualifier. " * 400 + "Final scope limitation."
    html, _ = memory.timeline(value)
    for literal in ("Final scope limitation.", "Keep the original qualifier.", "Supplied source context.",
                    "note:note_fixture#line:2", "derived_fact", "disputed", "<dd>0</dd>"):
        assert literal in html
    assert "sl-research-memory-superseded" in html
    threads = services.get_open_loops(pid, status=None, store=store)
    threads = [{**threads[0], "id": f"thread_{i}", "text": f"Full thread {i}"} for i in range(27)]
    html, _ = memory.threads(threads)
    assert html.count("sl-research-memory-thread") == 27 and "Full thread 26" in html


def test_recall_preserves_supplied_scores_and_vector_mismatch(recorded):
    value = native_values(recorded)["recall_memory"]
    value["embedding_space_mismatch"] = {"skipped": 3, "note": "Stored vectors were ignored."}
    value["hits"][0].update(score=0, semantic=0, keyword=0, recency=0, importance=0, confidence=0,
                             review_status="disputed", text="Exact supplied excerpt…")
    html, _ = memory.recall(value)
    assert "Exact supplied excerpt…" in html and "Stored vectors were ignored." in html
    assert "Ranking score" in html and html.count("<dd>0</dd>") >= 6
    assert "<dd>false</dd>" in html and "Supplied recall excerpt" in html


@pytest.mark.parametrize("name,value", [
    ("search_entities", {}), ("resolve_entity", {}), ("list_active_projects", [{"entity_id": "a", "name": "b", "open_loops": True, "valid_facts": 0}]),
    ("get_project", {"entity": {}, "status_now": None, "facts": [], "open_threads": [], "event_ids": []}),
    ("get_state_at", {"persona_id": "p", "as_of": "2026-01-01", "entities": [], "open_threads": [], "world_context": [None]}),
    ("get_timeline", {"persona_id": "p", "facts": [], "events": [], "facts_total": False, "events_total": 0}),
    ("get_open_loops", [{"id": "t", "persona_id": "p", "text": {}, "status": "open"}]),
    ("recall_memory", {"persona_id": "p", "query": "", "hits": [], "k": 1, "semantic_enabled": "false"}),
    ("get_persona_memory", {"persona_id": "p", "content": []}),
    ("export_persona_memory", {"persona_id": "p", "path": "a", "bytes": -1}),
])
def test_malformed_native_values_fail_before_partial_markup(name, value):
    with pytest.raises(ValueError):
        NAMES[name](value)


def test_untrusted_native_text_cannot_inject_markup(recorded):
    values = native_values(recorded)
    values["get_timeline"]["facts"][0]["fact"] = '<img src=x onerror="bad()">'
    values["get_timeline"]["facts"][0]["source_refs"] = [{"kind": "note", "id": "<script>bad()</script>", "quote": "<iframe>"}]
    values["get_persona_memory"]["content"] = '# Title\n<script>bad()</script>\n[link](javascript:bad())'
    values["export_persona_memory"]["path"] = 'javascript:bad()" onclick="bad()'
    for name in ("get_timeline", "get_persona_memory", "export_persona_memory"):
        html, _ = NAMES[name](values[name])
        assert all(tag not in html for tag in ("<img", "<script", "<iframe", '<a href="javascript:'))


def test_product_memory_reuses_prepared_bodies_and_whole_record_overview(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.ui_components import memory_outcomes
    calls = []
    for module, name in ((memory, "knowledge_content"), (memory, "state_content"), (memory, "recall_content"),
                         (memory, "document"), (memory_outcomes, "digests"), (memory_outcomes, "summary_content")):
        original = getattr(module, name)
        def observe(*args, _name=name, _original=original, **kwargs):
            result = _original(*args, **kwargs)
            calls.append((_name, deepcopy(args), result[0] if isinstance(result, tuple) else result))
            return result
        monkeypatch.setattr(module, name, observe)
    monkeypatch.setattr(services, "extract_pain_points", forbidden)
    response = TestClient(web.create_app()).get(f"/personas/{recorded[0]}/memory?as_of=2026-01-15&q=Renewal")
    assert response.status_code == 200
    assert {name for name, _, _ in calls} == {"knowledge_content", "state_content", "recall_content", "document", "digests", "summary_content"}
    assert all(html in response.text for _, _, html in calls)
    summary = next(args[0] for name, args, _ in calls if name == "summary_content")
    assert summary["period"]["start"] is None and summary["events"] == 2
    assert 'name="as_of"' in response.text and 'name="q"' in response.text and "Whole-record memory overview" in response.text
    assert "disputed" in response.text and "mem-fact" in response.text


def test_product_keeps_twenty_loop_limit_and_native_overview_does_not_write(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    for i in range(25):
        store.upsert_thread({"id": f"extra_{i}", "persona_id": recorded[0], "entity_id": None,
            "text": f"Extra open loop {i}", "status": "open", "opened_on": "2026-03-01", "closed_on": None,
            "created_at": STAMP, "updated_at": STAMP})
    store.commit()
    calls = []
    original = memory_rows.thread_row
    def observe(value, **kwargs):
        calls.append((value["id"], kwargs))
        return original(value, **kwargs)
    monkeypatch.setattr(memory_rows, "thread_row", observe)
    monkeypatch.setattr(services, "extract_pain_points", forbidden)
    response = TestClient(web.create_app()).get(f"/personas/{recorded[0]}/memory")
    assert response.status_code == 200 and len(calls) == 20
    assert all("opened" in kwargs["prepared"] for _, kwargs in calls)
    assert "sl-research-memory-document" in response.text and "sl-research-memory-summary" in response.text
    assert "Extra open loop 24" in response.text, "The full compact memory document retains its supplied text"


def test_product_pain_body_preserves_original_finding_primitive(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop import artifacts
    from sonaloop.web._render import render_findings
    from sonaloop.ui_components import memory_outcomes
    observation = {"id": "pain_fixture", "persona_id": recorded[0], "issue": "Unclear handover",
        "severity": 2, "frequency": 3, "evidence_event_ids": ["evt_before"], "affected_workflow": "Handover",
        "opportunity": "Check the original owner", "created_at": STAMP}
    store.upsert_pain_point(observation)
    store.commit()
    expected = render_findings([artifacts.pain_point_finding(observation)])
    assert memory_outcomes.pain_content([observation]) == expected
    observed = []
    original = memory_outcomes.pain_content
    def capture(values, **kwargs):
        observed.append(deepcopy(values))
        return original(values, **kwargs)
    monkeypatch.setattr(memory_outcomes, "pain_content", capture)
    monkeypatch.setattr(services, "extract_pain_points", forbidden)
    response = TestClient(web.create_app()).get(f"/personas/{recorded[0]}")
    assert response.status_code == 200 and observed == [[observation]] and expected in response.text


def test_legacy_optional_fact_shape_keeps_product_loops_and_document_readable(recorded, store):
    from starlette.testclient import TestClient
    fact = store.list_entity_facts(recorded[1]["id"])[0]
    fact["confidence"] = {"legacy": "unknown"}
    store.insert_entity_fact(fact)
    store.commit()
    response = TestClient(web.create_app()).get(f"/personas/{recorded[0]}/memory")
    assert response.status_code == 200 and "cannot be displayed in full" in response.text
    assert "sl-research-memory-thread" in response.text and "sl-research-memory-document" in response.text
    assert "Confirm the next owner" in response.text


def test_ten_actual_fastmcp_tools_preserve_native_schema_and_result(recorded, monkeypatch, tmp_path):
    from sonaloop.mcp_server import build_server, _tools_simulation
    original = original_server()
    server = build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in NAMES:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/memory/v1"
    captured = []
    env = _tools_simulation._env
    def capture(name, *args, **kwargs):
        result = env(name, *args, **kwargs)
        captured.append((name, deepcopy(result)))
        return result
    monkeypatch.setattr(_tools_simulation, "_env", capture)
    for name, arguments in native_inputs(recorded).items():
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and captured[-1][0] == name
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(captured[-1][1])
        assert result.content == text and result.structuredContent == structured
        presentation = result.meta["sonaloop/presentation"]
        assert presentation["tool"] == name and presentation["state"] == "ready"
        assert presentation["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
    assert len(captured) == 10, "Rendering must not repeat a native call or export write"


def test_failed_export_presentation_retains_native_success_without_repeat(recorded, monkeypatch):
    from sonaloop.mcp_server import build_server, _research_ui
    server = build_server()
    calls = []
    original = services.export_persona_memory
    def export(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(deepcopy(result))
        return result
    def unsupported(*args, **kwargs):
        raise ValueError("Synthetic unsupported presentation")
    monkeypatch.setattr(services, "export_persona_memory", export)
    monkeypatch.setattr(_research_ui, "render_tool", unsupported)
    result = asyncio.run(server.call_tool("export_persona_memory", native_inputs(recorded)["export_persona_memory"]))
    assert not result.isError and len(calls) == 1
    assert result.structuredContent["data"] == calls[0] and calls[0]["bytes"] > 0
    assert not result.meta or "sonaloop/presentation" not in result.meta

"""Native Persona preparation and shared Product bodies, without provider access."""
import asyncio
from copy import deepcopy
from datetime import date
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
from sonaloop.ui_components import persona_preparation as view


TOOLS = {
    "persona_readiness": view.readiness,
    "persona_task_readiness": view.task_readiness,
    "prepare_persona_for_task": view.snapshot,
    "get_persona_context_snapshot": view.snapshot,
    "list_persona_context_snapshots": view.snapshots,
    "begin_persona_build": view.build,
    "persona_build_step": view.build,
    "get_persona_build": view.build,
    "list_persona_builds": view.builds,
}


def forbidden(*args, **kwargs):
    pytest.fail("Preparation presentation attempted native mutation, provider, media, file or network access")


@pytest.fixture
def persona(store, monkeypatch):
    from sonaloop import avatar
    from sonaloop.services import _hooks, _persona_lifecycle
    class FixedDay(date):
        @classmethod
        def today(cls):
            return date(2026, 6, 2)
    monkeypatch.setattr(_persona_lifecycle, "date", FixedDay)
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    return create_persona(store, "Preparation fixture")


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_personas
    server = FastMCP("original-persona-preparation")
    _tools_personas.register_personas(server)
    return server


def seed_ready(store, pid, build):
    """Explicit synthetic persisted inputs; no claim that authoring gates ran."""
    stamp = build["created_at"]
    person = store.get_persona(pid)
    person["personality"] = {key: "Checks written details before agreeing to the next action."
                             for key in person["personality"]}
    person["capabilities"] = {"rungs": {"see": True, "walk": True, "drive": False, "login": False},
                              "tech_comfort": 3, "devices": ["mobile"], "accessibility": "", "provenance": "authored"}
    store.upsert_persona(person, reason="synthetic preparation test")
    corpus = services.ingest_corpus("Transfer review requires confirmation details before approval.",
                                    "interview", "Synthetic interview", store=store)
    chunk = store.list_corpus_chunks(corpus["id"])[0]
    services.record_grounding(pid, [corpus["id"]], [{"claim": "Checks transfer confirmation details",
                              "chunk_ids": [chunk["id"]]}], store=store)
    for idx in range(8):
        store.insert_experience_event({"id": f"prep-event-{idx}", "persona_id": pid,
            "timestamp": f"2026-06-{idx % 2 + 1:02d}T09:00:00", "event_type": "focus",
            "task": "Routine", "summary": "Routine", "tool": "E-Mail", "participants": [],
            "collaboration_mode": "solo", "what_happened": "Routine", "conversation": [],
            "key_quotes": [], "actions_done": [], "artifacts_touched": [],
            "persona_thought": "Check the written details.", "decision": None, "open_loops": [],
            "impact": {}, "pain_points": [], "goal_refs": [], "calendar_event_id": None, "created_at": stamp})
    store.upsert_entity({"id": "prep-project", "persona_id": pid, "kind": "project", "name": "Review",
        "status": "active", "aliases": [], "first_seen": "2026-06-01", "last_seen": "2026-06-02",
        "created_at": stamp, "updated_at": stamp})
    for idx in range(4):
        store.insert_entity_fact({"id": f"prep-fact-{idx}", "persona_id": pid, "entity_id": "prep-project",
            "fact": "Transfer confirmation requires review" if idx == 0 else f"Routine fact {idx}",
            "status": "active", "t_valid": "2026-06-01", "t_invalid": None, "importance": 5,
            "source_event_id": f"prep-event-{idx}", "source_kind": "simulated_episode", "source_refs": [],
            "confidence": 0, "review_status": "unreviewed", "created_at": stamp})
    for day in ("2026-05-31", "2026-06-01", "2026-06-02"):
        store.upsert_daily_summary({"id": "prep-day-" + day, "persona_id": pid, "date": day,
            "mood": "steady", "completed": [], "blockers": [], "open_loops": [], "created_at": stamp})
    store.insert_reflection({"id": "prep-reflection", "persona_id": pid, "period_start": "2026-06-01",
        "period_end": "2026-06-02", "summary": "Routine work", "themes": [], "created_at": stamp})
    store.upsert_digest({"id": "prep-digest", "persona_id": pid, "scope": "month", "period_start": "2026-06-01",
        "period_end": "2026-06-30", "text": "Routine month", "themes": [], "project_arcs": [], "trends": [], "created_at": stamp})
    store.upsert_plan({"id": "prep-plan", "persona_id": pid, "scope": "month", "period_start": "2026-06-01",
        "period_end": "2026-06-30", "sample_days": ["2026-06-01"], "created_at": stamp})
    store.insert_eval_report({"id": "prep-critic", "persona_id": pid, "kind": "llm_critic", "green": True,
        "period_start": "2026-06-01", "period_end": "2026-06-02", "low_dimensions": [], "created_at": stamp})
    store.commit()


def native_examples(persona, store):
    server = original_server()
    examples = []
    def call(name, arguments, scenario=None):
        result = server._tool_manager._tools[name].fn(**arguments)
        assert result["ok"]
        value = result["data"]
        markup, state = TOOLS[name](value)
        assert markup
        examples.append({"scenario": scenario or "preparation-" + name.replace("_", "-"),
                         "tool": name, "input": arguments, "value": value, "state": state})
        return value
    call("list_persona_builds", {"persona_id": persona}, "preparation-builds-empty")
    call("list_persona_context_snapshots", {"persona_id": persona}, "preparation-snapshots-empty")
    call("persona_readiness", {"persona_id": persona})
    assignment = {"persona_id": persona, "task": "Review a transfer", "as_of": "2026-06-02",
                  "required_capability": "login"}
    call("persona_task_readiness", assignment)
    context = call("prepare_persona_for_task", {**assignment, "recent_events": 0})
    call("get_persona_context_snapshot", {"snapshot_id": context["id"]})
    call("list_persona_context_snapshots", {"persona_id": persona})
    build = call("begin_persona_build", {"persona_id": persona, "operation_id": "preparation-fixture", "days": 7})
    call("begin_persona_build", {"persona_id": persona, "operation_id": "preparation-fixture", "days": 7},
         "preparation-build-resumed")
    call("persona_build_step", {"build_id": build["build_id"]})
    call("get_persona_build", {"build_id": build["build_id"]})
    call("list_persona_builds", {"persona_id": persona})
    seed_ready(store, persona, build)
    call("persona_readiness", {"persona_id": persona}, "preparation-structurally-ready")
    call("persona_task_readiness", {**assignment, "required_capability": "walk"}, "preparation-task-ready")
    call("persona_task_readiness", assignment, "preparation-task-capability-blocked")
    call("persona_build_step", {"build_id": build["build_id"]}, "preparation-build-complete")
    call("list_persona_builds", {"persona_id": persona}, "preparation-build-history-complete")
    return examples


@pytest.fixture
def examples(persona, store):
    return native_examples(persona, store)


def select(examples, name):
    return next(item["value"] for item in examples if item["tool"] == name and item["state"] == "ready")


def test_actual_nine_native_tools_render_exact_values_and_export(examples, tmp_path):
    assert {item["tool"] for item in examples} == set(TOOLS)
    sizes = [len(json.dumps({"name": item["tool"], "value": item["value"]}, ensure_ascii=False,
                            separators=(",", ":")).encode()) for item in examples]
    assert max(sizes) <= 8192, sizes
    path = Path(os.environ.get("RESEARCH_PERSONA_PREPARATION_FIXTURE_PATH", tmp_path / "preparation-fixtures.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print(f"Actual native preparation fixtures: {path}; cases={len(examples)}; max public props={max(sizes)}")
    assert select(examples, "persona_build_step")["journal"][0]["tool"] == "preview_persona_update"
    assert select(examples, "prepare_persona_for_task") == select(examples, "get_persona_context_snapshot")
    assert select(examples, "persona_task_readiness")["capability"]["ok"] is False
    by_scenario = {item["scenario"]: item["value"] for item in examples}
    assert by_scenario["preparation-structurally-ready"]["level"] == "ready"
    assert by_scenario["preparation-task-ready"]["ready"] is True
    assert by_scenario["preparation-task-capability-blocked"]["ready"] is False
    complete = by_scenario["preparation-build-complete"]
    assert complete["status"] == "complete" and complete["dispatch"]["kind"] == "done"
    assert len(complete["journal"]) == 2


def test_pure_rendering_never_loads_data_or_recomputes_readiness(examples, monkeypatch):
    from sonaloop import avatar, embeddings, memory
    from sonaloop.web import _components
    # Bootstrap the shared HTML toolkit before denying all I/O.
    for item in examples:
        TOOLS[item["tool"]](item["value"])
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(avatar, "generate_persona_avatar", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(memory, "recall", forbidden)
        patch.setattr(embeddings, "embed_texts", forbidden)
        for name in TOOLS:
            patch.setattr(services, name, forbidden)
        for item in examples:
            assert TOOLS[item["tool"]](item["value"])[1] == item["state"]
    assert examples == before


def test_frozen_snapshot_reopen_does_not_recall_or_reassess(examples, store, monkeypatch):
    from sonaloop import memory
    from sonaloop.services import _persona_lifecycle
    value = select(examples, "prepare_persona_for_task")
    monkeypatch.setattr(memory, "recall", forbidden)
    monkeypatch.setattr(_persona_lifecycle, "persona_task_readiness", forbidden)
    reopened = services.get_persona_context_snapshot(value["id"], store=store)
    assert reopened == value
    markup, state = view.snapshot(reopened)
    assert state == "ready" and value["context_sha256"] in markup
    assert html.escape(value["agent_context"]) in markup
    history = services.list_persona_context_snapshots(value["persona_id"], store=store)
    assert "agent_context" not in history[0] and "task" not in history[0]
    assert value["context_sha256"] in view.snapshots(history)[0]


def test_build_progress_is_supplied_and_dispatch_credentials_never_project(examples):
    value = deepcopy(select(examples, "persona_build_step"))
    secret = "fixture-dispatch-grant-NEVER-VISIBLE"
    value["dispatch"].update(params={"dispatch_token": secret}, execution_grant=secret)
    value["dispatch_token"] = secret
    # The status is not inferred from cursor, counts, a journal word or current readiness.
    value["journal"].append({"cursor": 9, "dispatch_key": "literal-digest", "kind": "done",
                            "tool": "prepare_persona_for_task", "at": "historical time"})
    value["cursor"] = 10
    before = deepcopy(value)
    markup, state = view.build(value)
    assert state == "ready" and "<dd>active</dd>" in markup and "<dd>10</dd>" in markup
    assert secret not in markup and "literal-digest" in markup and "historical time" in markup
    assert value == before and "<button" not in markup and "<a " not in markup
    assert 'class="sl-research-disclosure"' in markup and "<details open" not in markup
    assert markup.index("<dd>active</dd>") < markup.index("<details")


def test_full_context_reference_and_zero_values_survive_in_closed_dom(examples):
    value = deepcopy(select(examples, "prepare_persona_for_task"))
    hostile = '<img src=x onerror="bad()"><a href="javascript:bad()">Full final context</a>'
    value["agent_context"] = hostile * 90 + "END-OF-EXACT-CONTEXT"
    value["loaded_refs"] = [{"kind": "memory", "id": "literal-ref", "anchor": "paragraph-3",
                             "quote": hostile, "score": 0}]
    markup, _ = view.snapshot(value)
    assert "END-OF-EXACT-CONTEXT" in markup and "literal-ref#paragraph-3" in markup
    assert markup.count("Full final context") == 91 and "&lt;img" in markup
    assert "<img" not in markup and "<a " not in markup and "<pre" not in markup
    assert "<dt>score</dt><dd>0</dd>" in markup and "<dd>false</dd>" in markup
    assert "<details open" not in markup


def test_independent_grounding_and_memory_provenance_remain_literal(examples):
    value = next(item["value"] for item in examples if item["scenario"] == "preparation-task-ready")
    assert value["grounding_hits"] and value["recall"]["hits"]
    markup, _ = view.task_readiness(value)
    hit = value["grounding_hits"][0]
    for text in (hit["id"], hit["corpus_id"], hit["text"], "prep-fact-0", "simulated_episode", "unreviewed"):
        assert text in markup
    assert "confidence" in markup and "<dd>0</dd>" in markup
    assert "<button" not in markup and "<a " not in markup


@pytest.mark.parametrize("name,mutate", [
    ("persona_readiness", lambda v: v.update(level="complete")),
    ("persona_readiness", lambda v: v.update(score=True)),
    ("persona_readiness", lambda v: v["counts"].update(events=-1)),
    ("persona_task_readiness", lambda v: v.update(ready="true")),
    ("persona_task_readiness", lambda v: v["capability"]["profile"]["rungs"].update(login=1)),
    ("prepare_persona_for_task", lambda v: v.update(schema="sonaloop.persona_context_snapshot.v0")),
    ("prepare_persona_for_task", lambda v: v.update(context_sha256="bad")),
    ("persona_build_step", lambda v: v.update(status="finished")),
    ("persona_build_step", lambda v: v["journal"].append({"kind": "done"})),
])
def test_malformed_native_fields_fail_before_presentation(examples, name, mutate):
    value = deepcopy(select(examples, name))
    mutate(value)
    with pytest.raises(ValueError):
        TOOLS[name](value)


def test_existing_product_readiness_and_capabilities_markup_is_preserved(persona, store):
    from sonaloop.services._capabilities import capability_profile
    from sonaloop.web.pages import personas
    from sonaloop.web.pages import _persona_preparation as product
    readiness = services.persona_readiness(persona, store=store)
    caps = capability_profile(store.get_persona(persona))
    assert product.readiness_html(readiness) == personas._persona_readiness_html(readiness)
    assert product.capabilities_html(caps) == personas._capabilities_html(caps)
    assert product.capabilities_html({}) == personas._capabilities_html({})
    assert product.readiness_html(readiness).count('id="readiness"') == 1
    assert product.capabilities_html(caps).count('id="caps"') == 1


def test_product_history_and_details_reuse_shared_bodies_without_writes(examples, store, monkeypatch):
    from sonaloop.web.pages import _persona_preparation as product
    app = FastAPI()
    product.register_persona_preparation(app)
    # Topbar/store reads belong to the Product adapter; its layout is not the
    # preparation contract. Keep this test focused on the actual registered route.
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    for name in ("prepare_persona_for_task", "begin_persona_build", "persona_build_step"):
        monkeypatch.setattr(services, name, forbidden)
    context = select(examples, "get_persona_context_snapshot")
    build = services.get_persona_build(select(examples, "get_persona_build")["build_id"], store=store)
    pid = context["persona_id"]
    client = TestClient(app)
    history = client.get(f"/personas/{pid}/preparation")
    assert history.status_code == 200 and context["id"] in history.text and build["build_id"] in history.text
    context_page = client.get(f'/personas/{pid}/preparation/contexts/{context["id"]}')
    build_page = client.get(f'/personas/{pid}/preparation/builds/{build["build_id"]}')
    assert context_page.status_code == build_page.status_code == 200
    assert view.snapshot(context)[0] in context_page.text and view.build(build)[0] in build_page.text


def test_product_detail_rejects_cross_persona_contexts_and_builds(examples, store, monkeypatch):
    from sonaloop.web.pages import _persona_preparation as product
    other = create_persona(store, "Another fixture")
    context = select(examples, "get_persona_context_snapshot")
    build = select(examples, "get_persona_build")
    app = FastAPI()
    product.register_persona_preparation(app)
    monkeypatch.setattr(product, "_missing", lambda store: "Preparation record unavailable")
    client = TestClient(app)
    for suffix in (f'contexts/{context["id"]}', f'builds/{build["build_id"]}'):
        result = client.get(f"/personas/{other}/preparation/{suffix}")
        assert result.text == "Preparation record unavailable" and context["context_sha256"] not in result.text


def test_actual_product_persona_and_preparation_navigation_share_bodies(persona, store, monkeypatch):
    context = services.prepare_persona_for_task(persona, "Inspect the recorded context", recent_events=0, store=store)
    build = services.begin_persona_build(persona, "product-preparation-fixture", days=7, store=store)
    seen = []
    for name in ("readiness_content", "capabilities_content"):
        original = getattr(view, name)
        def observe(*args, _original=original, _name=name, **kwargs):
            markup = _original(*args, **kwargs)
            seen.append((_name, markup, kwargs))
            return markup
        monkeypatch.setattr(view, name, observe)
    for name in ("prepare_persona_for_task", "begin_persona_build", "persona_build_step"):
        monkeypatch.setattr(services, name, forbidden)
    client = TestClient(web.create_app())
    response = client.get(f"/personas/{persona}")
    assert response.status_code == 200
    for name in ("readiness_content", "capabilities_content"):
        assert any(key == name and markup in response.text and "prepared" in kwargs for key, markup, kwargs in seen)
    assert f'href="/personas/{persona}/preparation"' in response.text
    history = client.get(f"/personas/{persona}/preparation")
    assert history.status_code == 200 and context["id"] in history.text and build["build_id"] in history.text
    full_context = client.get(f'/personas/{persona}/preparation/contexts/{context["id"]}')
    assert full_context.status_code == 200 and view.snapshot(context)[0] in full_context.text
    # Repeated nested cards in these read-only views introduce no duplicate
    # Product anchor IDs; the original profile card keeps its existing anchor.
    assert 'id="readiness"' not in view.snapshot(context)[0]


def test_actual_fastmcp_nine_schemas_outputs_and_single_native_execution(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_personas
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema
        assert new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/preparation/v1"
    envelopes = []
    env = _tools_personas._env
    def capture(*args, **kwargs):
        value = env(*args, **kwargs)
        envelopes.append(deepcopy(value))
        return value
    monkeypatch.setattr(_tools_personas, "_env", capture)
    for name in TOOLS:
        item = next(item for item in examples if item["tool"] == name and item["state"] == "ready")
        calls = []
        native = getattr(services, name)
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
        assert result.meta["sonaloop/presentation"]["state"] == "ready"
        assert result.meta["sonaloop/presentation"]["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()

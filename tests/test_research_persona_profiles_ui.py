"""Native profile receipts and actual Product seams, without providers/media."""
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

from conftest import make_profile
from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import persona_profiles as views, persona_profile_rows as rows


TOOLS = {"record_persona": views.profile, "update_persona": views.profile,
    "get_persona": views.detail, "get_persona_soul": views.soul,
    "list_personas": views.profiles, "query_personas": views.queried}


def forbidden(*args, **kwargs):
    pytest.fail("Profile presentation attempted authoring, media, file or network access")


@pytest.fixture(autouse=True)
def no_providers(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_personas, _tools_substrate
    server = FastMCP("native-profile-fixture")
    _tools_personas.register_personas(server)
    _tools_substrate.register_substrate(server)
    return server


@pytest.fixture
def examples(store):
    server, cases = original_server(), []
    def call(tool, arguments, scenario):
        result = server._tool_manager._tools[tool].fn(**arguments)
        assert result["ok"]
        markup, state = TOOLS[tool](result["data"])
        assert markup
        cases.append({"scenario": scenario, "tool": tool, "input": arguments, "value": result["data"], "state": state})
        return result["data"]
    call("list_personas", {}, "profiles-empty")
    call("query_personas", {"q": "missing"}, "profiles-query-empty")
    native = make_profile("Morgan Lee", title="Operations lead", goals=["Keep handovers clear"], pains=["Late supplier replies"])
    first = call("record_persona", {"description": "Synthetic operations lead profile", "profile": native,
        "generate_avatar": False}, "profiles-recorded")
    pid = first["id"]
    call("get_persona", {"persona_id": pid}, "profiles-get-empty-history")
    call("update_persona", {"persona_id": pid, "patch": {"goals": ["Keep handovers clear", "Protect focus time"]},
        "reason": "Host-authored synthetic goals"}, "profiles-updated")
    call("get_persona_soul", {"persona_id": pid}, "profiles-soul")
    # Returned native history is seeded data, not a claim simulation/provider ran.
    store.insert_calendar_event({"id": "calendar_profile", "persona_id": pid, "start": "2026-04-03T09:00:00",
        "end": "2026-04-03T09:30:00", "title": "Review supplier replies", "block_type": "focus"})
    store.insert_experience_event({"id": "event_profile", "persona_id": pid, "timestamp": "2026-04-03T09:00:00",
        "event_type": "focus", "summary": "Compared the received handover notes", "task": "Review replies",
        "tool": "Email", "collaboration_mode": "solo", "mood": "focused", "thought": "Keep the next owner clear",
        "pain_point": "", "follow_up": "", "entities": [],
        "details": {"completed": True, "interruptions": 0}})
    store.upsert_daily_summary({"id": "day_profile", "persona_id": pid, "date": "2026-04-03", "summary": "Protected a review period"})
    store.insert_reflection({"id": "reflection_profile", "persona_id": pid, "period_start": "2026-04-03",
        "period_end": "2026-04-03", "summary": "Clear handovers reduced follow-up"})
    store.upsert_pain_point({"id": "pain_profile", "persona_id": pid, "issue": "Repeated supplier follow-ups",
        "severity": 2, "frequency": 1, "affected_workflow": "Handover", "opportunity": "Clarify the next owner", "evidence_event_ids": ["event_profile"]})
    store.conn.commit()
    call("get_persona", {"persona_id": pid}, "profiles-get-history")
    call("record_persona", {"description": "Second independent synthetic profile", "profile": make_profile("Riley Quinn"),
        "generate_avatar": False}, "profiles-second-record")
    page = call("list_personas", {"limit": 1}, "profiles-list-first")
    call("list_personas", {"limit": 1, "cursor": page["next_cursor"]}, "profiles-list-next")
    call("list_personas", {"limit": 1, "compact": False}, "profiles-list-full")
    call("query_personas", {"limit": 1}, "profiles-query-first")
    call("query_personas", {"limit": 1, "offset": 1}, "profiles-query-next")
    return cases


def test_actual_six_native_results_and_fixture_export(examples, tmp_path):
    assert {row["tool"] for row in examples} == set(TOOLS)
    path = Path(os.environ.get("RESEARCH_PROFILE_FIXTURE_PATH", tmp_path / "profiles.json"))
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    sizes = {row["scenario"]: len(json.dumps({"name": row["tool"], "value": row["value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for row in examples}
    print("Profile native fixtures:", path, "sizes:", sizes)


def test_pure_profiles_never_probe_media_read_files_or_call_tools(examples, monkeypatch):
    from sonaloop.web import _components
    before = deepcopy(examples)
    monkeypatch.setattr(Store, "__init__", forbidden)
    monkeypatch.setattr(_components, "_avatar", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    for name in TOOLS:
        monkeypatch.setattr(services, name, forbidden)
    for row in examples:
        markup, state = TOOLS[row["tool"]](row["value"])
        assert markup and state == row["state"]
        assert "<img" not in markup and "<button" not in markup and "<input" not in markup
    assert examples == before


def test_complete_history_and_unloaded_media_are_truthful(examples):
    row = next(row for row in examples if row["scenario"] == "profiles-get-history")
    value = deepcopy(row["value"])
    value["persona"]["avatar"] = {"path": "/unread/portrait.png", "sha256": "fixture-reference"}
    markup, _ = views.detail(value)
    assert "fixture-reference" in markup and "<img" not in markup
    for key in ("calendar_events", "experience_events", "daily_summaries", "pain_points", "reflections"):
        assert all(item["id"] in markup for item in value[key])
    assert "<dt>interruptions</dt><dd><span>0</span>" in markup
    assert "<details open" not in markup


def test_profile_strings_escape_and_private_grants_stay_out_of_dom(examples):
    value = deepcopy(next(row["value"] for row in examples if row["tool"] == "record_persona"))
    hostile = '<img src=x onerror="bad()"><script>Untrusted profile</script>'
    value["display_name"] = hostile
    value["relationships"][0]["friction"] = hostile
    value["provenance"] = {"source": hostile, "approval_token": "must-stay-private"}
    before = deepcopy(value)
    markup, _ = views.profile(value)
    assert html.escape(hostile) in markup and "<img" not in markup and "<script" not in markup
    assert "must-stay-private" not in markup and value == before


@pytest.mark.parametrize("mutate", [lambda v: v.update(id=""), lambda v: v.update(goals="goal"),
    lambda v: v.update(role={"title": 1}), lambda v: v["relationships"][0].update(friction=False)])
def test_malformed_profiles_cannot_claim_success(examples, mutate):
    value = deepcopy(next(row["value"] for row in examples if row["tool"] == "record_persona"))
    mutate(value)
    with pytest.raises(ValueError):
        views.profile(value)


def test_existing_product_sections_and_list_use_shared_pure_bodies(examples, store, monkeypatch):
    from sonaloop.web import _routes_lists
    from sonaloop.web._components import _hero, _pills
    from sonaloop.web._routes_lists import _row
    value = next(row["value"] for row in examples if row["tool"] == "record_persona")
    from sonaloop.web._html import h, raw
    assert rows.heading(value) == _hero(value["display_name"], sub=rows.subtitle(value))
    assert rows.list_section("Goals", value["goals"], section_id="ziele", fallback=True) == h("div",
        {"class_": "sec", "id": "ziele", "data-persona-surface-fallback": True}, h("h2", {}, "Goals"), raw(_pills(value["goals"])))
    assert rows.profile_row(value, prepared={"avatar": "A", "right": "R", "actions": "X"}) == _row(
        f'/personas/{value["id"]}', "A", value["display_name"], "R", sub=value["role"]["title"], actions="X")
    calls = []
    original = rows.profile_row
    def observe(*args, **kwargs):
        calls.append(kwargs);return original(*args, **kwargs)
    monkeypatch.setattr(rows, "profile_row", observe)
    assert value["display_name"] in _routes_lists._persona_row(value, store)
    assert calls and set(calls[-1]["prepared"]) == {"avatar", "right", "actions"}
    page = TestClient(web.create_app()).get(f'/personas/{value["id"]}')
    assert page.status_code == 200 and rows.relationships_content(value["relationships"]) in page.text
    assert f'/personas/{value["id"]}/profile' in page.text


def test_explicit_product_profile_and_soul_use_only_existing_getters(examples, monkeypatch):
    from sonaloop.web.pages import _persona_profiles
    pid = next(row["value"]["id"] for row in examples if row["tool"] == "record_persona")
    app = FastAPI();_persona_profiles.register_persona_profiles(app)
    monkeypatch.setattr(_persona_profiles, "_layout", lambda title, body, *args, **kwargs: str(body))
    for name in ("record_persona", "update_persona", "generate_persona_surface_avatar", "prepare_persona_for_task"):
        monkeypatch.setattr(services, name, forbidden)
    client = TestClient(app)
    assert views.detail(services.get_persona(pid))[0] in client.get(f'/personas/{pid}/profile').text
    assert views.soul(services.get_persona_soul(pid))[0] in client.get(f'/personas/{pid}/soul').text
    assert client.get('/personas/missing/profile').status_code == 404
    assert client.get('/personas/missing/soul').status_code == 404


def test_decorated_profile_tools_preserve_native_output_and_register_shared_resource(examples, monkeypatch):
    from sonaloop.mcp_server import build_server
    from sonaloop.ui_components.registry import SURFACES
    mcp = build_server(); original = original_server()
    for name in TOOLS:
        assert SURFACES[name].uri == "ui://sonaloop/profiles/v1"
        target = mcp._tool_manager._tools[name]
        assert target.parameters == original._tool_manager._tools[name].parameters
        assert target.description == original._tool_manager._tools[name].description
    for row in examples:
        # Pagination is performed in the list_personas MCP handler itself;
        # its real native page is already exercised by the fixture above.
        if row["tool"] == "list_personas":
            continue
        calls = []
        def native(*args, **kwargs):
            calls.append((args, kwargs));return deepcopy(row["value"])
        with monkeypatch.context() as patch:
            patch.setattr(services, row["tool"], native)
            result = asyncio.run(mcp.call_tool(row["tool"], row["input"]))
        assert len(calls) == 1
        assert result.structuredContent["data"] == row["value"]
        text = "\n".join(block.text for block in result.content)
        assert hashlib.sha256(text.encode()).hexdigest() == result.meta["sonaloop/presentation"]["text_sha256"]

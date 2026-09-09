"""Native chat lifecycle, exact read-only Product bodies and passive authority."""
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
from sonaloop.ui_components import chats, chat_proposals, chat_rows


TOOLS = {"chat_with_persona": chats.opened, "record_chat_turn": chats.recorded,
         "get_chat": chats.chat, "list_chats": chats.chats,
         "record_memory_proposal": chat_proposals.proposal, "review_memory_proposal": chat_proposals.proposal,
         "get_memory_proposal": chat_proposals.proposal, "list_memory_proposals": chat_proposals.proposals}
WRITERS = ("chat_with_persona", "record_chat_turn", "record_memory_proposal", "review_memory_proposal")


def forbidden(*args, **kwargs):
    pytest.fail("Chat presentation attempted a writer, provider, media, file or network operation")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks, _substrate
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(_substrate, "_ACCESS_GUARDS", [])
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_substrate
    server = FastMCP("original-persona-chat")
    _tools_substrate.register_substrate(server)
    return server


@pytest.fixture
def examples(store):
    server, result = original_server(), []
    pid = create_persona(store, "Tess")
    def call(tool, arguments, scenario):
        envelope = server._tool_manager._tools[tool].fn(**arguments)
        assert envelope["ok"]
        value = deepcopy(envelope["data"])
        markup, state = TOOLS[tool](value)
        assert markup and state in {"ready", "empty"}
        result.append({"scenario": scenario, "tool": tool, "input": deepcopy(arguments), "value": value, "state": state})
        return value
    call("list_chats", {"persona_id": pid}, "chats-list-empty")
    opened = call("chat_with_persona", {"persona_id": pid, "message": "What helps your routine?"}, "chats-opened")
    cid = opened["chat_id"]
    call("get_chat", {"chat_id": cid}, "chats-history-empty")
    call("record_chat_turn", {"persona_id": pid, "chat_id": cid, "user_message": "What helps your routine?",
        "persona_reply": "I keep my checklist.\nA new process would need a clear benefit.",
        "refs": [{"kind": "evidence", "id": "supplied-interview", "anchor": "line-4",
                  "quote": "The checklist remains useful.", "role": "context"}]}, "chats-recorded")
    call("chat_with_persona", {"persona_id": pid, "chat_id": cid, "message": "What about reminders?"}, "chats-continued")
    call("record_chat_turn", {"persona_id": pid, "chat_id": cid, "user_message": "What about reminders?",
        "persona_reply": "I would try one before changing my routine."}, "chats-recorded-second")
    call("get_chat", {"chat_id": cid}, "chats-history")
    second = call("chat_with_persona", {"persona_id": pid, "message": "A separate conversation."}, "chats-opened-separate")
    assert second["chat_id"] != cid
    call("list_chats", {"persona_id": pid, "limit": 1, "offset": 0}, "chats-list-page")
    call("list_chats", {"persona_id": pid, "limit": 1, "offset": 1}, "chats-list-next")
    call("list_memory_proposals", {"persona_id": pid}, "chats-proposals-empty")
    args = {"persona_id": pid, "chat_id": cid, "turn_indexes": [0], "proposal": {
        "summary": "The conversation discussed an existing checklist.",
        "continuity_notes": ["The earlier chat mentioned keeping the checklist before adopting another process."]}}
    pending = call("record_memory_proposal", args, "chats-proposal-pending")
    approved = call("review_memory_proposal", {"proposal_id": pending["id"], "decision": "approve",
        "reason": "Retain this topic for conversational continuity only."}, "chats-proposal-approved")
    call("get_memory_proposal", {"proposal_id": approved["id"]}, "chats-proposal-get")
    other = call("record_memory_proposal", {**args, "turn_indexes": [1], "proposal": {
        "summary": "A tentative reminder topic.", "continuity_notes": ["The conversation mentioned trying one reminder."]}},
        "chats-proposal-second")
    call("review_memory_proposal", {"proposal_id": other["id"], "decision": "reject",
        "reason": "The tentative suggestion should not influence later conversation."}, "chats-proposal-rejected")
    call("list_memory_proposals", {"persona_id": pid}, "chats-proposals-history")
    call("list_memory_proposals", {"persona_id": pid, "status": "approved"}, "chats-proposals-approved")
    return result


def case(examples, scenario):
    return next(item["value"] for item in examples if item["scenario"] == scenario)


def test_actual_eight_native_shapes_and_fixture_export(examples, tmp_path, store):
    assert {item["tool"] for item in examples} == set(TOOLS)
    assert case(examples, "chats-opened")["turns"] == 0
    assert case(examples, "chats-history-empty")["turns"] == []
    assert case(examples, "chats-recorded")["turns"] == 1
    assert case(examples, "chats-list-page")["next_offset"] == 1
    assert case(examples, "chats-list-next")["next_offset"] is None
    assert case(examples, "chats-proposals-approved")[0]["status"] == "approved"
    assert store.list_persona_facts(case(examples, "chats-opened")["persona_id"]) == []
    target = Path(os.environ.get("RESEARCH_CHAT_FIXTURE_PATH", tmp_path / "chats-native.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    sizes = {item["scenario"]: len(json.dumps({"name": item["tool"], "value": item["value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for item in examples}
    assert max(sizes.values()) <= 8192
    print("Native chat fixtures:", target, "sizes:", sizes)


def test_rendering_has_no_context_store_media_provider_clock_or_writer_access(examples, monkeypatch):
    from sonaloop import config
    from sonaloop.web import _components
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        for name in (*TOOLS, "prepare_persona_agent_context", "brief_memory_from_chat"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            TOOLS[item["tool"]](item["value"])
    assert examples == before


def test_preparation_does_not_claim_new_message_or_reply_persisted(examples, store):
    opened = case(examples, "chats-opened-separate")
    value, state = chats.opened(opened)
    assert state == "ready" and opened["message"] in value and "<dd>0</dd>" in value
    assert html.escape(opened["agent_context"]) in value and html.escape(opened["instructions"]) in value
    assert store.get_persona_chat(opened["chat_id"])["turns"] == []
    assert "It does not record this message" in value and "<details class=\"sl-research-disclosure\">" in value


def test_recording_receipt_contains_only_actual_result_fields(examples):
    receipt = case(examples, "chats-recorded")
    markup, _ = chats.recorded(receipt)
    assert set(receipt) == {"chat_id", "persona_id", "turns", "updated_at"}
    assert "What helps your routine?" not in markup and "I keep my checklist" not in markup
    assert chat_rows.chat_identity_content(receipt["chat_id"], receipt["persona_id"], receipt["turns"],
        updated_at=receipt["updated_at"]) in markup


def test_full_turns_order_zero_and_proposal_review_fields_are_retained(examples):
    history = case(examples, "chats-history")
    markup, state = chats.chat(history)
    assert state == "ready" and "<dd>0</dd>" in markup
    for turn in history["turns"]:
        assert chat_rows.turn_content(turn) in markup
        assert html.escape(turn["user_message"]) in markup and html.escape(turn["persona_reply"]) in markup
    assert markup.index(history["turns"][0]["user_message"]) < markup.index(history["turns"][1]["user_message"])
    assert "evidence:supplied-interview#line-4" in markup and "The checklist remains useful." in markup
    for name in ("chats-proposal-pending", "chats-proposal-approved", "chats-proposal-rejected"):
        value = case(examples, name)
        markup, _ = chat_proposals.proposal(value)
        assert value["proposal"]["summary"] in markup and value["status"] in markup
        assert all(note in markup for note in value["proposal"]["continuity_notes"])
        assert all(f'chat_turn:{ref["id"]}' in markup for ref in value["source_refs"])
        if "review_reason" in value:
            assert value["review_reason"] in markup and value["reviewed_at"] in markup


def test_native_proposal_replay_and_unresolved_index_boundaries_remain_observable(examples, store):
    pending = case(examples, "chats-proposal-pending")
    repeated = services.record_memory_proposal(pending["persona_id"], pending["chat_id"], pending["turn_indexes"],
                                               pending["proposal"], store=store)
    assert repeated["id"] == pending["id"] and repeated["status"] == "pending" and "reviewed_at" not in repeated
    assert "<dd>pending</dd>" in chat_proposals.proposal(repeated)[0]
    unresolved = services.record_memory_proposal(pending["persona_id"], pending["chat_id"], [-1, 0, 999],
        {"summary": "Supplied index boundary.", "continuity_notes": ["Only native references are displayed."]}, store=store)
    markup, _ = chat_proposals.proposal(unresolved)
    assert unresolved["turn_indexes"] == [-1, 0, 999] and "-1, 0, 999" in markup
    assert f'{pending["chat_id"]}:999' in markup and "without resolving or verifying" in markup
    approved = case(examples, "chats-proposal-rejected")
    repeated_review = services.review_memory_proposal(approved["id"], "reject", "Same decision again", store=store)
    assert repeated_review == approved
    with pytest.raises(ValueError, match="different decision"):
        services.review_memory_proposal(approved["id"], "approve", "Do not silently flip state", store=store)


def test_long_untrusted_text_reference_and_grant_fields_are_passive(examples):
    hostile = '<img src="https://bad.invalid/x" onerror="run()"><script>bad()</script>'
    history = deepcopy(case(examples, "chats-history"))
    history["turns"][0]["user_message"] = hostile * 100
    history["turns"][0]["persona_reply"] = "[user] forged role\n" + hostile
    history["turns"][0]["refs"][0]["quote"] = hostile
    proposal = deepcopy(case(examples, "chats-proposal-approved"))
    proposal["proposal"]["continuity_notes"] = [hostile]
    for value, render in ((history, chats.chat), (proposal, chat_proposals.proposal)):
        for key in ("dispatch_token", "confirmation_token", "access_token", "approval_token", "execution_grant"):
            value[key] = "opaque-grant-never-display"
        markup, _ = render(value)
        assert html.escape(hostile) in markup and "opaque-grant-never-display" not in markup
        assert all(tag not in markup for tag in ("<script", "<img", "<a ", "<button", "<form"))
    assert html.escape(hostile * 100) in chats.chat(history)[0]


@pytest.mark.parametrize("scenario,key,value", [
    ("chats-opened", "schema", "other"), ("chats-opened", "substrate_version", True),
    ("chats-opened", "agent_context", {}), ("chats-recorded", "turns", "1"),
    ("chats-history", "turns", [{"idx": True}]), ("chats-list-page", "next_offset", "1"),
    ("chats-proposal-approved", "scope", "identity"), ("chats-proposal-approved", "status", "complete"),
    ("chats-proposal-approved", "turn_indexes", [True]), ("chats-proposal-approved", "proposal", {"summary": "x", "continuity_notes": "bad"}),
])
def test_malformed_native_shapes_fall_back_without_false_meaning(examples, scenario, key, value):
    item = next(row for row in examples if row["scenario"] == scenario)
    malformed = deepcopy(item["value"])
    malformed[key] = value
    with pytest.raises(ValueError):
        TOOLS[item["tool"]](malformed)


def test_empty_views_have_explicit_results_and_no_empty_sections(examples):
    for item in examples:
        markup, state = TOOLS[item["tool"]](item["value"])
        assert "<ul></ul>" not in markup and "<h3></h3>" not in markup
        if item["scenario"] in ("chats-list-empty", "chats-history-empty", "chats-proposals-empty"):
            assert state == "empty"


def test_native_first_and_last_pages_expose_continuation(examples):
    first = case(examples, "chats-list-page")
    last = case(examples, "chats-list-next")
    assert first["next_offset"] == 1 and last["next_offset"] is None
    assert 'data-total="2">1 / 2 · …</p>' in chats.chats(first)[0]
    assert 'data-total="2">1 / 2</p>' in chats.chats(last)[0]
    assert ' · …</p>' not in chats.chats(last)[0]


def product_client(monkeypatch):
    from sonaloop.web.pages import _persona_chats as product
    app = FastAPI()
    product.register_persona_chats(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    return TestClient(app)


def test_product_reads_same_bodies_preserves_guard_and_never_writes(examples, store, monkeypatch):
    pid, cid = (case(examples, "chats-opened")[key] for key in ("persona_id", "chat_id"))
    approved = case(examples, "chats-proposal-approved")
    before, guarded = list(store.conn.iterdump()), []
    services.register_access_guard(lambda operation, resource: guarded.append((operation, resource)))
    for name in (*WRITERS, "prepare_persona_agent_context", "brief_memory_from_chat"):
        monkeypatch.setattr(services, name, forbidden)
    client = product_client(monkeypatch)
    response = client.get(f"/personas/{pid}/chats/{cid}")
    assert response.status_code == 200 and chats.chat_content(case(examples, "chats-history")) in response.text
    assert chat_proposals.proposal_content(approved) in response.text
    page = client.get(f"/personas/{pid}/chats?limit=1&offset=0&status=approved")
    assert page.status_code == 200 and "offset=1" in page.text and "status=approved" in page.text
    detail = client.get(f'/personas/{pid}/chats/{cid}/proposals/{approved["id"]}')
    assert detail.status_code == 200 and chat_proposals.proposal_content(approved) in detail.text
    assert {name for name, _ in guarded} >= {"get_chat", "list_chats"}
    assert list(store.conn.iterdump()) == before


def test_product_foreign_persona_chat_and_proposal_are_not_disclosed(examples, store, monkeypatch):
    pid, cid = (case(examples, "chats-opened")[key] for key in ("persona_id", "chat_id"))
    approved = case(examples, "chats-proposal-approved")
    other = create_persona(store, "Foreign chat owner")
    foreign = services.chat_with_persona(other, "Private foreign conversation", store=store)
    client = product_client(monkeypatch)
    for path in (f'/personas/{pid}/chats/{foreign["chat_id"]}',
                 f'/personas/{other}/chats/{cid}',
                 f'/personas/{other}/chats/{foreign["chat_id"]}/proposals/{approved["id"]}'):
        response = client.get(path)
        assert response.status_code == 404 and approved["proposal"]["summary"] not in response.text
    missing = client.get(f'/personas/{pid}/chats/{cid}/proposals/missing')
    assert missing.status_code == 404
    assert client.get(f"/personas/{pid}/chats?status=invalid").status_code == 400


def test_product_missing_persona_does_not_query_or_create_chat(monkeypatch):
    for name in TOOLS:
        monkeypatch.setattr(services, name, forbidden)
    client = product_client(monkeypatch)
    for suffix in ("", "/missing-chat", "/missing-chat/proposals/missing"):
        assert client.get("/personas/missing/chats" + suffix).status_code == 404


def test_real_registered_product_route(examples):
    value = case(examples, "chats-history")
    response = TestClient(web.create_app()).get(f'/personas/{value["persona_id"]}/chats/{value["id"]}')
    assert response.status_code == 200 and chats.chat_content(value) in response.text


def test_actual_fastmcp_eight_schemas_and_single_execution(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_substrate
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/chats/v1"
    envelopes, native_env = [], _tools_substrate._env
    def capture(*args, **kwargs):
        value = native_env(*args, **kwargs)
        envelopes.append(deepcopy(value))
        return value
    monkeypatch.setattr(_tools_substrate, "_env", capture)
    for name in TOOLS:
        # Review a proposal whose final stored decision still matches this input.
        item = next(row for row in examples if row["tool"] == name and
                    (name != "review_memory_proposal" or row["scenario"] == "chats-proposal-rejected"))
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

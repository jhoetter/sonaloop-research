"""Actual Product Understanding natives, shared Product content and passive safety."""
import asyncio
import base64
import builtins
from copy import deepcopy
import html
from io import BytesIO
import json
import os
from pathlib import Path
import socket

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from sonaloop import config, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import product_understanding as ui
from sonaloop.ui_components import product_understanding_rows as rows


TOOLS = {"record_product_understanding": (ui.recorded, ui.recorded_view),
    "record_manifest_product_understanding": (ui.recorded, ui.recorded_view),
    "get_product_understanding": (ui.stored, ui.stored_view)}


def forbidden(*args, **kwargs):
    pytest.fail("Product Understanding presentation attempted source access or execution")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)
    token = config.set_request_tenant_scope(["understanding-workspace"], "understanding-workspace")
    try:
        yield
    finally:
        config.reset_request_tenant_scope(token)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_plan
    server = FastMCP("original-product-understanding")
    _tools_plan.register_plan(server)
    return server


def screen_bytes():
    out = BytesIO()
    Image.new("RGB", (32, 20), (40, 90, 140)).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


@pytest.fixture
def examples(store):
    server, result = original_server(), []
    def call(name, arguments, scenario):
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"], envelope
        value = deepcopy(envelope["data"])
        public = TOOLS[name][1](value)
        markup, state = TOOLS[name][0](value)
        assert ui.render_view(public) == (markup, state)
        result.append({"scenario": scenario, "tool": name, "input": deepcopy(arguments),
            "value": value, "public_value": public, "state": state})
        return value

    project = services.start_project("Product example", "Inspect the supplied state", persona_ids=[], store=store)
    pid = project["id"]
    asset = services.attach_asset(pid, content_base64=screen_bytes(), filename="home.png", kind="screenshot", store=store)
    ref = {"kind": "asset", "id": asset["id"], "anchor": "screen:0", "quote": "Home overview",
        "text": "An exact synthetic screen", "role": "Visible state"}
    args = {"project_id": pid, "target": {"name": "Handover product", "identity": "synthetic-product",
        "url": "https://example.test/handover", "role": "target_identity_only", "identity_only": True,
        "is_evidence": False, "server_fetch_authorized": False}, "revision": "release:1",
        "routes": [{"path": "/", "label": "Overview", "evidence_refs": [ref]}],
        "flows": [{"name": "Handover overview", "evidence_refs": [ref]}],
        "states": [{"state": "idle", "evidence_refs": [ref]}],
        "capabilities": [{"key": "handover", "claim": "A handover control is visible.",
            "status": "observed_present", "evidence_refs": [ref]},
            {"key": "save", "claim": "Saving after handover is not shown.", "status": "unknown"}],
        "evidence_refs": [ref], "observed_at": "2026-09-09T08:00:00Z", "key": "understanding:first"}
    first = call("record_product_understanding", args, "understanding-recorded")
    call("record_product_understanding", args, "understanding-replayed")
    args = deepcopy(args)
    args.update(revision="release:2", observed_at="2026-09-09T08:10:00Z", key="understanding:second")
    args["capabilities"][0].update(claim="The handover control is absent in the captured state.",
        status="observed_absent", verification_attempt={"procedure": "Inspected the complete captured home state",
        "description": "The control was not visible.", "attempts": 0, "completed": False},
        revision_reason="A later captured revision has no handover control.")
    args["capabilities"].append({"claim": "A downstream handover may require another screen.",
        "status": "inferred", "evidence_refs": [ref]})
    call("record_product_understanding", args, "understanding-revised")
    call("get_product_understanding", {"project_id": pid}, "understanding-history")
    call("get_product_understanding", {"project_id": pid, "version_id": first["id"]}, "understanding-historical")

    project = services.start_project("Frozen screenshot example", "Understand the exact page",
        methodology="Reaction Test", persona_ids=[], operation_id="understanding:bounded-project", store=store)
    pid = project["id"]
    run = services.start_run(pid, operation_id="understanding:bounded-run", store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    token = dispatch["dispatch_token"]
    asset = services.admit_remote_screenshot(pid, run["run_id"], "understanding:screen", screen_bytes(),
        "screen.png", "image/png", "2026-09-09T08:20:00Z", "release:3", label="Overview",
        dispatch_token=token, store=store)
    action = services.run_step(run["run_id"], store=store)["blocking_action"]
    services.record_reaction_test_capture_review(pid, True,
        [{"asset_version_id": asset["id"], "role": "Overview under test"}], [],
        "Limited to the captured overview state.", action["next_call"]["arguments"]["operation_id"], token, store=store)
    manifest = services.record_flow_manifest(pid, run["run_id"], "understanding:manifest", "primary", "Overview flow",
        [{"asset_version_id": asset["id"], "label": "Overview"}], "Understand the exact page", "release:3",
        "2026-09-09T08:20:00Z", dispatch_token=token, store=store)
    services.inspect_reaction_test_screen(pid, manifest["id"], 0, asset["id"], token, store=store)
    args = {"project_id": pid, "manifest_id": manifest["id"],
        "observations": [{"step_index": 0, "visible_observation": "The screen presents an overview."}],
        "unknown_capabilities": ["Behavior after selection is not visible."], "target_name": "Example product",
        "target_url": "https://example.test/overview", "dispatch_token": token}
    call("record_manifest_product_understanding", args, "understanding-bounded")
    call("record_manifest_product_understanding", args, "understanding-bounded-replayed")
    call("get_product_understanding", {"project_id": pid}, "understanding-bounded-history")
    return result


def case(examples, name):
    return next(item for item in examples if item["scenario"] == name)


def test_actual_three_native_results_closed_public_equivalence_and_fixture_export(examples, tmp_path):
    from jsonschema import Draft202012Validator
    assert {item["tool"] for item in examples} == set(TOOLS)
    for item in examples:
        assert ui.render_view(item["public_value"]) == TOOLS[item["tool"]][0](item["value"])
        Draft202012Validator(ui.public_schema(item["public_value"]["view"])).validate(item["public_value"])
        assert len(json.dumps({"name": item["tool"], "value": item["public_value"]},
            ensure_ascii=False, separators=(",", ":")).encode()) <= 8192
    target = Path(os.environ.get("RESEARCH_UNDERSTANDING_FIXTURE_PATH", tmp_path / "understanding.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Native Product Understanding fixtures:", target, "count:", len(examples))


def test_native_replay_history_and_bounded_authority_remain_actual(examples, store):
    first = case(examples, "understanding-recorded")["value"]
    replay = case(examples, "understanding-replayed")["value"]
    assert first["id"] == replay["id"] and replay["idempotent_replay"] is True
    assert first["dispatch"]["checkpointed"] is False
    current = case(examples, "understanding-history")["value"]
    historical = case(examples, "understanding-historical")["value"]
    assert len(current["history"]) == 2 and historical["id"] == first["id"]
    assert current["supersedes"] == first["id"]
    assert all(set(row) == {"id", "version", "revision", "observed_at", "supersedes"} for row in current["history"])
    bounded = case(examples, "understanding-bounded-replayed")["value"]
    assert bounded["dispatch"]["checkpointed"] is True and bounded["dispatch"]["receipt"]["deduplicated"] is True
    assert bounded["bounded_authoring"]["served_steps"] == [0]
    assert bounded["bounded_authoring"]["url_role"] == "target_identity_only"
    assert bounded["stimulus_manifest"]["manifest_version"] == 1
    assert bounded["coverage_checklist"][0]["status"] == "served_to_host"
    markup = ui.recorded(bounded)[0]
    for key in ("manifest_digest", "target_revision", "expected_task", "captured_at"):
        assert bounded["stimulus_manifest"][key] in markup
    assert "<dd>0</dd>" in markup and "served_to_host" in markup
    assert len(services.get_product_understanding(bounded["project_id"], store=store)["history"]) == 1
    markup = ui.stored(current)[0]
    assert "conflict" not in markup.lower() and "<dd>false</dd>" in markup and "<dd>0</dd>" in markup
    changed = deepcopy(case(examples, "understanding-recorded")["input"])
    changed["revision"] = "different-retry-content"
    with pytest.raises(Exception, match="PRODUCT_UNDERSTANDING_IDEMPOTENCY_CONFLICT"):
        services.record_product_understanding(**changed, store=store)
    assert len(services.get_product_understanding(first["project_id"], store=store)["history"]) == 2


def test_native_references_and_every_scalar_target_qualification_are_retained(examples):
    value = case(examples, "understanding-recorded")["value"]
    view = ui.recorded_view(value)["value"]
    assert {row["name"]: row["value"] for row in view["target"]["attributes"]} == value["target"]
    assert view["evidence_refs"] == value["evidence_refs"]
    markup = ui.recorded(value)[0]
    for field in ("identity_only", "is_evidence", "server_fetch_authorized", "target_identity_only"):
        assert field in markup
    assert "<dd>true</dd>" in markup and "<dd>false</dd>" in markup
    for key, text in value["evidence_refs"][0].items():
        assert html.escape(text) in markup
    assert all(tag not in markup for tag in ("<a ", "<img", "<script", "<button", "<form", "<pre"))
    assert ' open' not in markup and markup.count('<h2>Product Understanding</h2>') == 1


def test_exact_context_exclusions_do_not_mutate_native_or_erase_domain_prose(examples):
    value = deepcopy(case(examples, "understanding-bounded")["value"])
    markers = []
    for record, key in ((value, "operation_id"), (value, "operation_fingerprint"),
        (value["dispatch"], "operation_id"), (value["dispatch"]["receipt"], "key")):
        record[key] = marker = "EXCLUDED-CONTEXT-" + str(len(markers))
        markers.append(marker)
    value["target"]["operation_id"] = "A supplied target attribute, not execution scope"
    value["capabilities"][0]["claim"] = "The words dispatch_token and receipt.key are source prose."
    before = deepcopy(value)
    public = ui.recorded_view(value)
    markup = ui.render_view(public)[0]
    assert all(marker not in json.dumps(public) + markup for marker in markers)
    assert value == before and value["target"]["operation_id"] in markup
    assert value["capabilities"][0]["claim"] in markup


def test_passive_rendering_has_no_source_time_icon_or_native_access(examples, monkeypatch):
    from sonaloop.web import _render, _components, ui as web_ui
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(builtins, "open", forbidden)
        for name in ("read_text", "read_bytes", "exists", "open"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(_render, "render_ref", forbidden)
        patch.setattr(_components, "_icon", forbidden)
        patch.setattr(web_ui, "local_ts", forbidden)
        for name in (*TOOLS, "run_step", "inspect_reaction_test_screen", "record_flow_manifest", "start_project"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            assert TOOLS[item["tool"]][0](item["value"]) == ui.render_view(item["public_value"])
    assert examples == before


def test_public_schema_closed_and_malformed_native_fails_truthfully(examples):
    from jsonschema import Draft202012Validator
    view = deepcopy(case(examples, "understanding-bounded")["public_value"])
    for node in (view, view["value"], view["value"]["target"], view["value"]["capabilities"][0],
        view["value"]["dispatch"], view["value"]["dispatch"]["receipt"], view["value"]["stimulus_manifest"],
        view["value"]["coverage_checklist"][0], view["value"]["evidence_refs"][0]):
        node["unexpected"] = "closed"
        assert not Draft202012Validator(ui.public_schema("record")).is_valid(view)
        with pytest.raises(ValueError):
            ui.render_view(view)
        del node["unexpected"]
    with pytest.raises(ValueError):
        ui.render_view(case(examples, "understanding-bounded")["value"])
    for bad in ({}, None, [], {"target": "not an object"}):
        with pytest.raises(ValueError):
            ui.recorded(bad)
    for bad in ({"view": []}, {"view": {}}, {"view": None}):
        with pytest.raises(ValueError):
            ui.render_view(bad)


def test_untrusted_long_values_are_escaped_without_truncation(examples):
    value = deepcopy(case(examples, "understanding-revised")["value"])
    hostile = '<script>bad()</script><img src="https://invalid.test/pixel" onerror="bad()">'
    value["target"]["name"] = hostile
    value["capabilities"][0]["claim"] = hostile * 70
    value["capabilities"][0]["verification_attempt"]["procedure"] = hostile
    value["capabilities"][0]["revision_reason"] = hostile
    value["evidence_refs"][0]["quote"] = hostile
    markup = ui.recorded(value)[0]
    assert html.escape(hostile * 70) in markup
    assert all(tag not in markup for tag in ("<script", "<img", "<a ", "<pre"))


def test_product_shares_body_preserves_history_counts_links_time_and_missing_states(examples, store, monkeypatch):
    from sonaloop.web.pages import projects
    from sonaloop.web._html import h
    from sonaloop.web import _render
    value = case(examples, "understanding-history")["value"]
    project = store.get_research_project(value["project_id"])
    calls, body = [], ui.record_content
    def observed(value, **kwargs):
        output = body(value, **kwargs)
        calls.append((value, kwargs, output))
        return output
    monkeypatch.setattr(ui, "record_content", observed)
    monkeypatch.setattr(_render, "render_ref", lambda ref, store: h("a", {"href": "/synthetic/" + ref["id"]}, ref["id"]))
    markup = projects._product_understanding_html(project, store, embedded=True)
    assert calls[0][2] in markup and calls[0][1]["passive"] is False
    assert calls[0][0] == ui.stored_view({key: val for key, val in value.items() if key not in {"history", "context"}})["value"]
    assert 'class="sl-integrity sl-integrity--product sl-integrity--embedded"' in markup
    assert "1 contradictory revisions" in markup and "1 verified absences" in markup
    assert '<a href="/synthetic/' in markup and 'data-local-time=' in markup
    assert "Evidenced product areas (2)" in markup and "Areas still to verify (1)" in markup
    for kind in ("flow_manifest_required", "capture_review_required", "product_understanding_required"):
        missing = projects._product_understanding_html({"integrity": {"product_understanding_required": True}},
            preflight={"kind": kind})
        assert 'data-setup-kind="' + kind + '"' in missing
    assert projects._product_understanding_html({}, store) == ""
    assert projects._product_understanding_html({"integrity": {"product_understanding_required": True}}, show_missing=False) == ""


@pytest.mark.parametrize("field", ["target", "inventory", "verification"])
def test_native_dynamic_extensions_preserve_product_base_and_truthful_fallback(examples, store, field):
    from sonaloop.web.pages.projects import _product_understanding_html
    from sonaloop.web._i18n import t
    value = deepcopy(case(examples, "understanding-revised")["value"])
    if field == "target":
        value["target"]["extension"] = {"nested": ["original native data"]}
    elif field == "inventory":
        value["routes"][0]["extension"] = ["original native data"]
    else:
        value["capabilities"][0]["verification_attempt"]["extension"] = {"nested": False}
    with pytest.raises(ValueError):
        ui.recorded(value)
    project = store.get_research_project(value["project_id"])
    project["product_understanding_versions"][-1] = {key: item for key, item in value.items()
        if key not in {"idempotent_replay", "dispatch", "project_url"}}
    store.upsert_research_project(project)
    markup = _product_understanding_html(project, store)
    assert value["capabilities"][0]["claim"] in markup and "Evidenced product areas" in markup
    assert t("rpu_details_unavailable") in markup and "original native data" not in markup
    response = TestClient(web.create_app()).get('/jobs/' + project["id"])
    assert response.status_code == 200 and value["capabilities"][0]["claim"] in response.text


def test_foreign_historical_version_and_inaccessible_product_boundary(examples, store, monkeypatch):
    value = case(examples, "understanding-history")["value"]
    other = case(examples, "understanding-bounded-history")["value"]
    with pytest.raises(KeyError):
        services.get_product_understanding(value["project_id"], version_id=other["id"], store=store)
    # SQLite is single-tenant. Exercise the existing Product read boundary,
    # without asserting Postgres RLS evidence from this isolated fixture.
    calls = []
    def missing(project_id, *, store):
        calls.append(project_id)
        raise KeyError(project_id)
    monkeypatch.setattr(services, "get_project_graph", missing)
    monkeypatch.setattr(ui, "record_content", forbidden)
    response = TestClient(web.create_app()).get('/jobs/' + value["project_id"])
    assert response.status_code == 200 and calls == [value["project_id"]]
    assert value["capabilities"][0]["claim"] not in response.text


def test_original_mcp_envelopes_unchanged_after_presentation(examples, store):
    server = original_server()
    listed = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        item = next(row for row in examples if row["tool"] == name)
        envelope = server._tool_manager._tools[name].fn(**item["input"])
        before = deepcopy(envelope)
        rendered = TOOLS[name][0](envelope["data"])
        assert rendered[1] == "ready" and envelope == before
        assert listed[name].inputSchema and listed[name].outputSchema

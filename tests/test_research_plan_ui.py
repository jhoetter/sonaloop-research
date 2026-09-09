"""Native Plan8, exact public projection, Product reuse and no rendering writes."""
import asyncio
from copy import deepcopy
import html
import json
import os
from pathlib import Path
import socket

from fastapi.testclient import TestClient
import pytest

from sonaloop import config, services, web
from sonaloop import plan as native
from sonaloop.storage import Store
from sonaloop.ui_components import research_plan as ui, research_plan_rows as rows


TOOLS = {"get_plan": (ui.plan, ui.plan_view), "add_task": (ui.task, ui.task_view),
    "record_frame": (ui.task, ui.task_view), "link_evidence": (ui.task, ui.task_view),
    "record_judgment": (ui.judgment, ui.judgment_view), "assess_progress": (ui.progress, ui.progress_view),
    "park_evidence": (ui.parked, ui.parked_view), "unpark_evidence": (ui.unparked, ui.unparked_view)}


def forbidden(*args, **kwargs):
    pytest.fail("Plan presentation attempted a native writer, source, provider, media or network call")


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


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_plan, _tools_methodology
    server = FastMCP("original-research-plan")
    _tools_plan.register_plan(server)
    _tools_methodology.register_methodologies(server)
    return server


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
    call("get_plan", {"project_id": "absent-plan"}, "researchplan-absent")
    pid = services.start_project("Plan example", "Understand the handover", persona_ids=[], store=store)["id"]
    call("get_plan", {"project_id": pid}, "researchplan-initial")
    call("record_frame", {"project_id": pid, "task_id": "frame__root", "questions": ["Where is the handover unclear?"],
        "hypotheses": ["A missing reference may cause delay."], "memory_refs": ["memory:unresolved-source"]}, "researchplan-frame")
    task = call("add_task", {"project_id": pid, "bucket": "act", "capability": "explore", "title": "Inspect handover",
        "intent": "Retain the unresolved source.", "consumes": ["frame__root"], "requires": {"min_inputs": 0},
        "plan_note": "A bounded example."}, "researchplan-task")
    args = {"project_id": pid, "task_id": task["id"], "kind": "source-kind", "evidence_id": "unresolved-example"}
    call("link_evidence", args, "researchplan-linked")
    call("link_evidence", args, "researchplan-link-replayed")
    for decided in (False, True):
        call("record_judgment", {"project_id": pid, "task_id": task["id"], "gate_tag": "question-reviewed",
            "decided": decided, "rationale": "The supplied source supports this bounded judgment.",
            "evidence_refs": ["source-kind:unresolved-example"]}, "researchplan-judgment-" + str(decided).lower())
    call("assess_progress", {"project_id": pid, "task_id": task["id"], "rationale": "The frame is recorded; questions remain.",
        "evidence_refs": ["source-kind:unresolved-example"], "delta": "More precisely framed, still uncertain."}, "researchplan-progress")
    park_args = {"project_id": pid, "refs": ["source-kind:unresolved-example", {"kind": "note", "id": "context"}],
        "reason": "Keep visible outside the gate.", "task_id": task["id"]}
    call("park_evidence", park_args, "researchplan-parked")
    call("park_evidence", park_args, "researchplan-parking-replayed")
    call("unpark_evidence", {"project_id": pid, "refs": ["note:context"], "reason": "Context is relevant again.",
        "task_id": task["id"]}, "researchplan-unparked")
    call("park_evidence", {"project_id": pid, "refs": ["note:whole-plan"], "reason": "Whole-plan parking."}, "researchplan-plan-parking")
    call("get_plan", {"project_id": pid}, "researchplan-history")
    # Native permits arbitrary buckets/statuses and signed min_inputs. Persist
    # those authored data through its real validator; the renderer cannot erase them.
    plan = native.get_plan(pid, store=store)
    plan["tasks"].append({"id": "custom", "title": "An open-tag task", "bucket": "ponder", "status": "awaiting-review",
        "requires": {"min_inputs": -1}, "presentation": {"forms": ["free-form"], "formats": [], "library": ["Notes"]}})
    native.save_plan(plan, store=store)
    call("get_plan", {"project_id": pid}, "researchplan-open-tags")
    empty = services.start_project("Empty plan", "No tasks supplied", store=store)["id"]
    native.save_plan({"project_id": empty, "tasks": []}, store=store)
    call("get_plan", {"project_id": empty}, "researchplan-empty")
    governed = services.start_project("Governed example", "Inspect the actual checkpoint", persona_ids=[],
        operation_id="research-plan-governed", store=store)["id"]
    verify = services.add_task(governed, "verify", "decide", "Review the frame", consumes=["frame__root"],
        requires={"min_inputs": 0, "gate_tag": "reviewed"}, store=store)
    run = services.start_run(governed, operation_id="research-plan-run", store=store)
    issued = services.run_step(run["run_id"], store=store)
    args = {"project_id": governed, "task_id": "frame__root", "questions": ["What remains unclear?"],
            "memory_refs": ["memory:governed-example"], "dispatch_token": issued["dispatch_token"]}
    call("record_frame", args, "researchplan-governed-frame")
    call("record_frame", args, "researchplan-frame-replayed")
    issued = services.run_step(run["run_id"], store=store)
    assert issued["step_id"] == verify["id"]
    args = {"project_id": governed, "task_id": verify["id"], "gate_tag": "reviewed", "decided": True,
        "rationale": "The minimal frame was reviewed.", "evidence_refs": ["frame:frame__root"],
        "dispatch_token": issued["dispatch_token"]}
    call("record_judgment", args, "researchplan-governed-judgment")
    call("record_judgment", args, "researchplan-judgment-replayed")
    call("record_judgment", args, "researchplan-judgment-checkpoint-replayed")
    call("get_plan", {"project_id": governed}, "researchplan-governed-history")
    return result


def case(examples, name):
    return next(item for item in examples if item["scenario"] == name)


def test_actual_eight_native_results_public_equivalence_and_fixture_export(examples, tmp_path):
    from jsonschema import Draft202012Validator
    assert {item["tool"] for item in examples} == set(TOOLS)
    for item in examples:
        assert ui.render_view(item["public_value"]) == TOOLS[item["tool"]][0](item["value"])
        Draft202012Validator(ui.public_schema(item["public_value"]["view"])).validate(item["public_value"])
    sizes = {item["scenario"]: len(json.dumps({"name": item["tool"], "value": item["public_value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for item in examples}
    assert max(sizes.values()) <= 8192
    target = Path(os.environ.get("RESEARCH_PLAN_FIXTURE_PATH", tmp_path / "research-plan.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Native Plan fixtures:", target, "count:", len(examples), "public sizes:", sizes)


def test_native_replays_and_parking_scope_are_not_reinterpreted(examples, store):
    frame = case(examples, "researchplan-frame-replayed")["value"]
    assert frame["dispatch"]["reconciled_existing_checkpoint"] is True
    assert frame["dispatch"]["receipt"]["deduplicated"] is True
    judgment = case(examples, "researchplan-judgment-replayed")["value"]
    initial = case(examples, "researchplan-governed-judgment")["value"]
    assert initial["dispatch"]["state"] == "linked" and initial["dispatch"]["checkpointed"] is False
    assert "needs" in initial["dispatch"] and "receipt" not in initial["dispatch"]
    assert judgment["dispatch"]["receipt"]["deduplicated"] is False
    assert case(examples, "researchplan-judgment-checkpoint-replayed")["value"]["dispatch"]["receipt"]["deduplicated"] is True
    assert "operation_id" in judgment and "operation_id" not in ui.judgment_view(judgment)["value"]
    history = case(examples, "researchplan-governed-history")["value"]
    assert len(history["judgments"]) == 1 and "dispatch" not in history["judgments"][0]
    assert len(case(examples, "researchplan-link-replayed")["value"]["produces"]) == 1
    history = case(examples, "researchplan-history")["value"]
    assert len(history["parked_refs"]) == 2 and history["parked_refs"][0]["refs"] == ["source-kind:unresolved-example"]
    assert history["unparked_refs"][0]["refs"] == ["note:context"]
    parked = case(examples, "researchplan-plan-parking")["value"]
    assert parked["task_id"] == "" and "Whole plan" in ui.parked(parked)[0]
    replay = case(examples, "researchplan-parking-replayed")["value"]
    assert "deduplicated" not in replay and "deduplicated" not in ui.parked_view(replay)["value"]


def test_every_excluded_context_path_and_native_bytes_remain_distinct(examples):
    records = [deepcopy(case(examples, name)) for name in
        ("researchplan-governed-frame", "researchplan-judgment-replayed", "researchplan-governed-history")]
    points = [(records[0]["value"]["dispatch"]["receipt"], "key"),
        (records[1]["value"], "operation_id"), (records[1]["value"]["dispatch"]["receipt"], "key"),
        (records[2]["value"]["judgments"][0], "operation_id")]
    markers = []
    for index, (record, key) in enumerate(points):
        record[key] = marker = f"EXCLUDED-CONTEXT-{index}"
        markers.append(marker)
    for item in records[:2]:
        for key in ("dispatch_token", "operation_id", "arguments", "key"):
            item["value"]["dispatch"][key] = {"nested": "EXCLUDED-DISPATCH-" + key}
            markers.append("EXCLUDED-DISPATCH-" + key)
    before = deepcopy(records)
    for item in records:
        view = TOOLS[item["tool"]][1](item["value"])
        output = json.dumps(view) + ui.render_view(view)[0]
        assert all(marker not in output for marker in markers)
    assert records == before
    # Ordinary authored prose is preserved, including words resembling metadata.
    value = records[1]["value"]
    value["rationale"] = "The term dispatch_token remains quoted source prose."
    assert value["rationale"] in ui.judgment(value)[0]


def test_projection_and_shared_body_never_read_or_write(examples, monkeypatch):
    from sonaloop import presentation
    from sonaloop.web import _plan_fw, _components
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        for name in ("read_text", "read_bytes", "exists"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(presentation, "present", forbidden)
        patch.setattr(_plan_fw, "_framework_strip", forbidden)
        patch.setattr(_components, "_icon", forbidden)
        for name in (*TOOLS, "start_project", "run_step", "assess_project", "project_health"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            assert TOOLS[item["tool"]][0](item["value"]) == ui.render_view(item["public_value"])
    assert examples == before


def test_public_schema_is_closed_at_all_nested_record_levels(examples):
    from jsonschema import Draft202012Validator
    view = deepcopy(case(examples, "researchplan-judgment-replayed")["public_value"])
    for record in (view, view["value"], view["value"]["dispatch"], view["value"]["dispatch"]["receipt"]):
        record["operation_id"] = "NOT-A-PUBLIC-PROP"
        assert not Draft202012Validator(ui.public_schema("judgment")).is_valid(view)
        with pytest.raises(ValueError):
            ui.render_view(view)
        del record["operation_id"]
    with pytest.raises(ValueError):
        ui.render_view(case(examples, "researchplan-history")["value"])


@pytest.mark.parametrize("path,bad", [(('tasks', 0, 'frame', 'questions'), [{"arguments": []}]),
    (('tasks', 0, 'presentation'), {"style": "url(unsafe)"}),
    (('tasks', 0, 'requires', 'min_inputs'), True), (('judgments', 0, 'decided'), "true"),
    (('progress', 0, 'coverage', 'tasks_done'), -1), (('parked_refs', 0, 'refs'), [{"arguments": {}}])])
def test_unknown_native_nested_shapes_fail_truthfully(examples, path, bad):
    value = deepcopy(case(examples, "researchplan-history")["value"])
    node = value
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad
    with pytest.raises(ValueError):
        ui.plan(value)


def test_free_buckets_status_signed_minimum_zero_and_absence(examples):
    value = case(examples, "researchplan-open-tags")["value"]
    markup = ui.plan(value)[0]
    assert "An open-tag task" in markup and "awaiting-review" in markup and "ponder" in markup
    assert "min_inputs: -1" in markup and "min_inputs: 0" in markup
    assert "source-kind:unresolved-example" in markup and "frame:frame__root" in markup
    for name in ("researchplan-absent", "researchplan-empty"):
        assert ui.render_view(case(examples, name)["public_value"])[1] == "empty"
    empty = case(examples, "researchplan-empty")["public_value"]["value"]
    assert "goal" not in empty and "judgments" not in empty
    progress = case(examples, "researchplan-progress")["value"]
    assert progress["coverage"]["sessions"] == 0 and progress["delta"] in ui.progress(progress)[0]
    assert "<dd>0</dd>" in ui.progress(progress)[0]
    assert "<dd>false</dd>" in ui.judgment(case(examples, "researchplan-judgment-false")["value"])[0]


def test_long_authored_prose_and_references_are_inert_and_complete(examples):
    value = deepcopy(case(examples, "researchplan-history")["value"])
    hostile = '<script>bad()</script><img src="https://invalid.test/pixel" onerror="bad()">'
    value["tasks"][0]["frame"]["questions"] = [hostile * 100]
    value["tasks"][0]["intent"] = hostile
    value["judgments"][0]["rationale"] = hostile
    value["parked_refs"][0]["refs"] = ["javascript:source-label"]
    markup = ui.plan(value)[0]
    assert html.escape(hostile * 100) in markup and "javascript:source-label" in markup
    assert all(tag not in markup for tag in ("<script", "<img", "<a ", "<form", "<button", "<pre"))


def test_product_prepares_original_chips_framework_and_shares_full_history(examples, store, monkeypatch):
    from sonaloop.web import _graph
    from sonaloop.web._html import h
    value = case(examples, "researchplan-history")["value"]
    calls, body = [], ui.plan_content
    def observed(value, **kw):
        result = body(value, **kw)
        calls.append((deepcopy(value), kw, result))
        return result
    monkeypatch.setattr(ui, "plan_content", observed)
    monkeypatch.setattr(_graph, "_framework_strip", lambda *a: h("span", {"data-test-framework": True}, "Prepared framework"))
    rendered = _graph._plan_html(value, store)
    projected, kw, result = calls[0]
    assert rendered == result and projected == ui.plan_view(value)["value"] and kw["passive"] is False
    assert 'class="pt-mark"' in rendered and 'class="ptask is-done is-last"' in rendered
    assert 'class="psec"' in rendered and 'class="plan-prog-row"' in rendered
    assert "Prepared framework" in rendered and len(kw["prepared"]["tasks"][0]["evidence"]) == 0
    assert rows.frame_content(projected["tasks"][0]["frame"]) in rendered
    assert rows.history_content(projected) in rendered
    assert rows.judgment_content(projected["judgments"][0]) in rendered
    with pytest.raises(ValueError):
        ui.plan_content(projected, prepared={"framework": "untrusted"})


def test_actual_product_plan_route_has_one_plan_read_and_no_writer(examples, store, monkeypatch):
    value = case(examples, "researchplan-open-tags")["value"]
    pid = value["project_id"]
    before, calls, getter = list(store.conn.iterdump()), [], services.get_plan
    def read(*a, **kw):
        calls.append(a)
        return getter(*a, **kw)
    monkeypatch.setattr(services, "get_plan", read)
    for name in set(TOOLS) - {"get_plan"}:
        monkeypatch.setattr(services, name, forbidden)
    client = TestClient(web.create_app())
    response = client.get(f"/jobs/{pid}/plan")
    assert response.status_code == 200 and len(calls) == 1
    assert "An open-tag task" in response.text and "Context is relevant again." in response.text
    assert before == list(store.conn.iterdump())
    monkeypatch.setattr(services, "get_plan", forbidden)
    assert "An open-tag task" not in client.get("/jobs/missing-project/plan").text


def test_product_evidence_resolution_stays_by_identity_and_position(examples, monkeypatch):
    from sonaloop.web import _graph
    from sonaloop.web._html import h
    value = deepcopy(case(examples, "researchplan-history")["value"])
    value["tasks"][1]["produces"] = [{"kind": kind, "id": rid} for kind, rid in
        (("custom-report-kind", "syn"), ("custom-artifact-kind", "proto"), ("session", "council-a"),
         ("session", "council-b"), ("missing-kind", "unknown"))]
    class PreparedStore:
        def list_syntheses(self):
            return [{"id": "syn"}]
        def list_prototypes(self, project_id):
            assert project_id == value["project_id"]
            return [{"id": "proto", "slug": "existing-prototype", "name": "Existing prototype"}]
        def get_council_session(self, identity):
            return {"id": identity} if identity in {"council-a", "council-b"} else None
    monkeypatch.setattr(_graph, "_framework_strip", lambda *a: h("span", {}, "Framework kept"))
    markup = _graph._plan_html(value, PreparedStore())
    for href in ("/syntheses/syn", "/prototypes/existing-prototype", "/councils/council-a", "/councils/council-b"):
        assert f'href="{href}"' in markup
    assert " 1 ↗" in markup and " 2 ↗" in markup and "Existing prototype" in markup
    assert 'href="unknown"' not in markup and "missing-kind:unknown" in markup
    passive = ui.plan(value)[0]
    assert "<a " not in passive and "custom-report-kind:syn" in passive and "Framework kept" not in passive
    assert "</span> · <span" in passive


def test_product_foreign_project_stops_before_plan_read(monkeypatch):
    # SQLite is single-tenant; exercise the route's actual Project read boundary
    # without pretending this is an RLS qualification.
    calls = []
    def missing(project_id, *, store):
        calls.append(project_id)
        raise KeyError(project_id)
    monkeypatch.setattr(services, "get_research_project", missing)
    monkeypatch.setattr(services, "get_plan", forbidden)
    response = TestClient(web.create_app()).get('/jobs/foreign-project/plan')
    assert response.status_code == 200 and calls == ["foreign-project"]
    assert "sl-research-plan-history" not in response.text


def test_legacy_product_minimal_task_keeps_original_defaults(store):
    from sonaloop.web._graph import _plan_html
    value = {"project_id": "legacy", "tasks": [{"id": "kept-identity", "bucket": "act", "status": "todo"}]}
    with pytest.raises(ValueError):
        ui.plan(value)
    markup = _plan_html(value, store)
    assert 'class="pt-title">kept-identity</span>' in markup
    assert 'class="plan-prog-row"' in markup and "Additional recorded details are unavailable" in markup


@pytest.mark.parametrize("extension", ["presentation", "integrity", "frame"])
def test_native_extension_keeps_product_base_plan_with_truthful_detail_fallback(examples, store, extension):
    from sonaloop.web._i18n import t
    value = deepcopy(case(examples, "researchplan-history")["value"])
    if extension == "presentation":
        value["tasks"][0]["presentation"]["legacy_extension"] = {"unexpected": "old-style"}
    elif extension == "integrity":
        value["integrity"] = {"custom_policy": ["outside-public-shape"]}
    else:
        value["tasks"][0]["frame"]["custom_context"] = {"arguments": ["unsupported"]}
    native.save_plan(value, store=store)
    actual = services.get_plan(value["project_id"], store=store)
    with pytest.raises(ValueError):
        ui.plan(actual)
    before = list(store.conn.iterdump())
    response = TestClient(web.create_app()).get(f'/jobs/{value["project_id"]}/plan')
    assert response.status_code == 200 and "Inspect handover" in response.text
    assert 'class="pt-mark"' in response.text and 'class="psec"' in response.text
    assert t("rplan_details_unavailable") in response.text
    assert "old-style" not in response.text and "outside-public-shape" not in response.text
    assert before == list(store.conn.iterdump())


def test_actual_fastmcp_eight_input_output_schemas_and_single_native_execution(examples, store, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_plan, _tools_methodology
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/researchplan/v1"
    envelopes, env = [], _tools_plan._env
    def capture(*a, **kw):
        result = env(*a, **kw); envelopes.append(deepcopy(result)); return result
    monkeypatch.setattr(_tools_plan, "_env", capture)
    monkeypatch.setattr(_tools_methodology, "_env", capture)
    for name in TOOLS:
        item = next(row for row in examples if row["tool"] == name)
        if name == "unpark_evidence":
            services.park_evidence(item["input"]["project_id"], item["input"]["refs"], "Re-park for native replay test.",
                item["input"]["task_id"], store=store)
        calls, fn = [], getattr(services, name)
        def counted(*a, **kw):
            value = fn(*a, **kw); calls.append(deepcopy(value)); return value
        with monkeypatch.context() as patch:
            patch.setattr(services, name, counted)
            count = len(envelopes)
            result = asyncio.run(server.call_tool(name, item["input"]))
        assert not result.isError and len(calls) == 1 and len(envelopes) == count + 1
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1])
        assert result.content == text and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["html"] == TOOLS[name][0](calls[0])[0]

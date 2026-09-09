"""Actual Run results, closed authored props and read-only Product ownership."""
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

from sonaloop import config, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import run_journal as ui, run_journal_rows as rows


TOOLS = {"start_run": (ui.journal, ui.journal_view), "run_journal": (ui.journal, ui.journal_view),
         "resume_project_run": (ui.resumed, ui.resumed_view), "finish_run": (ui.finished, ui.finished_view)}
DIMENSIONS = ("exploration_depth", "segment_breadth", "concept_novelty", "evidence_groundedness",
              "honesty_anti_steering", "iteration", "finish")


def forbidden(*args, **kwargs):
    pytest.fail("Run presentation attempted a writer, provider, file, clock or network operation")


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
    from sonaloop.mcp_server import _tools_plan
    server = FastMCP("original-run-journal")
    _tools_plan.register_plan(server)
    return server


@pytest.fixture
def examples(store):
    server, result = original_server(), []
    def project(suffix):
        return services.start_project("Run example " + suffix, "Inspect recorded research steps", None,
            persona_ids=[], operation_id="run-view-project:" + suffix, store=store)["id"]
    def call(tool, arguments, scenario):
        envelope = server._tool_manager._tools[tool].fn(**arguments)
        assert envelope["ok"], envelope
        value = deepcopy(envelope["data"])
        markup, state = TOOLS[tool][0](value)
        public = TOOLS[tool][1](value)
        assert ui.render_view(public) == (markup, state)
        result.append({"scenario": scenario, "tool": tool, "input": deepcopy(arguments),
                       "value": value, "public_value": public, "state": state})
        return value
    pid = project("active")
    start = {"project_id": pid, "budget": 10, "operation_id": "run-view-active"}
    active = call("start_run", start, "runs-started")
    rid = active["run_id"]
    call("start_run", start, "runs-start-replayed")
    call("run_journal", {"run_id": rid}, "runs-journal-empty")
    call("resume_project_run", {"project_id": pid, "run_id": rid}, "runs-resumed-empty")
    dispatch = services.run_step(rid, store=store)
    services.record_dispatch_progress(pid, dispatch["dispatch_token"], "example:source-inspected", "source_inspected",
        {"source": "supplied-example"}, "recorded-example-digest", store=store)
    services.checkpoint_step(rid, {"task_id": dispatch["step_id"], "bucket": dispatch["kind"],
        "key": dispatch["key"], "dispatch_token": dispatch["dispatch_token"],
        "summary": "Recorded supplied source labels; their content is not resolved by this view.",
        "evidence": ["council:unresolved-example"], "consume_refs": ["frame:earlier-example"],
        "optional_context_refs": [{"kind": "evidence", "id": "source-example", "anchor": "line-2",
            "quote": "A supplied quotation.", "text": "Its supplied context."}],
        "produced_refs": ["council:unresolved-example"], "downstream_refs": ["verify:example"],
        "parked_refs": ["reference:parked-example"], "open_questions": ["What remains uncertain?"],
        "expected_output_kind": "frame"}, store=store)
    critic = services.record_completeness_critic(pid, {"passed": False, "scores": {"finish": 1},
        "missing": [{"kind": "risk", "what": "Unresolved source context"}], "rationale": "More work remains."},
        rid, "run-view-critic-open", store=store)
    services.record_critic_round(rid, critic["id"], "run-view-critic-open", store=store)
    call("run_journal", {"run_id": rid}, "runs-journal-populated")
    call("resume_project_run", {"project_id": pid, "run_id": rid}, "runs-resumed-context")
    for status in ("stopped", "capped", "finished"):
        terminal_pid = project(status)
        run = services.start_run(terminal_pid, operation_id="run-view-" + status, store=store)
        if status == "finished":
            # Actual freeform plan + two persisted run-bound critics satisfy the
            # native finish gate. No synthetic terminal status is written directly.
            issued = services.run_step(run["run_id"], store=store)
            services.record_frame(terminal_pid, "frame__root", ["What is the bounded question?"],
                memory_refs=["memory:authored-example"], dispatch_token=issued["dispatch_token"], store=store)
            for index in range(2):
                key = f"run-view-finished-critic:{index}"
                report = services.record_completeness_critic(terminal_pid, {"passed": True,
                    "scores": {name: 5 for name in DIMENSIONS}, "missing": [],
                    "rationale": "The minimal freeform frame is complete."}, run["run_id"], key, store=store)
                services.record_critic_round(run["run_id"], report["id"], key, store=store)
        args = {"run_id": run["run_id"], "status": status}
        call("finish_run", args, "runs-" + status)
        if status == "stopped":
            call("finish_run", args, "runs-stop-replayed")
        if status == "finished":
            call("run_journal", {"run_id": run["run_id"]}, "runs-journal-finished")
    call("start_run", {"project_id": project("signed-budget"), "budget": -1,
        "operation_id": "run-view-negative"}, "runs-negative-budget")
    return result


def case(examples, name):
    return next(row for row in examples if row["scenario"] == name)


def test_actual_native_four_shapes_public_equivalence_and_fixture_export(examples, tmp_path):
    assert {item["tool"] for item in examples} == set(TOOLS)
    for item in examples:
        assert ui.render_view(item["public_value"]) == TOOLS[item["tool"]][0](item["value"])
        # Native operation_id is an alias of dispatch scope/correlation context,
        # not a proven authorization bearer. Neither belongs in public props.
        for dispatch in item["value"].get("dispatches", []):
            assert dispatch["operation_id"] == dispatch["dispatch_token"]
            assert dispatch["dispatch_token"] not in json.dumps(item["public_value"])
    assert case(examples, "runs-finished")["value"]["status"] == "finished"
    assert case(examples, "runs-journal-finished")["value"]["critic_rounds"][-1]["passed"] is True
    sizes = {item["scenario"]: len(json.dumps({"name": item["tool"], "value": item["public_value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for item in examples}
    assert max(sizes.values()) <= 8192
    target = Path(os.environ.get("RESEARCH_RUN_FIXTURE_PATH", tmp_path / "runs-native.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Actual native Run fixtures:", target, "count:", len(examples), "public sizes:", sizes)


def test_projection_and_render_have_no_store_writer_provider_clock_or_file_access(examples, monkeypatch):
    from sonaloop.web import _components
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        for name in ("read_text", "read_bytes", "exists"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(_components, "_avatar", forbidden)
        for name in (*TOOLS, "run_step", "checkpoint_step", "project_health", "assess_project", "start_project"):
            patch.setattr(services, name, forbidden)
        for item in examples:
            assert TOOLS[item["tool"]][0](item["value"]) == ui.render_view(item["public_value"])
    assert before == examples


def test_native_replay_flags_omission_budget_cursor_and_terminal_meanings(examples, store):
    initial = case(examples, "runs-started")["public_value"]
    assert "idempotent_replay" not in initial
    assert case(examples, "runs-start-replayed")["public_value"]["idempotent_replay"] is True
    assert case(examples, "runs-stop-replayed")["public_value"]["deduplicated"] is True
    assert case(examples, "runs-negative-budget")["public_value"]["budget"] == -1
    legacy = deepcopy(case(examples, "runs-journal-populated")["value"])
    legacy.update(status="legacy-paused", budget=0, cursor=7)
    store.upsert_run(legacy)
    got = services.run_journal(legacy["run_id"], store=store)
    projected = ui.journal_view(got)
    assert projected["status"] == "legacy-paused" and projected["cursor"] == 7 and len(projected["steps"]) == 1
    assert "<dd>0</dd>" in ui.journal(got)[0] and "<dd>legacy-paused</dd>" in ui.journal(got)[0]
    for status in ("stopped", "capped", "finished"):
        value = case(examples, "runs-" + status)["public_value"]
        assert value["status"] == status and "project_id" not in value and "cursor" not in value
        assert f"<dd>{status}</dd>" in ui.render_view(value)[0]


def test_exact_trace_references_order_critic_counts_and_full_text(examples):
    value = deepcopy(case(examples, "runs-journal-populated")["value"])
    value["steps"].append({**deepcopy(value["steps"][0]), "idx": 4, "summary": "Second supplied row."})
    native = deepcopy(value)
    view, markup = ui.journal_view(value), ui.journal(value)[0]
    assert [step["idx"] for step in view["steps"]] == [0, 4]
    assert markup.index(value["steps"][0]["summary"]) < markup.index("Second supplied row.")
    assert all(text in markup for text in ("council:unresolved-example", "evidence:source-example#line-2",
        "A supplied quotation.", "Its supplied context.", "What remains uncertain?", "reference:parked-example"))
    assert view["critic_rounds"][0]["passed"] is False and view["critic_rounds"][0]["missing"] == 1
    assert view["dispatches"][0]["progress_receipts"][0]["result_digest"] == "recorded-example-digest"
    assert native == value


def test_every_omitted_execution_context_path_is_absent_without_native_mutation(examples):
    value = deepcopy(case(examples, "runs-journal-populated")["value"])
    resume = deepcopy(case(examples, "runs-resumed-context")["value"])
    locations = [(value, ("operation_id", "operation_fingerprint")),
        (value["steps"][0], ("key", "dispatch_token")),
        (value["dispatches"][0], ("dispatch_token", "operation_id", "workspace_id", "project_id", "run_id", "key")),
        (value["critic_rounds"][0], ("key",)),
        (value["steps"][0]["receipt"], ("key",)), (value["dispatches"][0]["receipt"], ("key",)),
        (next(iter(value["dispatches"][0]["progress_receipts"].values())), ("action_key",)),
        (resume, ("operation_id",)), (resume["trace"], ("cloud_trace_query",))]
    sentinels = []
    for index, (record, keys) in enumerate(locations):
        for key in (*keys, "primitive_key", "arguments", "next_call", "then", "directive", "brief", "blocking_action"):
            marker = f"EXCLUDED-CONTEXT-{index}-{key}"
            record[key] = marker
            sentinels.append(marker)
    progress = value["dispatches"][0]["progress_receipts"]
    progress["EXCLUDED-MAP-KEY"] = progress.pop(next(iter(progress)))
    sentinels.append("EXCLUDED-MAP-KEY")
    resume["safe_next_action"]["arguments"].update(dispatch_token="EXCLUDED-ARGUMENT", operation_id="EXCLUDED-ALIAS:suffix")
    resume["safe_next_action"]["then"] = {"tool": "writer", "arguments": {"token": "EXCLUDED-NESTED"}}
    sentinels += ["EXCLUDED-ARGUMENT", "EXCLUDED-ALIAS:suffix", "EXCLUDED-NESTED"]
    before = deepcopy((value, resume))
    for native, project in ((value, ui.journal_view), (resume, ui.resumed_view)):
        view = project(native)
        output = json.dumps(view) + ui.render_view(view)[0]
        assert all(marker not in output for marker in sentinels)
    assert before == (value, resume)


def test_public_schema_rejects_unknown_nested_fields_instead_of_stripping_them(examples):
    from jsonschema import Draft202012Validator
    for item in examples:
        Draft202012Validator(ui.public_schema(item["public_value"]["view"])).validate(item["public_value"])
    view = deepcopy(case(examples, "runs-journal-populated")["public_value"])
    objects = [view, view["steps"][0], view["dispatches"][0], view["critic_rounds"][0],
        view["steps"][0]["receipt"], view["dispatches"][0]["output_contract"],
        view["dispatches"][0]["progress_receipts"][0], view["steps"][0]["optional_context_refs"][0]]
    for record in objects:
        record["operation_id"] = "EXCLUDED-PUBLIC"
        with pytest.raises(ValueError):
            ui.render_view(view)
        assert not Draft202012Validator(ui.public_schema("journal")).is_valid(view)
        del record["operation_id"]


@pytest.mark.parametrize("path,bad", [(('steps', 0, 'evidence'), [{"unrecognized": {"arguments": []}}]),
    (('steps', 0, 'open_questions'), [{"text": "not a native question string"}]),
    (('dispatches', 0, 'output_contract', 'max_primary_outputs'), True),
    (('critic_rounds', 0, 'missing'), []), (('cursor',), -1)])
def test_unsupported_native_nested_shape_fails_without_partial_or_invented_result(examples, path, bad):
    value = deepcopy(case(examples, "runs-journal-populated")["value"])
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises(ValueError):
        ui.journal(value)


def test_untrusted_authored_fields_stay_literal_and_resume_is_not_health(examples):
    value = deepcopy(case(examples, "runs-journal-populated")["value"])
    hostile = '<img src="https://bad.invalid/image" onerror="call()"><script>bad()</script>'
    value["steps"][0]["summary"] = hostile * 100
    value["steps"][0]["optional_context_refs"][0].update(quote=hostile, text=hostile)
    markup = ui.journal(value)[0]
    assert html.escape(hostile * 100) in markup
    assert all(tag not in markup for tag in ("<img", "<script", "<button", "<form", "<a "))
    resumed = case(examples, "runs-resumed-context")["public_value"]
    assert "arguments" not in resumed and "cloud_trace_query" not in resumed["trace"]
    assert resumed["continuation_tool"] == "run_step" and "engine_finished" not in resumed
    assert resumed["trace"]["limitation"] in ui.render_view(resumed)[0]


@pytest.mark.parametrize("key,change", [
    ("safe_next_action", {"tool": "finish_run", "arguments": {"run_id": "foreign"}}),
    ("safe_next_action", {"tool": "run_step", "arguments": {"run_id": "foreign"}}),
    ("status", "finished"), ("idempotent_replay", False)])
def test_resume_rejects_a_different_native_continuation_or_replay_meaning(examples, key, change):
    value = deepcopy(case(examples, "runs-resumed-context")["value"])
    value[key] = change
    with pytest.raises(ValueError):
        ui.resumed(value)


def test_resume_and_outcome_public_objects_are_closed_and_never_accept_raw_native(examples):
    for name in ("runs-resumed-context", "runs-stopped", "runs-journal-populated"):
        item = case(examples, name)
        with pytest.raises(ValueError):
            ui.render_view(item["value"])
        value = deepcopy(item["public_value"])
        for record in [value, *([value["trace"]] if "trace" in value else [])]:
            record["arguments"] = {"operation_id": "not-a-public-prop"}
            with pytest.raises(ValueError):
                ui.render_view(value)
            del record["arguments"]


def product_client(monkeypatch):
    from sonaloop.web.pages import _run_journal as product
    app = FastAPI()
    product.register_run_journal(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *args, **kwargs: str(body))
    return TestClient(app)


def test_product_exact_shared_body_one_getter_and_no_persistence(examples, store, monkeypatch):
    value = case(examples, "runs-journal-populated")["value"]
    expected = ui.journal(services.run_journal(value["run_id"], store=store))[0]
    before, calls, native = list(store.conn.iterdump()), [], services.run_journal
    def counted(*args, **kwargs):
        calls.append(args)
        return native(*args, **kwargs)
    monkeypatch.setattr(services, "run_journal", counted)
    for name in ("start_run", "resume_project_run", "run_step", "finish_run", "project_health"):
        monkeypatch.setattr(services, name, forbidden)
    response = product_client(monkeypatch).get(f'/jobs/{value["project_id"]}/runs/{value["run_id"]}')
    assert response.status_code == 200 and expected in response.text and len(calls) == 1
    assert before == list(store.conn.iterdump())


def test_product_missing_and_mismatched_run_stop_before_native_read(examples, store, monkeypatch):
    value = case(examples, "runs-journal-populated")["value"]
    other = case(examples, "runs-journal-finished")["value"]
    monkeypatch.setattr(services, "run_journal", forbidden)
    client = product_client(monkeypatch)
    for pid, rid in (("absent", value["run_id"]), (value["project_id"], "absent"),
                     (other["project_id"], value["run_id"])):
        assert client.get(f"/jobs/{pid}/runs/{rid}").status_code == 404


def test_product_foreign_workspace_gate_precedes_any_run_read(monkeypatch):
    # SQLite is intentionally single-tenant. Exercise the Product's explicit
    # active-workspace seam, without pretending this is a PostgreSQL RLS test.
    from sonaloop.web.pages import _run_journal as product
    calls = []
    class ScopedStore:
        def get_research_project_for_active_workspace(self, project_id):
            calls.append(project_id)
            return None

        get_research_project = get_run = forbidden

    monkeypatch.setattr(product, "Store", ScopedStore)
    monkeypatch.setattr(services, "run_journal", forbidden)
    response = product_client(monkeypatch).get('/jobs/foreign-project/runs/foreign-run')
    assert response.status_code == 404 and calls == ["foreign-project"]


def test_product_malformed_journal_has_controlled_unavailable_body(examples, store, monkeypatch):
    value = deepcopy(case(examples, "runs-journal-populated")["value"])
    value["steps"][0]["evidence"] = [{"unsupported": {"secret": "not-disclosed"}}]
    store.upsert_run(value)
    response = product_client(monkeypatch).get(f'/jobs/{value["project_id"]}/runs/{value["run_id"]}')
    assert response.status_code == 200 and "cannot be displayed" in response.text and "not-disclosed" not in response.text


def test_real_registered_product_route(examples):
    value = case(examples, "runs-journal-populated")["value"]
    response = TestClient(web.create_app()).get(f'/jobs/{value["project_id"]}/runs/{value["run_id"]}')
    assert response.status_code == 200 and ui.journal_content(ui.journal_view(value)) in response.text


def test_actual_fastmcp_four_schemas_results_and_single_execution(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_plan
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/runs/v1"
    envelopes, env = [], _tools_plan._env
    def capture(*args, **kwargs):
        value = env(*args, **kwargs)
        envelopes.append(deepcopy(value))
        return value
    monkeypatch.setattr(_tools_plan, "_env", capture)
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
        assert result.meta["sonaloop/presentation"]["html"] == TOOLS[name][0](calls[0])[0]
        assert result.meta["sonaloop/presentation"]["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()

"""Native read effects, exact Assessment/Markdown DTOs and existing Plan inspector."""
import asyncio
import builtins
from contextlib import contextmanager
from copy import deepcopy
import gc
import hashlib
import html
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3

from fastapi.testclient import TestClient
import pytest

from sonaloop import config, plan as native, services, web
from sonaloop.storage import Store


TOOLS = ("assess_project", "export_plan_md")


def forbidden(*args, **kwargs):
    pytest.fail("Plan inspection attempted a provider, writer or source access")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch, tmp_path):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    from sonaloop.storage import _base
    monkeypatch.setattr(_base, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)
    yield
    # Each test owns a disposable SQLite/root; keep the shared-memory reserve
    # instead of retaining N complete copies until the entire module ends.
    gc.collect()
    shutil.rmtree(tmp_path)


@pytest.fixture
def store():
    with Store() as value:
        yield value


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_plan
    server = FastMCP("original-plan-assessment")
    _tools_plan.register_plan(server)
    return server


def file_state(root):
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns,
        hashlib.sha256(path.read_bytes()).hexdigest()) for path in root.rglob("*") if path.is_file()}


@contextmanager
def reject_writes(store, monkeypatch):
    """Audit real calls after fixture setup; deny attempted DB or file writes."""
    writes = []
    denied = {getattr(sqlite3, key) for key in ("SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE",
        "SQLITE_CREATE_INDEX", "SQLITE_CREATE_TABLE", "SQLITE_CREATE_TEMP_INDEX", "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER", "SQLITE_CREATE_TEMP_VIEW", "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW",
        "SQLITE_DROP_INDEX", "SQLITE_DROP_TABLE", "SQLITE_DROP_TRIGGER", "SQLITE_DROP_VIEW", "SQLITE_ALTER_TABLE")}
    def authorizer(action, *args):
        if action in denied:
            writes.append((action, args))
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    with monkeypatch.context() as patch:
        for module in (builtins, io):
            original = module.open
            def guarded(file, mode="r", *args, _original=original, **kwargs):
                if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
                    writes.append((str(file), mode))
                    forbidden()
                return _original(file, mode, *args, **kwargs)
            patch.setattr(module, "open", guarded)
        for name in ("write_text", "write_bytes", "touch", "mkdir", "unlink", "rename", "replace"):
            patch.setattr(Path, name, forbidden)
        store.conn.set_authorizer(authorizer)
        try:
            yield writes
        finally:
            store.conn.set_authorizer(None)
    assert not writes


@pytest.fixture
def examples(store):
    results, server = [], original_server()
    def call(name, pid, scenario):
        envelope = server._tool_manager._tools[name].fn(project_id=pid)
        assert envelope["ok"], envelope
        results.append({"scenario": scenario, "tool": name, "input": {"project_id": pid},
            "value": deepcopy(envelope["data"])})
        return envelope["data"]
    project = services.start_project("Plan review", "Understand the handover", persona_ids=["synthetic-member"], store=store)
    pid = project["id"]
    task = services.add_task(pid, "act", "explore", "Inspect a handover", consumes=["frame__root"], store=store)
    services.add_task(pid, "verify", "decide", "Review the evidence", consumes=["frame__root"],
        requires={"min_inputs": 1, "gate_tag": "reviewed", "artifact_tags": ["handover"], "session_of_tags": ["handover"]}, store=store)
    services.record_open_questions(pid, ["What remains unclear?"], store=store)
    # Persisted fixture dependencies contain no runnable app or provider output.
    store.upsert_prototype({"id": "synthetic-prototype", "slug": "synthetic-prototype", "project_id": pid,
        "type": "model", "tags": ["handover"], "created_at": "2026-09-09T08:00:00Z"})
    store.insert_prototype_session({"id": "synthetic-session", "persona_id": "synthetic-member",
        "prototype_id": "synthetic-prototype", "grounded_verified": False, "created_at": "2026-09-09T08:00:00Z"})
    call("assess_project", pid, "assessment-open")
    call("export_plan_md", pid, "assessment-document-open")
    services.record_frame(pid, "frame__root", ["Where is the handover unclear?"], memory_refs=["memory:unresolved"], store=store)
    call("assess_project", pid, "assessment-act")
    terminal = {"id": "synthetic-terminal", "title": "Handover finding", "project_id": pid,
        "scope": "study", "created_at": "2026-09-09T08:10:00Z", "council_ids": [],
        "gesamtbild": "The supplied handover evidence remains bounded. " * 12,
        "positionierung": "Review the actual records.", "findings": [], "statements": []}
    store.upsert_synthesis(terminal)
    prior = services.record_decision(pid, "Keep the existing handover", "Use the evidenced route.",
        based_on=[{"kind": "synthesis", "id": terminal["id"]}], key="decision-first", store=store)["decision"]
    newer = services.record_decision(pid, "Revise the handover", "Add a visible state indicator.",
        based_on=[{"kind": "synthesis", "id": terminal["id"]}],
        rejected=[{"kind": "decision", "id": prior["id"], "note": "The state remained unclear."}],
        key="decision-second", store=store)["decision"]
    services.update_decision(prior["id"], superseded_by=newer["id"], store=store)
    plan = native.get_plan(pid, store=store)
    for row in plan["tasks"]:
        row["status"] = "done"
    plan["tasks"][-1]["produces"] = [{"kind": "synthesis", "id": terminal["id"]}]
    native.save_plan(plan, store=store)
    project = store.get_research_project(pid)
    project["sections"] = [{"id": "synthetic-section", "title": "Review", "kind": "theme", "member_ids": []}]
    project["expected_result_schemas"] = [{"id": "synthetic_output.v1", "role": "target"}]
    store.upsert_research_project(project)
    call("assess_project", pid, "assessment-contract-missing")
    report = {"id": "synthetic-report", "title": "Handover report", "scope": "project", "project_id": pid,
        "status": "done", "created_at": "2026-09-09T08:20:00Z", "lead": "A bounded report.",
        "graph_snapshot": {"build_order": ["synthesis:older-source"]},
        "sections": [{"id": "report-section", "heading": "Handover", "markdown": "Complete authored body.",
            "source_study_ids": ["synthesis:older-source"]}]}
    store.upsert_synthesis(report)
    call("assess_project", pid, "assessment-stale-handoff")
    report["graph_snapshot"]["build_order"] = ["synthesis:" + terminal["id"]]
    report["sections"][0]["source_study_ids"] = ["synthesis:" + terminal["id"]]
    store.upsert_synthesis(report)
    project["job_outcomes"] = [{"id": "synthetic-outcome", "schema_id": "synthetic_output.v1", "created_at": "2026-09-09T08:30:00Z"}]
    store.upsert_research_project(project)
    call("assess_project", pid, "assessment-complete")
    call("export_plan_md", pid, "assessment-document-decisions")
    empty = services.start_project("Empty plan", "No tasks recorded", store=store)["id"]
    native.save_plan({"project_id": empty, "tasks": []}, store=store)
    call("assess_project", empty, "assessment-blocked")
    call("export_plan_md", empty, "assessment-document-empty-plan")
    free = services.start_project("Minimal inquiry", "A bounded question", store=store)["id"]
    services.record_frame(free, "frame__root", ["A question?"], memory_refs=["memory:example"], store=store)
    call("assess_project", free, "assessment-minimal-complete")
    return results


def case(examples, scenario):
    return next(item for item in examples if item["scenario"] == scenario)


def test_native_assessment_and_export_reads_do_not_attempt_db_file_or_provider_writes(examples, store, monkeypatch, tmp_path):
    before, files, changes = list(store.conn.iterdump()), file_state(tmp_path), store.conn.total_changes
    with reject_writes(store, monkeypatch):
        for pid in dict.fromkeys(item["input"]["project_id"] for item in examples):
            assert services.assess_project(pid, store=store)["project_id"] == pid
            assert services.export_plan_md(pid, store=store).startswith("# Research plan")
    assert changes == store.conn.total_changes and before == list(store.conn.iterdump())
    assert file_state(tmp_path) == files


def test_inject_work_native_boolean_is_not_an_effect_count(store, tmp_path):
    server = original_server()
    project = services.start_project("Critic work", "Inspect the native effect", store=store)
    pid = project["id"]
    result = []
    for kind in ("segment", "angle", "concept", "fidelity_rung", "risk", "other"):
        args = {"project_id": pid, "missing": {"kind": kind, "what": "Inspect " + kind}}
        before = len(native.get_plan(pid, store=store)["tasks"]), len(store.list_open_questions(pid))
        envelope = server._tool_manager._tools["inject_work"].fn(**args)
        after = len(native.get_plan(pid, store=store)["tasks"]), len(store.list_open_questions(pid))
        assert envelope["data"] == {"injected": True}
        assert after == (before[0] + 1, before[1]) if kind in {"segment", "angle", "concept", "fidelity_rung"} else after == (before[0], before[1] + 1)
        result.append({"input": args, "value": envelope["data"], "before": before, "after": after})
        replay = server._tool_manager._tools["inject_work"].fn(**args)
        repeated = len(native.get_plan(pid, store=store)["tasks"]), len(store.list_open_questions(pid))
        assert replay["data"] == {"injected": True}
        result[-1]["repeated_after"] = repeated
    target = Path(os.environ.get("RESEARCH_PLAN_INJECT_AUDIT_PATH", tmp_path / "inject-audit.json"))
    target.write_text(json.dumps(result, indent=2))


def test_actual_native_public_equivalence_and_fixture_export(examples, tmp_path):
    from jsonschema import Draft202012Validator
    from sonaloop.ui_components import plan_assessment as ui
    transforms = {"assess_project": ui.assessment_view, "export_plan_md": ui.document_view}
    renderers = {"assess_project": ui.assessment, "export_plan_md": ui.document}
    for item in examples:
        before = deepcopy(item["value"])
        item["public_value"] = transforms[item["tool"]](item["value"])
        rendered = renderers[item["tool"]](item["value"])
        assert rendered == ui.render_view(item["public_value"]) and item["value"] == before
        item["state"] = rendered[1]
        Draft202012Validator(ui.public_schema(item["public_value"]["view"])).validate(item["public_value"])
        assert len(json.dumps({"name": item["tool"], "value": item["public_value"]},
            ensure_ascii=False, separators=(",", ":")).encode()) <= 8192
    target = Path(os.environ.get("RESEARCH_ASSESSMENT_FIXTURE_PATH", tmp_path / "assessment.json"))
    target.write_text(json.dumps(examples, indent=2))


def test_computed_states_stay_distinct_from_engine_completion(examples):
    from sonaloop.ui_components import plan_assessment as ui
    opened = case(examples, "assessment-open")["value"]
    assert opened["recommendation"] == "frame" and opened["run_state"]["active_run"] is False
    assert opened["novelty"]["has_interactive_model"] is True
    assert opened["memory_depth"]["avg_per_persona"] == 0.0
    assert any("GROUNDED" in item for gate in opened["open_gates"] for item in gate["unmet"])
    missing = case(examples, "assessment-contract-missing")["value"]
    assert missing["tasks_complete"] is True and missing["complete"] is False
    assert missing["recommendation"] == "finish" and missing["result_contract"]["satisfied"] is False
    stale = case(examples, "assessment-stale-handoff")["value"]
    assert stale["finish"]["report_handoff"]["latest_stale"] is True
    assert stale["finish"]["handed_off"] is False
    complete = case(examples, "assessment-complete")["value"]
    assert complete["complete"] is True and complete["finish"]["finished"] is True
    minimal = case(examples, "assessment-minimal-complete")["value"]
    assert minimal["complete"] is True and minimal["finish"]["handed_off"] is True
    assert minimal["finish"]["report_handoff"]["handed_off"] is False
    blocked = case(examples, "assessment-blocked")["value"]
    assert blocked["recommendation"] == "blocked" and blocked["complete"] is False and blocked["finish"]["finished"] is True
    markup = ui.assessment(opened)[0]
    assert "<dd>false</dd>" in markup and "<dd>0.0</dd>" in markup and "<dd>true</dd>" in markup
    assert "engine_finished" not in markup and " open" not in markup
    assert all(gap in html.unescape(markup) for gap in opened["gaps"])


def test_exact_handoff_body_and_open_count_keys_are_reused(examples, store, monkeypatch):
    from sonaloop.ui_components import plan_assessment as ui, project_health
    value = deepcopy(case(examples, "assessment-stale-handoff")["value"])
    handoff, calls = project_health._handoff, []
    def observed(record):
        result = handoff(record)
        calls.append((deepcopy(record), result))
        return result
    monkeypatch.setattr(project_health, "_handoff", observed)
    markup = ui.assessment(value)[0]
    assert calls[0][0] == value["finish"]["report_handoff"] and calls[0][1] in markup
    pid = value["project_id"]
    plan = native.get_plan(pid, store=store)
    plan["tasks"][0]["bucket"] = "open-bucket"
    plan["tasks"][0]["produces"].append({"kind": "unresolved-kind", "id": "source-id"})
    native.save_plan(plan, store=store)
    actual = services.assess_project(pid, store=store)
    view = ui.assessment_view(actual)["value"]
    assert any(row["bucket"] == "open-bucket" for row in view["tasks_by_bucket"])
    assert {"kind": "unresolved-kind", "count": 1} in view["coverage"]["evidence_by_kind"]
    assert "unresolved-kind" in ui.assessment(actual)[0]


def test_document_keeps_exact_decisions_references_and_supersession(examples):
    from sonaloop.ui_components import plan_assessment as ui
    value = case(examples, "assessment-document-decisions")["value"]
    markdown = value["markdown"]
    assert all(text in markdown for text in ("## Decisions", "based on: Handover finding", "rejected:",
        "superseded by:", "The state remained unclear.", "`superseded`"))
    markup = ui.document(value)[0]
    assert '<pre>' + html.escape(markdown) + '</pre>' in markup
    assert "<strong>" in markup and "<h3>Research plan" in markup
    assert ui.document_view(value)["value"] == value
    assert ui.document({"markdown": ""})[1] == "empty"
    assert "<img" not in markup and "download=" not in markup


def test_passive_projection_and_bodies_never_read_compute_or_write(examples, monkeypatch):
    from sonaloop.ui_components import plan_assessment as ui
    from sonaloop.web import _render
    renderers = {"assess_project": ui.assessment, "export_plan_md": ui.document}
    for item in examples:
        renderers[item["tool"]](item["value"])
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        for module in (builtins, io):
            patch.setattr(module, "open", forbidden)
        for name in ("open", "read_text", "read_bytes", "exists"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        patch.setattr(_render, "render_ref", forbidden)
        for name in (*TOOLS, "inject_work", "run_step", "project_health"):
            patch.setattr(services, name, forbidden)
        for name in ("ready_tasks", "is_complete", "verify_unmet", "get_plan", "render_plan_md"):
            patch.setattr(native, name, forbidden)
        for item in examples:
            assert renderers[item["tool"]](item["value"])[1] == "ready"
    assert examples == before


def test_closed_public_models_reject_unknown_compound_details(examples):
    from jsonschema import Draft202012Validator
    from sonaloop.ui_components import plan_assessment as ui
    value = ui.assessment_view(case(examples, "assessment-stale-handoff")["value"])
    for row in (value, value["value"], value["value"]["coverage"], value["value"]["tasks_by_bucket"][0],
        value["value"]["finish"], value["value"]["finish"]["report_handoff"],
        value["value"]["finish"]["report_handoff"]["reports"][0], value["value"]["result_contract"]):
        row["unexpected"] = "retained native extension"
        assert not Draft202012Validator(ui.public_schema("assessment")).is_valid(value)
        with pytest.raises(ValueError):
            ui.render_view(value)
        del row["unexpected"]
    for bad in (None, [], {}, {"view": []}, {"view": "health"}):
        with pytest.raises(ValueError):
            ui.render_view(bad)
    for bad in ({"markdown": False}, {"markdown": "x", "file": "not-returned"}):
        with pytest.raises(ValueError):
            ui.document(bad)


def test_long_hostile_text_is_complete_escaped_and_has_no_automatic_media(examples):
    from sonaloop.ui_components import plan_assessment as ui
    hostile = '<script>bad()</script><img src="https://invalid.test/pixel" onerror="bad()">'
    value = deepcopy(case(examples, "assessment-open")["value"])
    value["goal"] = hostile * 60
    value["gaps"] = [hostile]
    value["next"] = "Literal dispatch_token=<run_step token>. " + hostile
    markup = ui.assessment(value)[0]
    assert html.escape(hostile * 60) in markup and "Literal dispatch_token=" in markup
    document = ui.document({"markdown": "# A supplied document\n\n" + hostile * 60 + "\n![remote](https://invalid.test/pixel)"})[0]
    assert html.escape(hostile * 60) in document
    assert all(tag not in markup + document for tag in ("<script", "<img", "<iframe", "<form", "<button"))


def test_existing_product_plan_prepares_views_once_and_preserves_data(examples, store, monkeypatch, tmp_path):
    from sonaloop.ui_components import plan_assessment as ui
    from sonaloop.web._i18n import t
    pid = case(examples, "assessment-complete")["input"]["project_id"]
    calls, fragments = [], []
    assessment, document = services.assess_project, services.export_plan_md
    ac, dc = ui.assessment_content, ui.document_content
    def read_assessment(project_id, *, store):
        calls.append(("assessment", project_id))
        return assessment(project_id, store=store)
    def read_document(project_id, *, store):
        calls.append(("document", project_id))
        return document(project_id, store=store)
    def render_assessment(value):
        result = ac(value); fragments.append(result); return result
    def render_document(value):
        result = dc(value); fragments.append(result); return result
    monkeypatch.setattr(services, "assess_project", read_assessment)
    monkeypatch.setattr(services, "export_plan_md", read_document)
    monkeypatch.setattr(ui, "assessment_content", render_assessment)
    monkeypatch.setattr(ui, "document_content", render_document)
    before, files = list(store.conn.iterdump()), file_state(tmp_path)
    response = TestClient(web.create_app()).get(f'/jobs/{pid}/plan')
    assert response.status_code == 200 and calls == [("assessment", pid), ("document", pid)]
    assert len(fragments) == 2 and all(fragment in response.text for fragment in fragments)
    assert f'<summary>{t("rpa_title")}</summary>' in response.text
    assert f'<summary>{t("rpa_document")}</summary>' in response.text
    assert f'<h2>{t("rpa_title")}</h2>' not in response.text
    assert "Inspect a handover" in response.text and "Revise the handover" in response.text
    assert before == list(store.conn.iterdump()) and files == file_state(tmp_path)


def test_product_access_and_missing_plan_precede_additional_native_reads(store, monkeypatch):
    monkeypatch.setattr(services, "assess_project", forbidden)
    monkeypatch.setattr(services, "export_plan_md", forbidden)
    calls = []
    def missing(project_id, *, store):
        calls.append(project_id)
        raise KeyError(project_id)
    monkeypatch.setattr(services, "get_research_project", missing)
    response = TestClient(web.create_app()).get('/jobs/foreign/plan')
    assert response.status_code == 200 and calls == ["foreign"]
    assert "sl-research-plan-assessment" not in response.text
    monkeypatch.setattr(services, "get_research_project", lambda *args, **kwargs: {"id": "absent-plan", "title": "Existing project"})
    monkeypatch.setattr(services, "get_plan", lambda *args, **kwargs: None)
    response = TestClient(web.create_app()).get('/jobs/absent-plan/plan')
    assert response.status_code == 200 and "sl-research-plan-assessment" not in response.text


def test_native_read_failure_or_extension_keeps_product_plan(examples, monkeypatch):
    from sonaloop.web._i18n import t
    pid = case(examples, "assessment-open")["input"]["project_id"]
    original = services.assess_project
    def extension(project_id, *, store):
        return {**original(project_id, store=store), "unknown": {"nested": True}}
    monkeypatch.setattr(services, "assess_project", extension)
    response = TestClient(web.create_app()).get(f'/jobs/{pid}/plan')
    assert response.status_code == 200 and t("rpa_unavailable") in response.text
    assert "Inspect a handover" in response.text and "sl-research-plan-document" in response.text
    def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic decoder failure")
    monkeypatch.setattr(services, "export_plan_md", unavailable)
    response = TestClient(web.create_app()).get(f'/jobs/{pid}/plan')
    assert response.status_code == 200 and "Inspect a handover" in response.text
    assert response.text.count(t("rpa_unavailable")) == 2 and "Synthetic decoder failure" not in response.text


def test_original_mcp_contract_and_envelopes_unchanged_by_rendering(examples):
    from sonaloop.ui_components import plan_assessment as ui
    from sonaloop.mcp_server import build_server
    server = original_server()
    original = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    built = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    for name in TOOLS:
        assert original[name].inputSchema == built[name].inputSchema
        assert original[name].outputSchema == built[name].outputSchema
        item = next(item for item in examples if item["tool"] == name)
        envelope = server._tool_manager._tools[name].fn(**item["input"])
        before = deepcopy(envelope)
        result = (ui.assessment if name == "assess_project" else ui.document)(envelope["data"])
        assert result[1] == "ready" and envelope == before

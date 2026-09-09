"""Native Memory writer returns, shared content and strictly passive presentation."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from sonaloop import artifacts, services
from sonaloop.storage import Store
from sonaloop.ui_components import memory_outcomes as view
from conftest import create_persona
from test_memory_ui_prerequisites import PLAN, DIGEST, _host_content

NAMES = {"record_memory_deltas": view.consolidation, "put_digest": view.digest,
         "list_digests": view.digests, "record_day": view.day, "record_month_bundle": view.month,
         "summarize_persona_period": view.summary, "extract_pain_points": view.pain_points}
DELTAS = {"entities": [{"mention": "Handover", "kind": "project", "status": "open"}],
          "facts": [{"entity": "Handover", "fact": "A named owner is still needed."}],
          "threads": [], "event_links": []}


@pytest.fixture
def inputs(store):
    pid = create_persona(store, "Recorded memory outcomes")
    blocks, activities = _host_content(store, pid)
    return {
        "record_memory_deltas": {"persona_id": pid, "date": "2026-06-02", "deltas": DELTAS},
        "put_digest": {"persona_id": pid, "scope": "week", "date": "2026-06-02", "digest": {
            **DIGEST, "project_arcs": [{"name": "Handover", "arc": "The owner remains unnamed."}],
            "trends": ["Uncertainty persists"]}},
        "list_digests": {"persona_id": pid, "scope": "week"},
        "record_day": {"persona_id": pid, "date": "2026-06-02", "day_plan": blocks,
                       "plan": PLAN, "activities": activities},
        "record_month_bundle": {"persona_id": pid, "month": "2026-06", "bundle": {
            "period_plan": PLAN, "digest": DIGEST, "days": [{"date": "2026-06-02", "day_plan": PLAN,
                "plan": blocks, "activities": activities,
                "deltas": {"entities": [], "facts": [], "threads": [], "event_links": []}}]}},
        "summarize_persona_period": {"persona_id": pid, "start_date": "2026-06-02", "end_date": "2026-06-03"},
        "extract_pain_points": {"persona_id": pid, "start_date": "2026-06-02", "end_date": "2026-06-03"}}


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_simulation
    server = FastMCP("original-memory-outcomes")
    _tools_simulation.register_simulation(server)
    return server


def native_values(inputs):
    server = original_server()
    return {name: server._tool_manager._tools[name].fn(**arguments)["data"] for name, arguments in inputs.items()}


def test_actual_original_native_outcomes_export(inputs, tmp_path):
    server = original_server()
    cases = [(name, name, arguments) for name, arguments in inputs.items()]
    pid = inputs["record_day"]["persona_id"]
    cases += [("deltas-repeated", "record_memory_deltas", inputs["record_memory_deltas"]),
              ("digests-empty", "list_digests", {"persona_id": pid, "scope": "year"}),
              ("experience-empty", "summarize_persona_period", {"persona_id": pid, "start_date": "2027-01-01"}),
              ("pains-empty", "extract_pain_points", {"persona_id": pid, "start_date": "2027-01-01"})]
    examples = []
    for scenario, name, arguments in cases:
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        html, state = NAMES[name](value)
        assert state == ("empty" if scenario.endswith("empty") else "ready")
        assert len(json.dumps({"name": name, "value": value}, ensure_ascii=False).encode()) <= 8192
        examples.append({"scenario": scenario, "tool": name, "input": arguments, "value": value, "state": state})
    assert examples[0]["value"]["entities_created"] == 1
    assert examples[7]["value"]["entities_created"] == 0 and examples[7]["value"]["facts"] == 1
    path = Path(os.environ.get("RESEARCH_MEMORY_OUTCOMES_FIXTURE_PATH", tmp_path / "memory-outcomes-fixtures.json"))
    path.write_text(json.dumps(examples, indent=2, ensure_ascii=False))
    print("Actual isolated native Memory outcome fixtures:", path)


def forbidden(*args, **kwargs):
    pytest.fail("Passive outcome presentation attempted native or filesystem I/O")


def test_pure_outcomes_keep_zero_counts_and_do_not_retry(inputs, monkeypatch):
    from sonaloop.web import _render
    values = native_values(inputs)
    for name, value in values.items():
        NAMES[name](value)
    before = deepcopy(values)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(_render, "_avatar", forbidden)
        for name in NAMES:
            patch.setattr(services, name, forbidden)
        for method in ("open", "read_text", "exists", "is_file"):
            patch.setattr(Path, method, forbidden)
        for name, value in values.items():
            html, state = NAMES[name](value)
            assert state == "ready"
            assert all(tag not in html for tag in ("<a ", "<img", "<script", "<pre", "<button", "<form"))
    assert before == values
    html, _ = view.consolidation(values["record_memory_deltas"])
    assert ">0<" in html and "Reported processing counts" in html and "Objects reported disabled" in html
    html, _ = view.month(values["record_month_bundle"])
    assert "2026-06-02" in html and ">5<" in html and ">0<" in html


def test_embedding_batch_outcome_keeps_literal_native_counters(inputs):
    value = native_values(inputs)["record_memory_deltas"]
    # Native backfill may report the complete todo count as disabled after a
    # later batch returns no vectors, even when an earlier batch embedded 128.
    value["embeddings"] = {"embedded": 128, "skipped_existing": 0, "disabled": 129}
    html, _ = view.consolidation(value)
    assert ">128<" in html and ">129<" in html and "Objects reported disabled" in html
    assert "Objects without embedding" not in html


def test_full_digest_summary_and_pain_provenance_escape(inputs):
    values = native_values(inputs)
    digest = values["put_digest"]
    digest["text"] = "A long record. " * 220 + "Final qualifier <script>bad()</script>"
    html, _ = view.digest(digest)
    assert "Final qualifier &lt;script&gt;" in html and "Uncertainty persists" in html and "sl-clamp" not in html
    summary = values["summarize_persona_period"]
    html, _ = view.summary(summary)
    assert str(summary["events"]) in html and "at most 20 completed" in html and "latest 10 open-loop" in html
    pain = values["extract_pain_points"][0]
    pain["evidence_event_ids"] = ["event_fixture#line:2"]
    pain["issue"] = '<img src=x onerror="bad()">'
    html, _ = view.pain_points([pain])
    assert "&lt;img" in html and "<img" not in html and "event_fixture#line:2" in html
    assert "supplies no evidence event IDs" not in html
    pain["evidence_event_ids"] = []
    assert "supplies no evidence event IDs" in view.pain_points([pain])[0]


def test_product_pain_body_preserves_legacy_primitive():
    from sonaloop.web._render import render_findings
    legacy = {"issue": "Legacy issue", "opportunity": "Inspect the workflow"}
    assert view.pain_content([legacy]) == render_findings([artifacts.pain_point_finding(legacy)])
    with pytest.raises(ValueError):
        view.pain_content([legacy], passive=True)


@pytest.mark.parametrize("name,mutate", [
    ("record_day", lambda v: v.update(activities=True)),
    ("record_month_bundle", lambda v: v["days"][0].update(facts=-1)),
    ("record_memory_deltas", lambda v: v["embeddings"].update(disabled="0")),
    ("put_digest", lambda v: v.update(project_arcs=[{}])),
    ("summarize_persona_period", lambda v: v.update(top_pain_points=[["pain", False]])),
    ("extract_pain_points", lambda v: v[0].update(evidence_event_ids=[{}])),
])
def test_malformed_native_outcomes_fail_soft(inputs, name, mutate):
    value = native_values(inputs)[name]
    mutate(value)
    with pytest.raises(ValueError):
        NAMES[name](value)


def test_seven_fastmcp_outcomes_preserve_native_schema_text_and_single_execution(inputs, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_simulation
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    calls, env = [], _tools_simulation._env
    def capture(name, *args, **kwargs):
        result = env(name, *args, **kwargs)
        calls.append((name, deepcopy(result)))
        return result
    monkeypatch.setattr(_tools_simulation, "_env", capture)
    for name, arguments in inputs.items():
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/memory/v1"
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and calls[-1][0] == name
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(calls[-1][1])
        assert result.content == text and result.structuredContent == structured
        meta = result.meta["sonaloop/presentation"]
        assert meta["tool"] == name and meta["state"] == "ready"
        assert meta["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
    assert len(calls) == len(NAMES), "No writer retry or hidden getter"

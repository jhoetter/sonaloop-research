"""Captured reference text and capture status are shared without an implicit network read."""
import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from sonaloop import services, web
from sonaloop.storage import Store
from sonaloop.ui_components import references


def record():
    return {"id": "r", "kind": "variant", "url": "https://example.invalid/reference", "title": "Reference A", "label": "A",
            "snapshot": {"ok": True, "mode": "text", "description": "Only a supplied snapshot", "text": "Final captured line.",
                         "headings": [f"Heading {i}" for i in range(12)]}}


def forbidden(*args, **kwargs):
    pytest.fail("Rendering attempted storage or network access")


def test_full_passive_snapshot_keeps_all_supplied_headings_and_text_without_io(monkeypatch):
    from sonaloop import capture
    value = record(); value["snapshot"]["text"] = "Context. " * 500 + "Last scope qualifier."
    before = deepcopy(value)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(capture, "capture_url", forbidden)
        patch.setattr(Path, "open", forbidden)
        html, state = references.reference(value)
    assert state == "ready" and value == before
    for text in ("Heading 11", "Last scope qualifier.", value["url"], "Captured"):
        assert text in html
    assert "<a " not in html and "<iframe" not in html and "<details" not in html


def test_skipped_and_failed_capture_are_not_success_or_retried():
    value = record()
    value["snapshot"] = {"ok": False, "mode": "skipped", "headings": [], "text": ""}
    html, state = references.reference(value)
    assert state == "ready" and "Capture skipped" in html and "Capture failed" not in html
    value["snapshot"] = {"ok": False, "mode": "unavailable", "headings": [], "error": "Actual captured error"}
    html, state = references.reference(value)
    assert state == "ready" and "Actual captured error" in html and "Capture skipped" not in html
    html, state = references.references([])
    assert state == "empty"
    html, state = references.removed({"deleted": 0})
    assert state == "ready" and "0 references removed" in html


@pytest.mark.parametrize("change", [lambda x: x.pop("url"), lambda x: x.update(kind="other"),
    lambda x: x.update(snapshot={}), lambda x: x["snapshot"].update(ok="true"),
    lambda x: x["snapshot"].update(headings=[None]), lambda x: x["snapshot"].update(text=4)])
def test_malformed_snapshot_does_not_invent_a_capture(change):
    value = record(); change(value)
    with pytest.raises(ValueError):
        references.reference(value)


def test_snapshot_url_and_content_are_escaped():
    value = record(); value["url"] = 'javascript:alert(1)'
    value["snapshot"]["text"] = "<img src=x onerror=bad()>"
    html, _ = references.reference(value)
    assert "&lt;img" in html and "<img" not in html and "href=" not in html


def test_product_reference_page_uses_same_snapshot_core(store, monkeypatch):
    from starlette.testclient import TestClient
    project = services.create_research_project("References", "Isolated test", store=store)
    value = services.add_artifact(project["id"], "https://example.invalid/reference", capture=False, store=store)
    calls = []
    original = references.snapshot_content
    def observe(snapshot, **kwargs):
        calls.append((deepcopy(snapshot), kwargs))
        return original(snapshot, **kwargs)
    monkeypatch.setattr(references, "snapshot_content", observe)
    response = TestClient(web.create_app()).get(f'/references/{value["id"]}')
    assert response.status_code == 200 and calls == [(value["snapshot"], {})]
    assert 'href="https://example.invalid/reference"' in response.text
    # Product retains its existing compact presentation; passive gets the full supplied body.
    assert "Heading 11" not in references.snapshot_content(record()["snapshot"])
    assert "Heading 11" in references.snapshot_content(record()["snapshot"], passive=True)


def test_actual_native_reference_tools_keep_sdk_results_and_do_not_recapture(store, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from sonaloop import capture
    from sonaloop.mcp_server import build_server, _tools_council
    original = FastMCP("native-reference"); _tools_council.register_council(original)
    server = build_server()
    before = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    after = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    names = ("add_artifact", "get_artifact", "list_artifacts", "delete_artifact")
    for name in names:
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].meta["ui"]["resourceUri"] == "ui://sonaloop/references/v1"
    monkeypatch.setattr(capture, "capture_url", forbidden)
    envelopes = []
    native_env = _tools_council._env
    def observe(name, *args):
        result = native_env(name, *args)
        envelopes.append((name, deepcopy(result)))
        return result
    monkeypatch.setattr(_tools_council, "_env", observe)
    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError
        content, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1][1])
        assert result.content == content and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["tool"] == name
        assert "dispatch_token" not in result.meta["sonaloop/presentation"]["html"]
        return structured["data"], result.meta["sonaloop/presentation"]["html"]
    project = services.create_research_project("Native reference UI", "No network", store=store)
    value, html = call("add_artifact", project_id=project["id"], url="https://example.invalid/reference", capture=False)
    assert value["snapshot"]["mode"] == "skipped" and "Capture skipped" in html
    fetched, _ = call("get_artifact", project_id=project["id"], artifact_id=value["label"])
    assert fetched["id"] == value["id"]
    listed, _ = call("list_artifacts", project_id=project["id"])
    assert listed == [fetched]
    deleted, html = call("delete_artifact", project_id=project["id"], artifact_id=value["id"])
    assert deleted == {"deleted": 1} and "1 references removed" in html
    assert [name for name, _ in envelopes] == list(names)


def test_successful_empty_capture_has_no_false_failure_in_product_or_passive():
    from sonaloop.web.pages.library import _reference_status_pill
    value = record(); value["snapshot"].update(text="", description="", headings=[], status=204)
    for html in (references.snapshot_content(value["snapshot"]), references.reference(value)[0]):
        assert "Capture succeeded but supplied no text." in html
        assert "Capture failed" not in html
    assert ">captured</span>" in _reference_status_pill(value)
    value["snapshot"].update(ok=False, mode="skipped")
    assert "Capture skipped" in _reference_status_pill(value)
    assert "Capture failed" not in _reference_status_pill(value)

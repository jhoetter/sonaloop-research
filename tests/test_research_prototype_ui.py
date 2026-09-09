"""Prototype metadata is shared; presentation never launches or loads an app."""
import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from sonaloop import prototypes as native, services, web
from sonaloop.ui_components import prototypes


def record():
    return {"id": "prototype_fixture", "slug": "handover", "project_id": "project_fixture",
            "name": "Handover prototype", "version": "v0.2", "kind": "web", "type": "prototype",
            "path": "prototypes/handover", "entry": "index.html", "run": "static", "run_cmd": None,
            "notes": "Keep the owner visible.", "created_at": "2026-09-09T00:00:00Z",
            "fidelity": "midfi", "tags": ["midfi"], "url": ""}


def forbidden(*args, **kwargs):
    pytest.fail("Prototype presentation attempted runtime access")


def test_passive_metadata_preserves_all_notes_and_never_probes_locations(monkeypatch):
    value = {**record(), "notes": "Full note. " * 900 + "Final sentence.",
             "running": False, "url": "http://127.0.0.1:9999/private"}
    before = deepcopy(value)
    with monkeypatch.context() as patch:
        patch.setattr(services, "get_prototype_artifact", forbidden)
        patch.setattr(services, "prototype_entry_available", forbidden)
        patch.setattr(native, "run_prototype", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "exists", forbidden)
        html, state = prototypes.prototype(value)
    assert value == before and state == "ready"
    for text in ("Final sentence.", "v0.2", "midfi", "http://127.0.0.1:9999/private",
                 "No local process", "neither loaded nor executed"):
        assert text in html
    for text in ("<iframe", "<img", "<a ", "<button", "Process ID", "Prototype sessions"):
        assert text not in html


def test_untrusted_prototype_text_is_escaped_and_remote_note_is_actual():
    value = record()
    for key in ("name", "path", "entry", "notes", "version"):
        value[key] = '<script>alert("unsafe")</script>'
    html, _ = prototypes.registered_remote({"prototype": value, "note": {
        "id": "paired", "title": "Actual paired concept", "text": "Native concept text."},
        "dispatch": {"dispatch_token": "private-token"}})
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Actual paired concept" in html and "Native concept text." in html
    assert "private-token" not in html


@pytest.mark.parametrize("patch", [{"id": ""}, {"name": None}, {"path": []}, {"notes": {}},
    {"running": "false"}, {"url": None}, {"tags": [42]}, {"project_id": {}}, {"entry": None}])
def test_incomplete_native_records_do_not_invent_a_view(patch):
    with pytest.raises(ValueError):
        prototypes.prototype({**record(), **patch})


def test_run_remote_local_and_reused_states_do_not_conflate_processes():
    remote = {"prototype_id": "p", "url": "https://example.invalid/prototype", "pid": None,
              "running": False, "remote": True}
    html, _ = prototypes.running(remote)
    assert "Hosted prototype address" in html and "Process ID" not in html and "Local process started" not in html
    local = {"prototype_id": "p", "url": "http://127.0.0.1:17471/", "pid": 12345}
    html, _ = prototypes.running(local)
    assert "Local process started" in html and "12345" in html
    html, _ = prototypes.running({**local, "already_running": True})
    assert "Existing local process" in html
    for bad in ({**remote, "pid": 123}, {**remote, "running": True}, {**local, "pid": True},
                {**local, "pid": None}, {**local, "already_running": 1}):
        with pytest.raises(ValueError):
            prototypes.running(bad)


def test_empty_stop_and_delete_receipts_do_not_invent_identity_or_destroyed_files():
    html, state = prototypes.prototypes([])
    assert state == "empty" and "No prototypes" in html
    html, state = prototypes.stopped({"stopped": False})
    assert state == "ready" and "No local process was found" in html and "prototype_fixture" not in html
    html, _ = prototypes.stopped({"stopped": True, "prototype_id": "actual"})
    assert "actual" in html and "native runner reports" in html
    for count in (0, 1):
        html, _ = prototypes.removed({"deleted": count})
        assert f"Prototype records deleted: {count}" in html and "Files on disk remain" in html
    for fn, value in ((prototypes.removed, {"deleted": True}), (prototypes.stopped, {"stopped": True})):
        with pytest.raises(ValueError):
            fn(value)


def test_product_reuses_body_and_properties_with_its_prepared_preview(store, tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop import config
    monkeypatch.setattr(config, "prototypes_dir", lambda: tmp_path)
    monkeypatch.setattr(native, "prototypes_dir", lambda: tmp_path)
    project = services.create_research_project("Prototype view", "Synthetic", store=store)
    value = services.scaffold_prototype("shared-body", "Shared body", {"title": "Fixture", "screens": [{"id": "home", "title": "Handover", "elements": []}]},
                                        project_id=project["id"], store=store)
    value["notes"] = "Actual native notes now visible."; store.upsert_prototype(value)
    called = []
    for name in ("prototype_content", "prototype_properties"):
        original = getattr(prototypes, name)
        def observed(*args, _name=name, _original=original, **kwargs):
            called.append((_name, kwargs)); return _original(*args, **kwargs)
        monkeypatch.setattr(prototypes, name, observed)
    response = TestClient(web.create_app()).get(f'/prototypes/{value["id"]}')
    assert response.status_code == 200 and "Actual native notes now visible." in response.text
    assert [name for name, _ in called] == ["prototype_content", "prototype_properties"]
    assert '<iframe' in str(called[0][1]["preview"])
    assert called[0][1]["session_count"] == called[1][1]["session_count"] == 0
    assert 'id="sec-notes"' in response.text and 'href="#sec-notes"' in response.text
    assert f'/proto-files/{value["slug"]}/index.html' in response.text


def test_eight_real_native_mcp_tools_keep_exact_original_outputs_and_cleanup(store, tmp_path, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from sonaloop import config
    from sonaloop.mcp_server import build_server, _tools_prototypes
    monkeypatch.setattr(native, "prototypes_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "prototypes_dir", lambda: tmp_path)
    original = FastMCP("original-prototypes"); _tools_prototypes.register_prototypes(original)
    server = build_server()
    names = ("scaffold_prototype", "register_prototype", "register_remote_prototype", "get_prototype",
             "list_prototypes", "run_prototype", "stop_prototype", "delete_prototype")
    before = {x.name: x for x in asyncio.run(original.list_tools())}
    after = {x.name: x for x in asyncio.run(server.list_tools())}
    for name in names:
        assert before[name].inputSchema == after[name].inputSchema
        assert before[name].outputSchema == after[name].outputSchema
        assert after[name].meta["ui"]["resourceUri"] == "ui://sonaloop/prototypes/v1"
    envelopes = []; env = _tools_prototypes._env
    def capture(name, *args):
        value = env(name, *args); envelopes.append((name, deepcopy(value))); return value
    monkeypatch.setattr(_tools_prototypes, "_env", capture)
    def call(tool_name, **args):
        result = asyncio.run(server.call_tool(tool_name, args)); assert not result.isError
        content, structured = original._tool_manager._tools[tool_name].fn_metadata.convert_result(envelopes[-1][1])
        assert result.content == content and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["tool"] == tool_name
        return structured["data"], result.meta["sonaloop/presentation"]["html"]
    project = services.create_research_project("Native prototype UI", "Temporary files and processes", store=store)
    local, _ = call("scaffold_prototype", slug="local-ui", name="Local UI", concept={"title": "Local", "screens": [{"id": "home", "title": "Handover", "elements": []}]})
    try:
        call("register_prototype", slug="local-ui", name="Local UI", path=local["path"], notes="Native note")
        remote, _ = call("register_remote_prototype", slug="remote-ui", name="Remote UI", url="https://example.invalid/prototype", project_id=project["id"])
        call("get_prototype", prototype_id=local["id"])
        listed, _ = call("list_prototypes")
        assert len(listed) == 2
        running, html = call("run_prototype", prototype_id=local["id"])
        assert running["pid"] > 0 and "Local process started" in html
        same, _ = call("run_prototype", prototype_id=local["id"])
        assert same["pid"] == running["pid"] and same["already_running"] is True
        remote_run, html = call("run_prototype", prototype_id=remote["prototype"]["id"])
        assert remote_run["pid"] is None and "Hosted prototype address" in html
        stopped, _ = call("stop_prototype", prototype_id=local["id"])
        assert stopped["stopped"] is True and local["id"] not in native._PROCS
        call("stop_prototype", prototype_id=local["id"])
        deleted, _ = call("delete_prototype", prototype_id=local["id"])
        assert deleted == {"deleted": 1} and (tmp_path / "local-ui" / "index.html").exists()
        assert {name for name, _ in envelopes} == set(names)
        assert len(envelopes) == 11, "Presentation never repeats a native call"
    finally:
        native.stop_prototype(local["id"], store=store)
    assert local["id"] not in native._PROCS

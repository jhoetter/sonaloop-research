"""Real native asset metadata and the shared product/Apps body remain separate from pixels."""
import asyncio
import base64
from copy import deepcopy
from pathlib import Path

import pytest

from sonaloop import artifacts, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import assets


def record():
    return {"id": "asset_fixture", "filename": "notes.txt", "title": "Handover evidence",
            "kind": "document", "direction": "out", "bytes": 21, "media_type": "text/plain",
            "text_excerpt": "Keep the owner clear.", "source": "synthesis:fixture",
            "notes": "A synthetic reference, not research evidence.", "created_at": "2026-09-09T00:00:00Z",
            "supersedes": [{"id": "old", "filename": "old.txt", "created_at": "2026-09-08"}]}


def forbidden(*args, **kwargs):
    pytest.fail("Passive asset presentation attempted a runtime lookup")


def test_passive_asset_uses_only_supplied_full_excerpt_and_provenance(monkeypatch):
    value = record()
    value["text_excerpt"] = "Complete evidence. " * 400 + "Final qualification."
    value["source"] = "https://invalid.example/private"
    value.update(url="file:///private/image.png", preview_url="https://invalid.example/pixels")
    before = deepcopy(value)
    # The product may prepare media and sources before calling the pure core.
    from sonaloop.web import _presence, _render
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(_render, "render_ref", forbidden)
        patch.setattr(_presence, "asset_content_url", forbidden)
        patch.setattr(_presence, "asset_preview_html", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "exists", forbidden)
        html, state = assets.asset(value)
    assert state == "ready" and value == before
    for text in ("Final qualification.", "https://invalid.example/private", "old.txt", "2026-09-08",
                 "image pixels were not supplied", "text/plain"):
        assert text in html
    for unsafe in ("<img", "<a ", "<details", "file:///private", "https://invalid.example/pixels"):
        assert unsafe not in html


def test_asset_escapes_excerpt_identity_and_source():
    value = record()
    for key in ("filename", "title", "source", "text_excerpt", "notes"):
        value[key] = "<script>unsafe()</script>"
    html, _ = assets.asset(value)
    assert "<script>" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("change", [lambda x: x.pop("bytes"), lambda x: x.update(bytes=True),
    lambda x: x.update(bytes=-1), lambda x: x.update(filename=""), lambda x: x.update(media_type=None),
    lambda x: x.update(kind="future"), lambda x: x.update(text_excerpt=[]),
    lambda x: x.update(supersedes=["unknown"]), lambda x: x.update(source={"id": "other"})])
def test_partial_or_malformed_asset_never_invents_metadata(change):
    value = record(); change(value)
    with pytest.raises(ValueError):
        assets.asset(value)


def test_empty_list_and_detach_counts_have_truthful_distinct_states():
    html, state = assets.assets([])
    assert state == "empty" and "No files in this response" in html
    for count in (0, 1, 3):
        html, state = assets.removed({"deleted": count})
        assert state == "ready" and f"{count} files detached" in html
        assert "contents remain" in html and "asset_fixture" not in html
    with pytest.raises(ValueError):
        assets.removed({"deleted": True})


def test_product_asset_detail_uses_same_identity_excerpt_and_provenance(store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.web import _presence
    project = services.create_research_project("Asset UI", "Synthetic isolated test", store=store)
    value = services.attach_asset(project["id"], content_base64=base64.b64encode(b"Keep the owner clear.").decode(),
                                 filename="notes.txt", title="Handover evidence", store=store)
    calls = []
    for name in ("file_identity", "asset_content", "provenance_content"):
        original = getattr(assets, name)
        def observe(*args, _name=name, _original=original, **kwargs):
            calls.append((_name, kwargs.get("passive", False)))
            return _original(*args, **kwargs)
        monkeypatch.setattr(assets, name, observe)
    response = TestClient(web.create_app()).get(f'/assets/{value["id"]}')
    assert response.status_code == 200 and "Keep the owner clear." in response.text
    assert calls == [("file_identity", False), ("provenance_content", False), ("asset_content", False)]
    assert 'href="/data/assets/' in response.text, "Product retains its prepared download authority"
    assert 'class="sl-file__name sl-research-file-name"' in response.text
    assert "<svg" in response.text and "&lt;svg" not in response.text


def test_actual_native_mcp_attach_get_list_remove_keep_all_original_output(store, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_assets
    original = FastMCP("original-assets"); _tools_assets.register_assets(original)
    server = build_server()
    names = ("attach_asset", "get_asset", "list_assets", "remove_asset", "attach_prototype_shot", "admit_remote_screenshot")
    original_tools = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    decorated_tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in names:
        before = original_tools[name]
        after = decorated_tools[name]
        assert before.inputSchema == after.inputSchema
        assert before.outputSchema == after.outputSchema
        assert after.meta["ui"]["resourceUri"] == "ui://sonaloop/assets/v1"
    envelopes = []
    native_env = _tools_assets._env
    def capture(name, *args):
        result = native_env(name, *args)
        envelopes.append((name, deepcopy(result)))
        return result
    monkeypatch.setattr(_tools_assets, "_env", capture)
    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError
        content, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1][1])
        assert result.content == content and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["tool"] == name
        assert "dispatch_token" not in result.meta["sonaloop/presentation"]["html"]
        return result.structuredContent["data"], result.meta["sonaloop/presentation"]["html"]
    project = services.create_research_project("Native asset UI", "Temporary files only", store=store)
    value, html = call("attach_asset", project_id=project["id"], content_base64=base64.b64encode(b"Exact native excerpt.").decode(), filename="handover.txt", title="Handover", notes="Scoped fixture")
    assert "Exact native excerpt." in html
    fetched, _ = call("get_asset", project_id=project["id"], asset_id=value["id"])
    assert fetched["id"] == value["id"]
    listed, list_html = call("list_assets", project_id=project["id"])
    assert "text_excerpt" not in listed[0] and "Exact native excerpt." not in list_html
    removed, html = call("remove_asset", project_id=project["id"], asset_id=value["id"])
    assert removed == {"deleted": 1} and "1 files detached" in html
    assert services.list_assets(project["id"], store=store) == []
    assert [name for name, _ in envelopes] == list(names[:4]), "Decoration never repeats a native invocation"

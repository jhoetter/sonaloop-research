"""Protocol/visibility/media boundary checks; native operation tests live separately."""
import asyncio
from io import BytesIO
import hashlib
from types import SimpleNamespace

from PIL import Image
from sonaloop.mcp_server import build_server
from sonaloop.mcp_server import _tools_persona_surface as adapter
from sonaloop.persona_surface_contract import RESOURCE_URI, RESOURCE_MIME, PersonaSurfaceError


def test_surface_discovery_has_standard_ui_metadata_and_truthful_visibility():
    server = build_server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in ("get_persona_surface", "record_persona_surface"):
        assert tools[name].meta["ui"] == {"resourceUri": RESOURCE_URI, "visibility": ["model", "app"]}
    for name in ("update_persona_surface", "generate_persona_surface_avatar", "get_persona_surface_operation"):
        assert tools[name].meta["ui"]["visibility"] == ["app"]
    assert tools["get_persona_surface"].annotations.readOnlyHint
    assert not tools["generate_persona_surface_avatar"].annotations.readOnlyHint
    assert tools["generate_persona_surface_avatar"].annotations.openWorldHint
    resources = asyncio.run(server.list_resources())
    resource = next(resource for resource in resources if str(resource.uri) == RESOURCE_URI)
    assert resource.mimeType == RESOURCE_MIME
    assert resource.meta["ui"]["csp"]["connectDomains"] == []


def test_tool_result_keeps_private_pixels_out_of_model_fields(monkeypatch):
    dto = {"persona_id": "persona_test", "fields": {"display_name": "A <script>name</script>"},
           "avatar": {"sha256": "f" * 64}}
    monkeypatch.setattr(adapter, "_service", lambda: SimpleNamespace(get_persona_surface=lambda _: dto))
    monkeypatch.setattr(adapter, "_private_avatar", lambda *_: "data:image/png;base64,PRIVATE")
    result = asyncio.run(build_server().call_tool("get_persona_surface", {"persona_id": "persona_test"}))
    assert result.structuredContent == dto
    assert result.meta["sonaloop/avatarDataUri"].endswith("PRIVATE")
    assert all("PRIVATE" not in item.text for item in result.content)


def test_public_failure_is_bounded_and_unexpected_error_is_sanitized():
    def public_error():
        raise PersonaSurfaceError("conflict", "Refresh the current profile.", operation_id="one")
    result = adapter._result(public_error)
    assert result.isError
    assert result.structuredContent["error"]["code"] == "conflict"
    def private_error():
        raise RuntimeError("Bearer SECRET /private/provider/body")
    result = adapter._result(private_error)
    assert "SECRET" not in result.model_dump_json()
    assert result.structuredContent["error"]["code"] == "outcome_unknown"


def test_media_decode_size_and_exact_hash(monkeypatch):
    from sonaloop import avatar
    payload = BytesIO()
    Image.new("RGB", (8, 8), "green").save(payload, format="PNG")
    data = payload.getvalue()
    monkeypatch.setattr(avatar, "get_persona_avatar_content", lambda _: (data, {}))
    assert adapter._private_avatar("p", hashlib.sha256(data).hexdigest()).startswith("data:image/png;base64,")
    assert adapter._private_avatar("p", "0" * 64) is None
    broken = b"\x89PNG\r\n\x1a\nnot-an-image"
    monkeypatch.setattr(avatar, "get_persona_avatar_content", lambda _: (broken, {}))
    assert adapter._private_avatar("p", hashlib.sha256(broken).hexdigest()) is None
    large = BytesIO()
    Image.new("RGB", (2049, 1)).save(large, format="PNG")
    data = large.getvalue()
    monkeypatch.setattr(avatar, "get_persona_avatar_content", lambda _: (data, {}))
    assert adapter._private_avatar("p", hashlib.sha256(data).hexdigest()) is None

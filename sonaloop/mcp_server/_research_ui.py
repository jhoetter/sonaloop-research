"""Attach passive customer UI to unchanged native core tool results.

This is presentation decoration, not a facade: original signatures, output
schemas, text blocks, errors, annotations and invocation count are preserved.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import json
from pathlib import Path

from ..ui_components.registry import SCHEMA, SURFACES, render_tool

MAX_PRESENTATION_BYTES = 192 * 1024


def present(name, raw_result, metadata):
    from mcp.types import CallToolResult
    converted = metadata.convert_result(raw_result)
    if isinstance(converted, CallToolResult):
        result = converted.model_copy(deep=True)
    elif isinstance(converted, tuple):
        result = CallToolResult(content=converted[0], structuredContent=converted[1])
    else:
        result = CallToolResult(content=converted)
    if result.isError:
        return result
    try:
        html, state = render_tool(name, raw_result)
        html = str(html)
        if len(html.encode("utf-8")) > MAX_PRESENTATION_BYTES:
            return result
        native_text = "\n".join(block.text for block in result.content if block.type == "text")
        result.meta = {**(result.meta or {}), "sonaloop/presentation": {
            "schema_version": SCHEMA, "component_id": SURFACES[name].component_id,
            "tool": name, "state": state, "html": html,
            "text_sha256": hashlib.sha256(native_text.encode("utf-8")).hexdigest(),
        }}
    except Exception:
        # A projection failure cannot erase the actual native result, repeat a
        # write, or claim its outcome is unknown. Text remains canonical.
        pass
    return result


def _decorate(tool):
    original, metadata, name = tool.fn, tool.fn_metadata, tool.name
    if tool.is_async:
        @wraps(original)
        async def wrapped(**kwargs):
            return present(name, await original(**kwargs), metadata)
    else:
        @wraps(original)
        def wrapped(**kwargs):
            return present(name, original(**kwargs), metadata)
    tool.fn = wrapped
    surface = SURFACES[name]
    tool.meta = {**(tool.meta or {}),
                 "sonaloop/uiManifestUri": f"sonaloop://ui/{surface.family}/manifest",
                 "ui": {"resourceUri": surface.uri, "visibility": ["model", "app"]}}


def _resource(mcp, surface):
    root = Path(__file__).parent / "ui"
    manifest_path = root / f"{surface.family}.manifest.json"
    manifest_text = manifest_path.read_text()
    manifest = json.loads(manifest_text)
    data = (root / manifest["resource"]["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["resource"]["sha256"]:
        raise ValueError(f"Invalid UI resource for {surface.family}")

    @mcp.resource(surface.uri, name=surface.family.title(), mime_type="text/html;profile=mcp-app",
                  meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}})
    def app_resource() -> str:
        return data.decode("utf-8")

    @mcp.resource(f"sonaloop://ui/{surface.family}/manifest", name=f"{surface.family.title()} UI build manifest",
                  mime_type="application/json")
    def app_manifest() -> str:
        return manifest_text


def register_research_ui(mcp):
    """Only explicitly implemented surfaces; Persona and extensions unchanged."""
    for name in SURFACES:
        _decorate(mcp._tool_manager._tools[name])
    for family in sorted({surface.family for surface in SURFACES.values()}):
        _resource(mcp, next(surface for surface in SURFACES.values() if surface.family == family))

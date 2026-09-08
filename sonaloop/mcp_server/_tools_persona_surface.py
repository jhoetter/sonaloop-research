"""MCP Apps transport for the native customer-owned Persona surface."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from typing import Any

from ..persona_surface_contract import (
    MAX_AVATAR_BYTES, MAX_AVATAR_DIMENSION, RESOURCE_MIME, RESOURCE_URI,
    PersonaSurfaceError,
)

MANIFEST_URI = "sonaloop://ui/persona/manifest"


def _service():
    # Kept lazy so registration and text clients do not initialize a runtime store.
    from ..services import _persona_surface
    return _persona_surface


def _private_avatar(persona_id: str, expected_sha: str | None) -> str | None:
    """Bounded native image delivery; a read racing an edit cannot attach wrong bytes."""
    import hashlib
    import warnings
    from PIL import Image
    from ..avatar import get_persona_avatar_content

    if not expected_sha:
        return None
    try:
        data, _ = get_persona_avatar_content(persona_id)
        if len(data) > MAX_AVATAR_BYTES or hashlib.sha256(data).hexdigest() != expected_sha:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as picture:
                if picture.format != "PNG" or max(picture.size) > MAX_AVATAR_DIMENSION:
                    return None
                picture.verify()
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except (OSError, ValueError, KeyError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        return None


def _result(invoke):
    from mcp.types import CallToolResult, TextContent
    try:
        value = invoke()
        dto = value if "persona_id" in value and "fields" in value else value.get("result")
        meta: dict[str, Any] = {}
        if dto:
            data_uri = _private_avatar(dto["persona_id"], dto.get("avatar", {}).get("sha256"))
            if data_uri:
                meta["sonaloop/avatarDataUri"] = data_uri
        # Useful in text-only clients; no filesystem/provider metadata is projected.
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return CallToolResult(content=[TextContent(type="text", text=text)],
                              structuredContent=value, _meta=meta or None)
    except PersonaSurfaceError as error:
        return CallToolResult(isError=True,
            content=[TextContent(type="text", text=str(error))],
            structuredContent={"error": error.as_dict()})
    except KeyError:
        return CallToolResult(isError=True,
            content=[TextContent(type="text", text="Persona or operation not found.")],
            structuredContent={"error": {"code": "not_found", "message": "Persona or operation not found."}})
    except Exception:
        # Do not leak provider response bodies, filesystem paths or credentials.
        return CallToolResult(isError=True,
            content=[TextContent(type="text", text="The native Persona operation could not be completed. Inspect its status before retrying.")],
            structuredContent={"error": {"code": "outcome_unknown", "message": "Inspect the operation status before retrying."}})


def _ui(*, model: bool = False) -> dict[str, Any]:
    return {"sonaloop/uiManifestUri": MANIFEST_URI,
            "ui": {"resourceUri": RESOURCE_URI,
                   "visibility": ["model", "app"] if model else ["app"]}}


def register_persona_surface(mcp):
    @mcp.tool(meta=_ui(model=True), structured_output=False)
    def get_persona_surface(persona_id: str):
        """Read the current native Persona as an editable MCP App card or plain text.
        Use a real ID/slug obtained from list_personas. This read writes nothing."""
        return _result(lambda: _service().get_persona_surface(persona_id))

    @mcp.tool(meta=_ui(model=True), structured_output=False)
    def record_persona_surface(description: str, profile: dict[str, Any],
                               operation_id: str, segment_hint: str | None = None):
        """Create one native Persona and return its editable MCP App card.
        First call brief_persona and author its complete native profile. This writes
        the record; use only when the user requested creation. Choose one operation_id
        per create intent and preserve it on exact transport retry. No image is generated."""
        return _result(lambda: _service().record_persona_surface(
            description, profile, operation_id, segment_hint))

    @mcp.tool(meta=_ui(), structured_output=False)
    def update_persona_surface(persona_id: str, changes: dict[str, Any],
                               expected_version: str, operation_id: str):
        """Save explicit card edits against the current native version; exact retry is safe."""
        return _result(lambda: _service().update_persona_surface(
            persona_id, changes, expected_version, operation_id))

    @mcp.tool(meta=_ui(), structured_output=False)
    def generate_persona_surface_avatar(persona_id: str, prompt: str,
                                        expected_version: str, operation_id: str):
        """Generate the native portrait for this exact profile. This can incur provider
        cost. Preserve the operation ID; inspect unknown outcomes instead of retrying."""
        return _result(lambda: _service().generate_persona_surface_avatar(
            persona_id, prompt, expected_version, operation_id))

    @mcp.tool(meta=_ui(), structured_output=False)
    def get_persona_surface_operation(operation_id: str):
        """Inspect a native Persona operation without repeating it or generating an image."""
        return _result(lambda: _service().get_persona_surface_operation(operation_id))

    @mcp.resource(RESOURCE_URI, name="Persona", mime_type=RESOURCE_MIME,
                  meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}})
    def persona_surface_app() -> str:
        """The same customer-owned PersonaView used by the Research product page."""
        root = Path(__file__).parent / "ui"
        return (root / "persona.html").read_text(encoding="utf-8")

    @mcp.resource(MANIFEST_URI, name="Persona UI build manifest", mime_type="application/json")
    def persona_surface_manifest() -> str:
        """Customer component, source and artifact hashes; a declaration, not a grant."""
        return (Path(__file__).parent / "ui" / "persona.manifest.json").read_text(encoding="utf-8")

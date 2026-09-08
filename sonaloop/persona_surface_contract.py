"""Versioned transport-neutral PersonaView contract. No runtime/store imports.

The native service is the sole authority. Browser adapters only project this
contract and transport actions; they never persist their own Persona records.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

SCHEMA_VERSION = "sonaloop.persona-surface.v1"
COMPONENT_ID = "sonaloop.research.persona-view"
RESOURCE_URI = "ui://sonaloop/persona/v1"
RESOURCE_MIME = "text/html;profile=mcp-app"
EDITABLE_FIELDS = (
    "display_name", "age", "location", "role_title", "goals", "pain_points",
    "portrait_description",
)
MAX_AVATAR_BYTES = 8 * 1024 * 1024
MAX_AVATAR_DIMENSION = 2048
MAX_AVATAR_PROMPT = 500


class PersonaFields(TypedDict):
    display_name: str
    age: int | float | str | None
    location: str | None
    role_title: str | None
    goals: list[str]
    pain_points: list[str]
    portrait_description: str | None


class PersonaAvatar(TypedDict):
    state: Literal["missing", "ready", "stale", "unavailable"]
    sha256: str | None
    generated_at: str | None
    profile_version: str | None


class PersonaCapabilities(TypedDict):
    edit: list[str]
    generate_avatar: bool
    reasons: list[str]


class PersonaSurface(TypedDict):
    schema_version: str
    persona_id: str
    slug: str
    version: str
    fields: PersonaFields
    avatar: PersonaAvatar
    capabilities: PersonaCapabilities
    warnings: list[str]


class PersonaSurfaceError(ValueError):
    """A bounded public failure, safe to pass to a UI or text-only client."""

    def __init__(self, code: str, message: str, *, operation_id: str | None = None,
                 current: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.operation_id = operation_id
        self.current = current

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.operation_id is not None:
            result["operation_id"] = self.operation_id
        if self.current is not None:
            result["current"] = self.current
        return result

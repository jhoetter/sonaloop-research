"""Pure, bounded projection and edit mapping for the native Persona surface."""
from __future__ import annotations

import math

from .._persona_native import persona_version, persona_profile_version
from ..persona_surface_contract import EDITABLE_FIELDS, MAX_AVATAR_PROMPT, SCHEMA_VERSION, PersonaSurfaceError


def _field_value(persona, name):
    paths = {"age": ("demographics", "age"), "location": ("demographics", "location"),
             "role_title": ("role", "title"), "portrait_description": ("identity_traits", "avatar_profile")}
    if name not in paths:
        return persona.get(name)
    parent, key = paths[name]
    value = persona.get(parent)
    return value.get(key) if isinstance(value, dict) else None


def supported_field(name, value):
    if name in {"goals", "pain_points"}:
        return isinstance(value, list) and len(value) <= 8 and all(isinstance(v, str) and len(v) <= 180 for v in value)
    if name == "age":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return math.isfinite(value)
            except OverflowError:
                return False
        return value is None or isinstance(value, str) and len(value) <= 120
    maximum = MAX_AVATAR_PROMPT if name == "portrait_description" else 120 if name == "display_name" else 200
    return (value is None and name != "display_name") or isinstance(value, str) and len(value) <= maximum


def surface_projection(persona, *, can_edit=True, can_generate=False, reasons=(), store=None):
    from ..avatar import get_persona_avatar_content, validate_avatar_png
    import hashlib
    fields, editable, warnings = {}, [], []
    for name in EDITABLE_FIELDS:
        value = _field_value(persona, name)
        if supported_field(name, value):
            fields[name] = value
            if can_edit:
                editable.append(name)
        else:
            fields[name] = [] if name in {"goals", "pain_points"} else "" if name == "display_name" else None
            warnings.append(f"{name}: this native value has an unsupported shape; its stored value is unchanged.")
    avatar = {"state": "missing", "sha256": None, "generated_at": None, "profile_version": None}
    native = persona.get("avatar")
    if isinstance(native, dict) and native.get("path"):
        avatar["state"] = "unavailable"
        try:
            png, _ = get_persona_avatar_content(persona["id"], store=store)
            validate_avatar_png(png)
            basis = native.get("profile_version")
            avatar = {"state": "stale" if basis and basis != persona_profile_version(persona) else "ready",
                      "sha256": hashlib.sha256(png).hexdigest(),
                      "generated_at": native.get("generated_at") if isinstance(native.get("generated_at"), str) else None,
                      "profile_version": basis if isinstance(basis, str) else None}
            if not basis:
                warnings.append("The existing avatar has no recorded profile version.")
        except (FileNotFoundError, ValueError, KeyError, OSError):
            warnings.append("The native avatar is unavailable; its stored reference is unchanged.")
    return {"schema_version": SCHEMA_VERSION, "persona_id": persona["id"], "slug": persona["slug"],
            "version": persona_version(persona), "fields": fields, "avatar": avatar,
            "capabilities": {"edit": editable, "generate_avatar": bool(can_generate), "reasons": list(reasons)},
            "warnings": warnings}


def surface_patch(persona, changes):
    if not isinstance(changes, dict) or not changes or set(changes) - set(EDITABLE_FIELDS):
        raise PersonaSurfaceError("validation", "Provide only supported Persona fields.")
    patch = {}
    paths = {"age": ("demographics", "age"), "location": ("demographics", "location"),
             "role_title": ("role", "title"), "portrait_description": ("identity_traits", "avatar_profile")}
    for name, value in changes.items():
        if not supported_field(name, _field_value(persona, name)):
            raise PersonaSurfaceError("validation", "This native field cannot be edited by this surface.")
        if not supported_field(name, value):
            raise PersonaSurfaceError("validation", "A Persona field has an invalid value or exceeds its limit.")
        if name == "display_name" and not value.strip():
            raise PersonaSurfaceError("validation", "The display name must not be empty.")
        if name in {"goals", "pain_points"} and (not value or any(not s.strip() for s in value)):
            raise PersonaSurfaceError("validation", "Goals and pain points require non-empty entries.")
        if name in paths:
            parent, key = paths[name]
            if not isinstance(persona.get(parent), dict):
                raise PersonaSurfaceError("validation", "This native profile section has an unsupported shape.")
            patch.setdefault(parent, {})[key] = value
        else:
            patch[name] = value.strip() if name == "display_name" else value
    return patch

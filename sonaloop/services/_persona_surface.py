"""One native Persona service for the product and its MCP App."""
from __future__ import annotations

import copy
from contextlib import contextmanager

from .. import config
from .._persona_native import active_persona_workspace, persona_version, persona_digest, persona_lock
from ..persona_surface_contract import PersonaSurfaceError, MAX_AVATAR_PROMPT
from ..storage import Store
from ._persona_surface_operations import (execute_persona_operation, operation_key,
                                          operation_owner, effective_operation_status)
from ._persona_surface_view import surface_projection, surface_patch


@contextmanager
def _surface_store(store):
    owned = store is None
    store = store or Store()
    try:
        active_persona_workspace(store)
        yield store
    except PermissionError as exc:
        raise PersonaSurfaceError("forbidden", "This Persona is not available in the active workspace.") from exc
    finally:
        if owned:
            store.close()


def _authorize(operation, persona_id=None):
    from ._substrate import check_access
    try:
        # Existing cloud guard recognizes web.* as editor/entitlement-gated writes.
        check_access(operation, {"persona_id": persona_id} if persona_id else {})
    except PermissionError as exc:
        raise PersonaSurfaceError("forbidden", "This Persona operation is not permitted.") from exc


def _persona(store, persona_id):
    if not isinstance(persona_id, str) or not 0 < len(persona_id) <= 200:
        raise PersonaSurfaceError("validation", "A valid Persona ID is required.")
    row = store.get_persona_for_active_workspace(persona_id)
    if row is None:
        raise PersonaSurfaceError("not_found", "The Persona does not exist in this workspace.")
    return row


def _project(store, persona_id):
    if not persona_id:
        return None
    _authorize("get_persona_surface", persona_id)
    row = store.get_persona_for_active_workspace(persona_id)
    if row is None:
        return None
    from ..avatar import avatars_enabled
    edit, generate, reasons = True, avatars_enabled(), []
    try:
        _authorize("web.update_persona", row["id"])
    except PersonaSurfaceError:
        edit = False
        reasons.append("Persona editing requires permission in the active workspace.")
    try:
        _authorize("web.generate_avatar", row["id"])
    except PersonaSurfaceError:
        generate = False
        reasons.append("Avatar generation requires permission in the active workspace.")
    if not avatars_enabled():
        reasons.append("The optional image provider is not configured.")
    if any(op["kind"] == "generate_avatar" for op in store.unresolved_persona_operations(row["id"])):
        generate = False
        reasons.append("Inspect the pending or unconfirmed image operation before generating another image.")
    return surface_projection(row, can_edit=edit, can_generate=generate, reasons=reasons, store=store)


def _expected(persona, expected_version):
    if not isinstance(expected_version, str) or expected_version != persona_version(persona):
        raise PersonaSurfaceError("conflict", "The Persona changed. Refresh before applying this change.")


def get_persona_surface(persona_id, *, store=None):
    _authorize("get_persona_surface", persona_id)
    with _surface_store(store) as store:
        row = _persona(store, persona_id)
        return _project(store, row["id"])


def update_persona_surface(persona_id, changes, expected_version, operation_id, *, store=None):
    _authorize("web.update_persona", persona_id)
    with _surface_store(store) as store:
        canonical_id = _persona(store, persona_id)["id"]
        def execute(mark):
            from ._persona_updates import preview_persona_update, update_persona
            with persona_lock(store, canonical_id):
                row = _persona(store, canonical_id)
                _expected(row, expected_version)
                patch = surface_patch(row, changes)
                preview = preview_persona_update(row["id"], patch, row["updated_at"], store=store)
                mark("native_write_started")
                update_persona(row["id"], patch, "shared Persona surface edit", row["updated_at"],
                               preview.get("confirmation_token"), store=store)
                return row["id"]
        return execute_persona_operation("update", {"persona_id": persona_id, "changes": changes,
            "expected_version": expected_version}, canonical_id, operation_id, store, execute,
            lambda pid: _project(store, pid))


def record_persona_surface(description, profile, operation_id, segment_hint=None, *, store=None):
    _authorize("web.record_persona")
    operation_key(operation_id)
    if not isinstance(description, str) or not 0 < len(description.strip()) <= 8000:
        raise PersonaSurfaceError("validation", "A bounded Persona source description is required.")
    if segment_hint is not None and (not isinstance(segment_hint, str) or len(segment_hint) > 300):
        raise PersonaSurfaceError("validation", "The segment hint exceeds its limit.")
    if not isinstance(profile, dict) or len(str(profile)) > 64000:
        raise PersonaSurfaceError("validation", "A bounded authored Persona profile is required.")
    with _surface_store(store) as store:
        pid = "persona_" + persona_digest([operation_owner(), operation_id])[:16]
        def execute(mark):
            from ._personas import _profile_to_persona_dict, write_soul
            from ..llm_simulation import validate_profile_payload
            from ._hooks import emit_lifecycle_event
            from ._capabilities import merge_capabilities
            validated = validate_profile_payload(copy.deepcopy(profile))
            row = _profile_to_persona_dict(description.strip(), validated, segment_hint, None,
                                           config.utc_now_iso(), persona_id=pid)
            if profile.get("capabilities") is not None:
                row["capabilities"] = merge_capabilities(None, profile["capabilities"])
            # An operation-derived suffix permits two people with the same display name.
            row["slug"] = row["slug"][:100] + "-" + pid.removeprefix("persona_")
            row["soul"] = write_soul(row, store)
            mark("native_write_started")
            if not store.insert_persona_if_absent(row, "record_persona_surface"):
                raise PersonaSurfaceError("conflict", "This Persona creation identity already exists.")
            emit_lifecycle_event("persona.created", {"persona_id": pid, "slug": row["slug"],
                                                      "display_name": row["display_name"]}, store)
            return pid
        return execute_persona_operation("record", {"description": description, "profile": profile,
            "segment_hint": segment_hint}, pid, operation_id, store, execute, lambda pid: _project(store, pid))


def generate_persona_surface_avatar(persona_id, prompt, expected_version, operation_id, *, store=None):
    _authorize("web.generate_avatar", persona_id)
    if not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= MAX_AVATAR_PROMPT:
        raise PersonaSurfaceError("validation", "The portrait prompt must contain 1–500 characters.")
    with _surface_store(store) as store:
        canonical_id = _persona(store, persona_id)["id"]
        def execute(mark):
            from ..avatar import avatars_enabled, generate_persona_avatar
            with persona_lock(store, canonical_id):
                row = _persona(store, canonical_id)
                _expected(row, expected_version)
                if not avatars_enabled():
                    raise PersonaSurfaceError("provider_unavailable", "The optional image provider is not configured.")
                for other in store.unresolved_persona_operations(row["id"]):
                    if other["operation_id"] == operation_id or other["kind"] != "generate_avatar":
                        continue
                    if effective_operation_status(other) == "outcome_unknown":
                        raise PersonaSurfaceError("outcome_unknown", "Inspect the previous image operation before generating another image.")
                    if other.get("avatar_reserved"):
                        raise PersonaSurfaceError("in_progress", "Another image operation is already running.")
                mark("avatar_reserved")
            generate_persona_avatar(row["id"], store=store, prompt=prompt.strip(), expected_version=expected_version,
                                    before_provider=lambda: mark("provider_started"),
                                    before_persist=lambda: mark("native_write_started"))
            return row["id"]
        return execute_persona_operation("generate_avatar", {"persona_id": persona_id, "prompt": prompt,
            "expected_version": expected_version}, canonical_id, operation_id, store, execute,
            lambda pid: _project(store, pid))


def get_persona_surface_operation(operation_id, *, store=None):
    _authorize("get_persona_surface_operation")
    operation_key(operation_id)
    with _surface_store(store) as store:
        operation = store.get_persona_operation(operation_id)
        if not operation or operation["owner"] != operation_owner():
            raise PersonaSurfaceError("not_found", "The Persona operation is not available.")
        current = _project(store, operation.get("persona_id"))
        result = {"operation_id": operation_id, "status": effective_operation_status(operation)}
        if current is not None:
            result["result"] = current
        if operation.get("error"):
            result["error"] = operation["error"]
        return result

"""Native Persona operation ownership, retries and uncertain-outcome handling."""
from __future__ import annotations

import os
import re
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError

from .. import config
from .._persona_native import active_persona_workspace, persona_digest, persona_lock
from ..persona_surface_contract import PersonaSurfaceError
from ..storage._personas import PersonaWriteConflict

_RUNNING = set()
_RUNNING_GUARD = Lock()


def operation_owner():
    actor = config.current_request_actor() or {"kind": "local", "id": "local-process-owner"}
    return persona_digest({"kind": actor["kind"], "id": actor["id"]})


def operation_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", value):
        raise PersonaSurfaceError("validation", "Use a non-empty operation ID of at most 200 safe characters.")
    return value


def _process_start(pid):
    try:
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def operation_running(operation):
    if operation["status"] != "in_progress":
        return False
    if operation.get("worker_pid") == os.getpid():
        with _RUNNING_GUARD:
            return operation.get("worker_key") in _RUNNING
    pid = operation.get("worker_pid")
    if type(pid) is not int or pid <= 0:
        return False
    marker = _process_start(pid)
    if marker is not None:
        return marker == operation.get("worker_start")
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def effective_operation_status(operation):
    if operation["status"] == "in_progress" and not operation_running(operation):
        return "outcome_unknown"
    return operation["status"]


def _safe_failure(error, stage):
    if isinstance(error, PersonaSurfaceError):
        return error.code, str(error)
    if isinstance(error, PersonaWriteConflict):
        return "conflict", "The Persona changed. Refresh before applying this change."
    if isinstance(error, HTTPError):
        if 400 <= error.code < 500 and error.code != 408:
            return "provider_error", "The image provider rejected this operation."
        return "outcome_unknown", "The image provider outcome is unknown. Inspect this operation before continuing."
    if isinstance(error, (TimeoutError, URLError, ConnectionError)) or stage.get("native_write_started"):
        return "outcome_unknown", "The operation outcome is unknown. Inspect its status before continuing."
    if stage.get("provider_started"):
        return "provider_error", "The image provider did not return a publishable image."
    if isinstance(error, PermissionError):
        return "forbidden", "This Persona operation is not permitted."
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "validation", "The Persona request does not satisfy its native contract."
    return "outcome_unknown", "The operation could not be confirmed. Inspect its status before continuing."


def execute_persona_operation(kind, payload, persona_id, operation_id, store, execute, project):
    op_id = operation_key(operation_id)
    owner = operation_owner()
    try:
        fingerprint = persona_digest({"kind": kind, "payload": payload})
    except (ValueError, TypeError, OverflowError) as exc:
        raise PersonaSurfaceError("validation", "The Persona request must contain finite JSON values.") from exc
    worker_key = persona_digest([str(store.path), active_persona_workspace(store), op_id])
    with persona_lock(store, "operation:" + op_id):
        old = store.get_persona_operation(op_id)
        if old:
            if old["owner"] != owner:
                raise PersonaSurfaceError("forbidden", "This operation belongs to another actor.")
            if old["fingerprint"] != fingerprint:
                raise PersonaSurfaceError("operation_mismatch", "The operation ID already belongs to a different request.", operation_id=op_id)
            current = project(old.get("persona_id"))
            status = effective_operation_status(old)
            if status == "succeeded":
                if current is None:
                    raise PersonaSurfaceError("not_found", "The Persona no longer exists.", operation_id=op_id)
                return current
            error = old.get("error") or {}
            code = status if status in {"in_progress", "outcome_unknown"} else error.get("code", status)
            message = error.get("message") or "This operation is running or has an unconfirmed outcome; inspect its status."
            raise PersonaSurfaceError(code, message, operation_id=op_id, current=current)
        now = config.utc_now_iso()
        operation = {"operation_id": op_id, "persona_id": persona_id, "kind": kind,
                     "owner": owner, "fingerprint": fingerprint, "status": "in_progress",
                     "created_at": now, "updated_at": now, "worker_pid": os.getpid(),
                     "worker_start": _process_start(os.getpid()), "worker_key": worker_key}
        with _RUNNING_GUARD:
            _RUNNING.add(worker_key)
        try:
            store.put_persona_operation(operation)
        except BaseException:
            with _RUNNING_GUARD:
                _RUNNING.discard(worker_key)
            raise
    stage = {}

    def mark(name):
        stage[name] = True
        operation[name] = True
        operation["updated_at"] = config.utc_now_iso()
        store.put_persona_operation(operation)

    try:
        operation["persona_id"] = execute(mark)
        operation["status"] = "succeeded"
        operation["updated_at"] = config.utc_now_iso()
        store.put_persona_operation(operation)
        return project(operation["persona_id"])
    except BaseException as error:
        code, message = _safe_failure(error, stage)
        operation["status"] = code if code in {"conflict", "outcome_unknown"} else "failed"
        operation["error"] = {"code": code, "message": message}
        operation["updated_at"] = config.utc_now_iso()
        store.put_persona_operation(operation)
        current = project(operation.get("persona_id"))
        if not isinstance(error, Exception):
            raise
        raise PersonaSurfaceError(code, message, operation_id=op_id, current=current) from error
    finally:
        with _RUNNING_GUARD:
            _RUNNING.discard(worker_key)

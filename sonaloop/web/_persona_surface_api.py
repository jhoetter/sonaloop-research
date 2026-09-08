"""Thin JSON transport for the same native Persona commands used by MCP."""
from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..persona_surface_contract import PersonaSurfaceError
from ..services._persona_surface import (get_persona_surface, update_persona_surface,
    generate_persona_surface_avatar, get_persona_surface_operation)
from ._forms import csrf_ok


def _response(value=None, error=None):
    statuses = {"validation": 422, "not_found": 404, "forbidden": 403, "conflict": 409,
                "operation_mismatch": 409, "in_progress": 409, "outcome_unknown": 409,
                "provider_unavailable": 503, "provider_error": 502}
    return JSONResponse({"error": error.as_dict()} if error else {"structuredContent": value},
                        status_code=statuses.get(error.code, 500) if error else 200,
                        headers={"Cache-Control": "private, no-store"})


def register_persona_surface_api(app):
    @app.get("/api/personas/{persona_id}/surface")
    def persona_surface(persona_id: str):
        try:
            return _response(get_persona_surface(persona_id))
        except PersonaSurfaceError as error:
            return _response(error=error)

    @app.get("/api/personas/surface-operations/{operation_id}")
    def persona_surface_operation(operation_id: str):
        try:
            return _response(get_persona_surface_operation(operation_id))
        except PersonaSurfaceError as error:
            return _response(error=error)

    @app.post("/api/personas/{persona_id}/surface/actions")
    async def persona_surface_action(persona_id: str, request: Request):
        try:
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                raise PersonaSurfaceError("validation", "Send the Persona action as JSON.")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    raise PersonaSurfaceError("validation", "The Persona action exceeds its size limit.")
            try:
                def invalid_constant(value):
                    raise ValueError("non-finite JSON number")
                payload = json.loads(body, parse_constant=invalid_constant)
            except (ValueError, UnicodeError) as exc:
                raise PersonaSurfaceError("validation", "The Persona action contains invalid JSON.") from exc
            if not isinstance(payload, dict):
                raise PersonaSurfaceError("validation", "The Persona action must be an object.")
            if not csrf_ok(payload):
                raise PersonaSurfaceError("forbidden", "The request is missing a valid CSRF token.")
            action = payload.get("action")
            field = {"update": "changes", "generate_avatar": "prompt"}.get(action) if isinstance(action, str) else None
            required = {"action", "operation_id", "expected_version", "csrf_token", field}
            if field is None or set(payload) != required:
                raise PersonaSurfaceError("validation", "The Persona action contains missing or unsupported fields.")
            function = update_persona_surface if action == "update" else generate_persona_surface_avatar
            result = await run_in_threadpool(function, persona_id, payload[field],
                                            payload["expected_version"], payload["operation_id"])
            return _response(result)
        except PersonaSurfaceError as error:
            return _response(error=error)

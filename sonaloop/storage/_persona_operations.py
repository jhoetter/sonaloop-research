"""Durable Persona commands in the same native workspace database as Personas."""
from __future__ import annotations

import json

from .._persona_native import active_persona_workspace


class PersonaOperationsMixin:
    def _persona_operation_scope(self):
        workspace = active_persona_workspace(self)
        return (" AND workspace_id=?", [workspace]) if workspace else ("", [])

    def get_persona_operation(self, operation_id):
        suffix, scope = self._persona_operation_scope()
        row = self.conn.execute("SELECT data FROM persona_operations WHERE operation_id=?" + suffix,
                                [operation_id, *scope]).fetchone()
        return json.loads(row["data"]) if row else None

    def put_persona_operation(self, operation):
        self.conn.execute(
            "INSERT INTO persona_operations (operation_id,persona_id,status,data,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(operation_id) DO UPDATE SET "
            "persona_id=excluded.persona_id,status=excluded.status,data=excluded.data,updated_at=excluded.updated_at",
            (operation["operation_id"], operation.get("persona_id"), operation["status"],
             json.dumps(operation, ensure_ascii=False, allow_nan=False), operation["created_at"],
             operation["updated_at"]))
        self.conn.commit()

    def unresolved_persona_operations(self, persona_id):
        suffix, scope = self._persona_operation_scope()
        rows = self.conn.execute(
            "SELECT data FROM persona_operations WHERE persona_id=? AND status IN ('in_progress','outcome_unknown')"
            + suffix, [persona_id, *scope]).fetchall()
        return [json.loads(row["data"]) for row in rows]

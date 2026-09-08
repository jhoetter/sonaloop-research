from __future__ import annotations

import json
import hashlib
import os
import tempfile
from typing import Any

from .._persona_native import NativePersona, active_persona_workspace, persona_lock


class PersonaWriteConflict(ValueError):
    """The native Persona changed since this record was read."""


def _prepare_soul(persona, store):
    if not isinstance(persona.get("soul"), dict):
        return None
    from ..services._personas import soul_path, render_soul
    path = soul_path(persona)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_soul(persona, store)
    persona["soul"]["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    fd, temporary = tempfile.mkstemp(prefix=".soul-", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary, path


class PersonasMixin:
    def upsert_persona(self, persona: dict[str, Any], reason: str = "upsert") -> None:
        with persona_lock(self, persona["id"]):
            self._persist_persona(persona, reason)

    def insert_persona_if_absent(self, persona: dict[str, Any], reason="create") -> bool:
        with persona_lock(self, persona["id"]):
            if self.get_persona_for_active_workspace(persona["id"]):
                return False
            self._persist_persona(persona, reason, insert_only=True)
            return True

    def _persist_persona(self, persona, reason, *, insert_only=False):
        workspace = active_persona_workspace(self)
        suffix, scope = (" AND workspace_id=?", [workspace]) if workspace else ("", [])
        row = self.conn.execute("SELECT data FROM personas WHERE id=?" + suffix,
                                [persona["id"], *scope]).fetchone()
        expected = getattr(persona, "native_snapshot", None)
        if isinstance(persona, NativePersona) and persona.native_workspace != workspace:
            raise PermissionError("Persona belongs to a different active workspace")
        if expected is not None and (not row or row["data"] != expected):
            raise PersonaWriteConflict("persona changed since it was read; refresh before writing")
        prepared = None
        try:
            # Stage first, publish only after the winning row commits. A stale writer
            # never touches the canonical SOUL, including existing native callers.
            prepared = _prepare_soul(persona, self)
            serialized = json.dumps(persona, ensure_ascii=False, allow_nan=False)
            if row and not insert_only:
                cursor = self.conn.execute(
                    "UPDATE personas SET slug=?, data=?, updated_at=? WHERE id=? AND data=?" + suffix,
                    [persona["slug"], serialized, persona["updated_at"], persona["id"], row["data"], *scope])
                if cursor.rowcount != 1:
                    raise PersonaWriteConflict("persona changed since it was read; refresh before writing")
            else:
                self.conn.execute(
                    "INSERT INTO personas (id,slug,data,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (persona["id"], persona["slug"], serialized, persona["created_at"], persona["updated_at"]))
            self.audit("persona", persona["id"], "upsert", reason, persona)
            self.conn.commit()
            if prepared:
                os.replace(prepared[0], prepared[1])
            if isinstance(persona, NativePersona):
                persona.native_snapshot = serialized
        except BaseException:
            self.conn.rollback()
            raise
        finally:
            if prepared and os.path.exists(prepared[0]):
                os.unlink(prepared[0])

    def _persona_row(self, row):
        if not row:
            return None
        workspace = row["workspace_id"] if "workspace_id" in row.keys() else None
        return NativePersona(json.loads(row["data"]), row["data"], workspace)

    def get_persona_for_active_workspace(self, persona_id_or_slug):
        workspace = active_persona_workspace(self)
        sql = "SELECT * FROM personas WHERE (id=? OR slug=?)"
        params = [persona_id_or_slug, persona_id_or_slug]
        if workspace:
            sql += " AND workspace_id=?"
            params.append(workspace)
        return self._persona_row(self.conn.execute(sql, params).fetchone())

    def get_persona(self, persona_id_or_slug: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM personas WHERE id=? OR slug=?",
            (persona_id_or_slug, persona_id_or_slug),
        ).fetchone()
        return self._persona_row(row)

    def list_personas(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM personas ORDER BY created_at").fetchall()
        return [self._persona_row(row) for row in rows]

    # ---- Persona revisions -------------------------------------------
    def insert_persona_revision(self, revision: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO persona_revisions (id, persona_id, effective_on, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (revision["id"], revision["persona_id"], revision["effective_on"],
             json.dumps(revision, ensure_ascii=False), revision["created_at"]))

    def list_persona_revisions(self, persona_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM persona_revisions WHERE persona_id=? ORDER BY effective_on", (persona_id,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

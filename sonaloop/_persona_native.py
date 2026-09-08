"""Native Persona serialization and version helpers, shared by all transports."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from threading import local

from . import config
from ._project_locks import project_lifecycle_locks

_HELD_PERSONA_LOCKS = local()


def persona_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def persona_version(persona: dict) -> str:
    return "pv_" + persona_digest(persona)


def persona_profile_version(persona: dict) -> str:
    # Runtime files, image publication and operation history do not change the profile.
    return "pp_" + persona_digest({k: v for k, v in persona.items()
                                   if k not in {"avatar", "soul", "updated_at"}})


def active_persona_workspace(store) -> str | None:
    if not (getattr(store.backend, "dialect", "") == "postgres"
            and getattr(store.backend, "tenant", False)):
        return None
    accessible, active = config.request_tenant_scope() or ((), "")
    if not active or active not in accessible:
        raise PermissionError("Persona access requires an active authorized workspace")
    return active


@contextmanager
def persona_lock(store, identity: str):
    # Reuse the native SQLite OS-lock / PostgreSQL advisory-lock implementation.
    # The namespace keeps Persona and project locks independent.
    key = (str(getattr(store, "path", "postgres")), active_persona_workspace(store), identity)
    held = getattr(_HELD_PERSONA_LOCKS, "keys", set())
    if key in held:
        yield
        return
    with project_lifecycle_locks(store, ["persona:" + identity]):
        _HELD_PERSONA_LOCKS.keys = held | {key}
        try:
            yield
        finally:
            _HELD_PERSONA_LOCKS.keys = held


class NativePersona(dict):
    """A native record carrying its read version outside the persisted JSON.

    deepcopy preserves the snapshot. Serializing a record never emits this marker.
    It closes stale full-record writes in existing simulation/avatar/update paths.
    """
    def __init__(self, value, serialized: str, workspace: str | None = None):
        super().__init__(value)
        self.native_snapshot = serialized
        self.native_workspace = workspace

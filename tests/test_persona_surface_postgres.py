"""Real RLS proof for native Persona/operation authority; isolated PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_storage_tenancy_postgres import pg, _app_role, _scoped, pytestmark  # noqa: F401
from sonaloop import config, services
from sonaloop.storage import Store
from sonaloop.storage._personas import PersonaWriteConflict
from sonaloop.persona_surface_contract import PersonaSurfaceError
from conftest import create_persona, make_profile


def test_surface_operation_and_id_are_scoped_to_active_workspace(pg):
    def create(name):
        with Store() as store:
            return services.record_persona_surface("A source", make_profile(name), "same-operation", store=store)
    a = _scoped(["ws_alpha"], "ws_alpha", lambda: create("Alpha"))
    b = _scoped(["ws_beta"], "ws_beta", lambda: create("Beta"))
    assert a["persona_id"] == b["persona_id"]
    def read_active():
        with Store() as store:
            dto = services.get_persona_surface(a["persona_id"], store=store)
            result = services.get_persona_surface_operation("same-operation", store=store)
            assert result["result"] == dto
            return dto
    assert _scoped(["ws_alpha", "ws_beta"], "ws_alpha", read_active)["fields"]["display_name"] == "Alpha"
    assert _scoped(["ws_alpha", "ws_beta"], "ws_beta", read_active)["fields"]["display_name"] == "Beta"


def test_surface_unbound_or_inaccessible_scope_is_denied(pg):
    a = _scoped(["ws_alpha"], "ws_alpha", lambda: create_persona(Store(), "Only Alpha"))
    def denied():
        with Store() as store:
            with pytest.raises(PersonaSurfaceError) as error:
                services.get_persona_surface(a, store=store)
            assert error.value.code in {"forbidden", "not_found"}
    _scoped(["ws_beta"], "ws_beta", denied)
    _scoped([], "", denied)


def test_legacy_stale_native_write_is_rejected_by_postgres(pg):
    def run():
        with Store() as first, Store() as second:
            pid = create_persona(first, "Original PG")
            old = first.get_persona(pid)
            newer = second.get_persona(pid)
            newer["display_name"] = "Winner PG"
            second.upsert_persona(newer)
            old["display_name"] = "Stale PG"
            with pytest.raises(PersonaWriteConflict):
                first.upsert_persona(old)
            assert first.get_persona(pid)["display_name"] == "Winner PG"
            assert "Winner PG" in services.soul_path(first.get_persona(pid)).read_text()
    _scoped(["ws_alpha"], "ws_alpha", run)


def test_simultaneous_same_operation_has_one_native_effect(pg):
    # Bootstrap the schema once, just as the established PG concurrency tests
    # do; schema migration itself is not this operation-admission race.
    _scoped(["ws_alpha"], "ws_alpha", lambda: Store().close())
    start = Barrier(2)
    def write():
        def scoped():
            with Store() as store:
                start.wait(timeout=8)
                try:
                    return services.record_persona_surface("One concurrent source", make_profile("Once"), "race-op", store=store)
                except PersonaSurfaceError as error:
                    assert error.code == "in_progress"
                    return None
        return _scoped(["ws_alpha"], "ws_alpha", scoped)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    def verify():
        with Store() as store:
            assert len(store.list_personas()) == 1
            status = services.get_persona_surface_operation("race-op", store=store)
            assert status["status"] == "succeeded"
            assert all(r is None or r["persona_id"] == status["result"]["persona_id"] for r in results)
    _scoped(["ws_alpha"], "ws_alpha", verify)

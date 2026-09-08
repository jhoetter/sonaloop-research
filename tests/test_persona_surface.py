"""Native Persona surface contracts: one store, safe retries, real PNGs, no network."""
from __future__ import annotations

import base64
import copy
import json
from io import BytesIO
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest
from PIL import Image

from sonaloop import avatar, config, services
from sonaloop.persona_surface_contract import PersonaSurfaceError
from sonaloop.services import _substrate
from sonaloop.storage import Store
from conftest import create_persona, make_profile


def png(color="navy", size=(32, 32)):
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def clean_guards(monkeypatch):
    _substrate.clear_access_guards()
    monkeypatch.setattr(avatar, "load_env", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    _substrate.clear_access_guards()


@pytest.fixture
def provider(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key-never-returned")
    def run(url, payload, key):
        calls.append(copy.deepcopy(payload))
        return {"data": [{"b64_json": base64.b64encode(png()).decode()}],
                "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                "_request_id": "req_test_persona"}
    monkeypatch.setattr(avatar, "_post_json", run)
    return calls


def test_pure_surface_get_never_repairs_missing_soul(store):
    pid = create_persona(store, "Pure Read")
    path = services.soul_path(store.get_persona(pid))
    path.unlink()
    before = store.conn.total_changes
    value = services.get_persona_surface(pid, store=store)
    assert not path.exists()
    assert store.conn.total_changes == before
    assert value["fields"]["display_name"] == "Pure Read"
    encoded = json.dumps(value)
    assert all(key not in encoded for key in ["source_description", "soul", "data/", "approval_token"])


def test_update_uses_native_identity_and_replay_reads_current_record(store):
    pid = create_persona(store, "Initial")
    before = services.get_persona_surface(pid, store=store)
    first = services.update_persona_surface(pid, {"display_name": "Renamed"}, before["version"], "rename-1", store=store)
    assert first["persona_id"] == pid and first["slug"] == before["slug"]
    assert first["version"] != before["version"]
    latest = services.update_persona_surface(pid, {"role_title": "Nurse"}, first["version"], "role-2", store=store)
    replay = services.update_persona_surface(pid, {"display_name": "Renamed"}, before["version"], "rename-1", store=store)
    assert replay == latest
    inspected = services.get_persona_surface_operation("rename-1", store=store)
    assert inspected == {"operation_id": "rename-1", "status": "succeeded", "result": latest}
    text = services.soul_path(store.get_persona(pid)).read_text()
    assert "Renamed" in text and "Nurse" in text
    assert store.get_persona(pid)["display_name"] == "Renamed"


def test_operation_reuse_and_current_version_conflicts(store):
    pid = create_persona(store, "Bound")
    value = services.get_persona_surface(pid, store=store)
    services.update_persona_surface(pid, {"goals": ["First"]}, value["version"], "bound-1", store=store)
    with pytest.raises(PersonaSurfaceError) as error:
        services.update_persona_surface(pid, {"goals": ["Different"]}, value["version"], "bound-1", store=store)
    assert error.value.code == "operation_mismatch"
    with pytest.raises(PersonaSurfaceError) as error:
        services.update_persona_surface(pid, {"goals": ["Old"]}, value["version"], "bound-2", store=store)
    assert error.value.code == "conflict"
    assert error.value.current["fields"]["goals"] == ["First"]
    assert services.get_persona_surface_operation("bound-2", store=store)["status"] == "conflict"


@pytest.mark.parametrize("changes", [{"id": "other"}, {"avatar": {}}, {"display_name": " "},
    {"goals": []}, {"pain_points": [" "]}, {"age": True}, {"age": float("inf")}, {"age": 10 ** 400},
    {"portrait_description": "a" * 501}, {"role_title": "a" * 301}])
def test_bounded_patch_rejects_unknown_or_invalid_fields(store, changes):
    pid = create_persona(store, "Validation")
    value = services.get_persona_surface(pid, store=store)
    with pytest.raises((PersonaSurfaceError, ValueError)):
        services.update_persona_surface(pid, changes, value["version"], "invalid-1", store=store)
    assert services.get_persona_surface(pid, store=store)["fields"] == value["fields"]


@pytest.mark.parametrize("age", [42, 42.5, "mid forties", None])
def test_native_age_shapes_are_preserved(store, age):
    pid = create_persona(store, "Age")
    value = services.get_persona_surface(pid, store=store)
    result = services.update_persona_surface(pid, {"age": age, "location": "Bern"}, value["version"], "age-1", store=store)
    assert result["fields"]["age"] == age
    assert store.get_persona(pid)["demographics"] == {"age": age, "location": "Bern"}


def test_unsupported_imported_shape_is_disabled_not_rewritten(store):
    pid = create_persona(store, "Imported")
    row = store.get_persona(pid)
    row["identity_traits"]["avatar_profile"] = {"hair": "curly"}
    row["demographics"]["age"] = {"min": 35, "max": 45}
    store.upsert_persona(row)
    before = json.dumps(store.get_persona(pid), sort_keys=True)
    value = services.get_persona_surface(pid, store=store)
    assert "portrait_description" not in value["capabilities"]["edit"]
    assert "age" not in value["capabilities"]["edit"] and len(value["warnings"]) >= 2
    assert json.dumps(store.get_persona(pid), sort_keys=True) == before


def test_record_is_insert_only_and_same_named_people_have_distinct_native_ids(store):
    profile = make_profile("Same name")
    first = services.record_persona_surface("Same description", profile, "create-1", store=store)
    second = services.record_persona_surface("Same description", profile, "create-2", store=store)
    assert first["persona_id"] != second["persona_id"] and first["slug"] != second["slug"]
    assert services.record_persona_surface("Same description", profile, "create-1", store=store) == first
    assert len(store.list_personas()) == 2
    assert services.soul_path(store.get_persona(first["persona_id"])).is_file()


def test_owner_and_revoked_authority_are_rechecked_on_replay(store):
    pid = create_persona(store, "Owned")
    value = services.get_persona_surface(pid, store=store)
    token = config.set_request_actor({"kind": "user", "id": "alice", "label": "Alice"})
    try:
        services.update_persona_surface(pid, {"age": 45}, value["version"], "owned-1", store=store)
    finally:
        config.reset_request_actor(token)
    other = config.set_request_actor({"kind": "user", "id": "bob", "label": "Bob"})
    try:
        with pytest.raises(PersonaSurfaceError) as error:
            services.update_persona_surface(pid, {"age": 45}, value["version"], "owned-1", store=store)
        assert error.value.code == "forbidden"
        with pytest.raises(PersonaSurfaceError):
            services.get_persona_surface_operation("owned-1", store=store)
    finally:
        config.reset_request_actor(other)
    def deny(operation, resource):
        if operation.startswith("web."):
            raise PermissionError("viewer")
    _substrate.register_access_guard(deny)
    readonly = services.get_persona_surface(pid, store=store)
    assert readonly["capabilities"]["edit"] == []
    assert not readonly["capabilities"]["generate_avatar"]
    with pytest.raises(PersonaSurfaceError) as error:
        services.update_persona_surface(pid, {"age": 45}, value["version"], "owned-1", store=store)
    assert error.value.code == "forbidden"


def test_portrait_uses_native_avatar_without_rewriting_prompt_and_retry_is_free(store, provider):
    pid = create_persona(store, "Portrait")
    value = services.get_persona_surface(pid, store=store)
    result = services.generate_persona_surface_avatar(pid, "Curly hair in daylight", value["version"], "image-1", store=store)
    assert len(provider) == 1
    assert result["avatar"]["state"] == "ready"
    assert result["fields"] == value["fields"]
    assert services.generate_persona_surface_avatar(pid, "Curly hair in daylight", value["version"], "image-1", store=store) == result
    assert len(provider) == 1
    native = store.get_persona(pid)
    assert native["avatar"]["sha256"] == result["avatar"]["sha256"]
    assert native["identity_traits"]["avatar_profile"] == "unspecified"
    assert avatar.get_persona_avatar_content(pid, store)[0] == png()
    assert "private-test-key" not in json.dumps(result)
    changed = services.update_persona_surface(pid, {"display_name": "New name"}, result["version"], "after-image", store=store)
    assert changed["avatar"]["state"] == "stale"
    assert changed["avatar"]["sha256"] == result["avatar"]["sha256"]


def test_provider_failure_preserves_image_and_never_leaks_provider_body(store, provider, monkeypatch):
    pid = create_persona(store, "Failure")
    value = services.get_persona_surface(pid, store=store)
    ready = services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "good", store=store)
    def fail(*args):
        raise HTTPError("https://private-provider", 400, "SECRET provider body", {}, BytesIO(b"SECRET"))
    monkeypatch.setattr(avatar, "_post_json", fail)
    with pytest.raises(PersonaSurfaceError) as error:
        services.generate_persona_surface_avatar(pid, "Other portrait", ready["version"], "bad", store=store)
    assert error.value.code == "provider_error"
    assert error.value.current["avatar"] == ready["avatar"]
    assert "SECRET" not in json.dumps(services.get_persona_surface_operation("bad", store=store))
    assert services.get_persona_surface_operation("bad", store=store)["status"] == "failed"


def test_unknown_provider_is_durable_and_retry_never_repeats_call(store, provider, monkeypatch):
    pid = create_persona(store, "Unknown")
    value = services.get_persona_surface(pid, store=store)
    calls = []
    def timeout(*args):
        calls.append(1)
        raise TimeoutError("private provider detail")
    monkeypatch.setattr(avatar, "_post_json", timeout)
    for _ in range(2):
        with pytest.raises(PersonaSurfaceError) as error:
            services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "timeout-1", store=store)
        assert error.value.code == "outcome_unknown"
    assert len(calls) == 1
    with Store() as reopened:
        status = services.get_persona_surface_operation("timeout-1", store=reopened)
        assert status["status"] == "outcome_unknown"
        assert not status["result"]["capabilities"]["generate_avatar"]


def test_crashed_in_progress_inspection_is_pure_and_never_retries_provider(store, provider):
    pid = create_persona(store, "Crashed")
    from sonaloop.services._persona_surface_operations import operation_owner
    store.put_persona_operation({"operation_id": "crashed-1", "persona_id": pid,
        "status": "in_progress", "kind": "generate_avatar", "owner": operation_owner(),
        "created_at": config.utc_now_iso(), "updated_at": config.utc_now_iso(),
        "worker_pid": 0, "worker_key": "dead", "provider_started": True})
    before = store.conn.total_changes
    assert services.get_persona_surface_operation("crashed-1", store=store)["status"] == "outcome_unknown"
    assert store.conn.total_changes == before and provider == []


def test_pending_avatar_is_visible_without_duplicate_provider_execution(store, provider, monkeypatch):
    pid = create_persona(store, "Pending")
    value = services.get_persona_surface(pid, store=store)
    started, release = Event(), Event()
    def blocked(*args):
        started.set()
        assert release.wait(8)
        return {"data": [{"b64_json": base64.b64encode(png()).decode()}]}
    monkeypatch.setattr(avatar, "_post_json", blocked)
    def call():
        with Store() as separate:
            return services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "pending-1", store=separate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(call)
        try:
            assert started.wait(5)
            assert services.get_persona_surface_operation("pending-1", store=store)["status"] == "in_progress"
            with pytest.raises(PersonaSurfaceError) as error:
                call()
            assert error.value.code == "in_progress"
        finally:
            release.set()
        assert pending.result(timeout=8)["avatar"]["state"] == "ready"


def test_slug_and_id_share_one_avatar_reservation_and_preserve_retry_identity(store, provider, monkeypatch):
    pid = create_persona(store, "Alias Reservation")
    value = services.get_persona_surface(pid, store=store)
    started, release, calls = Event(), Event(), []
    def blocked(*args):
        calls.append(1)
        started.set()
        assert release.wait(8)
        return {"data": [{"b64_json": base64.b64encode(png()).decode()}]}
    monkeypatch.setattr(avatar, "_post_json", blocked)
    def call_slug():
        with Store() as separate:
            return services.generate_persona_surface_avatar(value["slug"], "Portrait", value["version"], "alias-slug", store=separate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(call_slug)
        try:
            assert started.wait(5)
            assert store.get_persona_operation("alias-slug")["persona_id"] == pid
            assert not services.get_persona_surface(pid, store=store)["capabilities"]["generate_avatar"]
            with pytest.raises(PersonaSurfaceError) as error:
                services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "alias-id", store=store)
            assert error.value.code == "in_progress"
            with pytest.raises(PersonaSurfaceError) as error:
                services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "alias-slug", store=store)
            assert error.value.code == "operation_mismatch"
        finally:
            release.set()
        ready = pending.result(timeout=8)
    assert calls == [1]
    assert services.generate_persona_surface_avatar(value["slug"], "Portrait", value["version"], "alias-slug", store=store) == ready
    assert calls == [1]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/private", "https://untrusted.invalid/image.png"])
def test_provider_image_urls_are_never_fetched(store, provider, monkeypatch, url):
    pid = create_persona(store, "No URL Fetch")
    value = services.get_persona_surface(pid, store=store)
    monkeypatch.setattr(avatar, "_post_json", lambda *args: {"data": [{"url": url}]})
    def forbidden_fetch(*args, **kwargs):
        pytest.fail("Provider-returned image URL must never be fetched")
    monkeypatch.setattr(avatar.urllib.request, "urlopen", forbidden_fetch)
    with pytest.raises(PersonaSurfaceError) as error:
        services.generate_persona_surface_avatar(pid, "Portrait", value["version"], "url-image", store=store)
    assert error.value.code == "provider_error"
    assert services.get_persona_surface_operation("url-image", store=store)["status"] == "failed"
    assert store.get_persona(pid)["avatar"] is None

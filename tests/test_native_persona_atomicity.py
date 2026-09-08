"""Existing native writers share the same record/SOUL concurrency boundary."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from sonaloop import avatar, services
from sonaloop.storage import Store
from sonaloop.storage._personas import PersonaWriteConflict
from conftest import create_persona, make_profile
from test_persona_surface import png


def test_stale_native_writer_cannot_replace_record_or_soul(store):
    pid = create_persona(store, "Original")
    stale = store.get_persona(pid)
    with Store() as other:
        preview = services.preview_persona_update(pid, {"display_name": "Winner"}, store=other)
        services.update_persona(pid, {"display_name": "Winner"}, "winner", preview["expected_updated_at"],
                                preview["confirmation_token"], store=other)
    path = services.soul_path(store.get_persona(pid))
    winning_soul = path.read_bytes()
    stale["display_name"] = "Loser"
    stale["soul"] = services.write_soul(stale, store)
    assert path.read_bytes() == winning_soul  # preparation never publishes stale text
    with pytest.raises(PersonaWriteConflict):
        store.upsert_persona(stale, reason="stale native writer")
    assert store.get_persona(pid)["display_name"] == "Winner"
    assert path.read_bytes() == winning_soul


def test_deepcopied_native_snapshot_remains_bound_to_its_read(store):
    pid = create_persona(store, "Copy")
    first = copy.deepcopy(store.get_persona(pid))
    second = store.get_persona(pid)
    second["role"]["title"] = "Current"
    store.upsert_persona(second)
    first["role"]["title"] = "Stale"
    with pytest.raises(PersonaWriteConflict):
        store.upsert_persona(first)


def test_native_create_retry_does_not_overwrite_new_profile(store):
    profile = make_profile("Existing")
    first = services.record_persona("Native intent", profile, store=store)
    assert services.record_persona("Native intent", profile, store=store)["id"] == first["id"]
    newer = dict(profile, goals=["Different authored content"])
    with pytest.raises(ValueError, match="creation intent"):
        services.record_persona("Native intent", newer, store=store)
    assert store.get_persona(first["id"])["goals"] == profile["goals"]


def test_legacy_avatar_cannot_revert_a_profile_edited_during_provider_call(store, monkeypatch):
    pid = create_persona(store, "Before Image")
    started, release = Event(), Event()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(avatar, "load_env", lambda: None)
    def provider(*args):
        started.set()
        assert release.wait(8)
        return {"data": [{"b64_json": base64.b64encode(png()).decode()}]}
    monkeypatch.setattr(avatar, "_post_json", provider)
    def generate():
        with Store() as other:
            return avatar.generate_persona_avatar(pid, store=other)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(generate)
        try:
            assert started.wait(5)
            preview = services.preview_persona_update(pid, {"display_name": "Edited During Image"}, store=store)
            services.update_persona(pid, {"display_name": "Edited During Image"}, "edit",
                preview["expected_updated_at"], preview["confirmation_token"], store=store)
        finally:
            release.set()
        with pytest.raises(PersonaWriteConflict):
            pending.result(timeout=8)
    current = store.get_persona(pid)
    assert current["display_name"] == "Edited During Image" and current["avatar"] is None
    assert "Edited During Image" in services.soul_path(current).read_text()


def test_legacy_regeneration_keeps_old_avatar_bytes_immutable(store, monkeypatch):
    pid = create_persona(store, "Immutable")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(avatar, "load_env", lambda: None)
    payloads = [png("navy"), png("green")]
    monkeypatch.setattr(avatar, "_post_json", lambda *a: {"data": [{"b64_json": base64.b64encode(payloads.pop(0)).decode()}]})
    first = avatar.generate_persona_avatar(pid, store=store)
    from sonaloop.services._snapshots import _avatar_disk_path
    original = _avatar_disk_path(first["path"])
    bytes_before = original.read_bytes()
    second = avatar.generate_persona_avatar(pid, store=store)
    assert first["path"] != second["path"]
    assert original.read_bytes() == bytes_before
    assert avatar.get_persona_avatar_content(pid, store)[0] == png("green")


def test_post_commit_soul_failure_is_uncertain_and_never_serves_stale_identity(store, monkeypatch):
    from sonaloop.storage import _personas
    from sonaloop.persona_surface_contract import PersonaSurfaceError
    pid = create_persona(store, "Before Publish")
    value = services.get_persona_surface(pid, store=store)
    original = _personas.os.replace
    def interrupted(*args):
        raise OSError("interrupted filesystem publication")
    monkeypatch.setattr(_personas.os, "replace", interrupted)
    with pytest.raises(PersonaSurfaceError) as error:
        services.update_persona_surface(pid, {"display_name": "Committed Winner"}, value["version"], "publish-1", store=store)
    assert error.value.code == "outcome_unknown"
    assert error.value.current["fields"]["display_name"] == "Committed Winner"
    monkeypatch.setattr(_personas.os, "replace", original)
    # Existing SOUL access is explicitly a repair/write path. The pure surface
    # only reported the authoritative row; it never silently repaired files.
    assert "Committed Winner" in services.get_persona_soul(pid, store)["content"]
    assert services.get_persona_surface_operation("publish-1", store=store)["status"] == "outcome_unknown"


@pytest.mark.parametrize("data", [b"not a PNG", png(size=(2049, 1)), png()[:30]])
def test_native_image_delivery_rejects_invalid_or_excessive_png(data):
    with pytest.raises(ValueError):
        avatar.validate_avatar_png(data)

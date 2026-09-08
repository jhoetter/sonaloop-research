"""The product JSON API preserves existing CSRF/access authority and native DTOs."""
import json

import pytest
from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.services import _substrate
from conftest import create_persona


@pytest.fixture
def client():
    _substrate.clear_access_guards()
    with TestClient(web.create_app()) as client:
        yield client
    _substrate.clear_access_guards()


def test_http_native_roundtrip_and_operation_inspection(store, client):
    pid = create_persona(store, "HTTP")
    read = client.get(f"/api/personas/{pid}/surface")
    assert read.status_code == 200 and "no-store" in read.headers["cache-control"]
    dto = read.json()["structuredContent"]
    updated = client.post(f"/api/personas/{pid}/surface/actions", json={
        "action": "update", "operation_id": "http-1", "expected_version": dto["version"],
        "changes": {"display_name": "Same Native Persona"}, "csrf_token": client.cookies["sl_csrf"]})
    assert updated.status_code == 200
    current = updated.json()["structuredContent"]
    assert current["fields"]["display_name"] == store.get_persona(pid)["display_name"]
    assert current == services.get_persona_surface(pid, store=store)
    status = client.get("/api/personas/surface-operations/http-1")
    assert status.json()["structuredContent"]["status"] == "succeeded"
    assert status.json()["structuredContent"]["result"] == current
    assert "no-store" in status.headers["cache-control"]


@pytest.mark.parametrize("change", [{}, {"csrf_token": "wrong"}, {"extra": 1},
                                    {"prompt": "irrelevant"}, {"changes": {"avatar": {}}}, {"action": []}])
def test_http_rejects_missing_csrf_or_invalid_payload_without_mutating(store, client, change):
    pid = create_persona(store, "Guarded")
    dto = client.get(f"/api/personas/{pid}/surface").json()["structuredContent"]
    payload = {"action": "update", "operation_id": "denied", "expected_version": dto["version"],
               "changes": {"display_name": "Denied"}, "csrf_token": client.cookies["sl_csrf"]}
    if change:
        payload.update(change)
    else:
        del payload["csrf_token"]
    response = client.post(f"/api/personas/{pid}/surface/actions", json=payload)
    assert response.status_code in {403, 422}
    assert response.json()["error"]["code"] in {"forbidden", "validation"}
    assert store.get_persona(pid)["display_name"] == "Guarded"


def test_http_viewer_cannot_write_and_error_is_structured(store, client):
    pid = create_persona(store, "Viewer")
    dto = client.get(f"/api/personas/{pid}/surface").json()["structuredContent"]
    def deny(operation, resource):
        if operation.startswith("web."):
            raise PermissionError("private membership details")
    _substrate.register_access_guard(deny)
    response = client.post(f"/api/personas/{pid}/surface/actions", json={
        "action": "update", "operation_id": "viewer", "expected_version": dto["version"],
        "changes": {"age": 60}, "csrf_token": client.cookies["sl_csrf"]})
    assert response.status_code == 403 and "private membership" not in response.text
    assert response.json()["error"]["code"] == "forbidden"


def test_http_size_nonfinite_json_and_unknown_persona(store, client):
    pid = create_persona(store, "Bounded")
    url = f"/api/personas/{pid}/surface/actions"
    too_big = client.post(url, content=" " * 16385, headers={"Content-Type": "application/json"})
    assert too_big.status_code == 422
    nonfinite = client.post(url, content='{"changes":{"age":NaN}}', headers={"Content-Type": "application/json"})
    assert nonfinite.status_code == 422
    assert client.get("/api/personas/missing/surface").status_code == 404
    assert client.get("/api/personas/surface-operations/missing").status_code == 404

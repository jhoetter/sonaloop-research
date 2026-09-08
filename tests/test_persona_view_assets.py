"""Customer UI packaging and native SSR mounts; no model/image/provider calls."""
import hashlib
import json
import re
from pathlib import Path

from starlette.testclient import TestClient

from conftest import create_persona
from sonaloop import web
from sonaloop.web._persona_view import persona_view_mount
from sonaloop.web._forms import _CSRF

PACKAGE = Path(__file__).resolve().parents[1] / "sonaloop"


def test_manifest_and_hashed_assets_match_package_bytes():
    manifest = json.loads((PACKAGE / "mcp_server/ui/persona.manifest.json").read_text())
    build_id = manifest.pop("build_id")
    assert build_id == hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    resource = manifest["resource"]
    html = (PACKAGE / "mcp_server/ui" / resource["file"]).read_bytes()
    assert hashlib.sha256(html).hexdigest() == resource["sha256"]
    assert len(html) == resource["bytes"]
    assert resource["uri"] == "ui://sonaloop/persona/v1"
    for asset in manifest["product"].values():
        assert re.fullmatch(r"persona-view/built/persona\.[a-f0-9]{64}\.(js|css)", asset["file"])
        assert hashlib.sha256((PACKAGE / "web/assets" / asset["file"]).read_bytes()).hexdigest() == asset["sha256"]


def test_mount_seed_is_inert_and_request_local():
    token = _CSRF.set("request-private-test-token")
    try:
        markup = str(persona_view_mount('persona_</script><img src=x onerror="alert(1)">'))
    finally:
        _CSRF.reset(token)
    seed = re.search(r'<script type="application/json">(.*?)</script>', markup).group(1)
    assert "<" not in seed
    assert json.loads(seed)["csrf_token"] == "request-private-test-token"
    assert json.loads(seed)["persona_id"].startswith("persona_</script>")
    for path in (PACKAGE / "web/assets/persona-view/built").glob("*"):
        assert b"request-private-test-token" not in path.read_bytes()
    assert b"request-private-test-token" not in (PACKAGE / "mcp_server/ui/persona.html").read_bytes()


def test_native_detail_and_drawer_keep_research_and_mount_same_view(store):
    persona = create_persona(store, "Native UI fixture")
    client = TestClient(web.create_app())
    for query in ("?lang=en", "?lang=de", "?slide=1&lang=en"):
        response = client.get(f"/personas/{persona}{query}")
        assert response.status_code == 200
        assert "data-persona-view" in response.text
        assert "Native UI fixture" in response.text  # SSR fallback stays usable without JS.
        assert f'"persona_id": "{persona}"' in response.text
        assert "cal" in response.text and "readiness" in response.text
        assert "no-store" in response.headers["cache-control"]
    full = client.get(f"/personas/{persona}?lang=en")
    seed = re.search(r'<script type="application/json">([^<]*"persona_id"[^<]*)</script>', full.text).group(1)
    assert json.loads(seed)["csrf_token"] == client.cookies.get("sl_csrf")
    paths = re.findall(r'(?:src|href)="(/web-assets/persona-view/built/[^"]+)"', full.text)
    assert len(paths) == 2 and len(set(paths)) == 2
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]


def test_shared_assets_register_once_for_multiple_apps(store):
    persona = create_persona(store, "Shell fixture")
    for _ in range(2):
        response = TestClient(web.create_app()).get(f"/personas/{persona}")
        assert response.text.count('/web-assets/persona-view/built/persona.') == 2

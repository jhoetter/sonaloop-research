"""Native catalog transport fixtures, pure Product bodies and passive outcomes."""
import asyncio
from copy import deepcopy
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_catalog_tools import _mini_catalog, _no_data_pkg, _bump_local, FUTURE
from sonaloop import config, services, web
from sonaloop.services import _catalog as native
from sonaloop.storage import Store
from sonaloop.ui_components import persona_catalog as ui, persona_catalog_rows as rows


TOOLS = {"catalog_search": ui.search, "catalog_recommend": ui.recommendations,
         "catalog_status": ui.status, "catalog_pull": ui.pulled}


def forbidden(*args, **kwargs):
    pytest.fail("Catalog view attempted provider, media, source, clock or persistence access")


@pytest.fixture(autouse=True)
def isolated_seams(monkeypatch):
    from sonaloop import avatar, embeddings
    from sonaloop.services import _hooks
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(avatar, "generate_persona_avatar", forbidden)
    monkeypatch.setattr(embeddings, "_post_json", forbidden)
    monkeypatch.setattr(native, "embeddings_enabled", lambda: False)
    original = services.record_persona
    monkeypatch.setattr(services, "record_persona", lambda *a, **kw: original(*a, **{**kw, "generate_avatar": False}))
    monkeypatch.delenv("SONALOOP_CATALOG_TOKEN", raising=False)


def original_server():
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_catalog
    server = FastMCP("original-persona-catalog")
    _tools_catalog.register_catalog(server)
    return server


def real_recommender(monkeypatch, tmp_path, profiles):
    """Load only the optional algorithm/rules, with no catalog/profile file reads."""
    source = Path(os.environ["RESEARCH_DATA_SOURCE_ROOT"])
    package_dir = source / "src/sonaloop_data"
    proof = {"kind": "real_pure_algorithm_with_authored_profiles", "git_commit": subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(), "files": {}}
    for name in ("recommend.py", "facets.py", "facet_rules.json"):
        path = package_dir / name
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes()
        assert data == subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{relative}"])
        proof["files"][relative] = hashlib.sha256(data).hexdigest()
    package = types.ModuleType("_research_catalog_algorithm")
    package.__path__ = [str(package_dir)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    loaded = {}
    for name in ("facets", "recommend"):
        spec = importlib.util.spec_from_file_location(package.__name__ + "." + name, package_dir / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[name] = module
    pkg = types.ModuleType("sonaloop_data")
    pkg.recommend = lambda spec: loaded["recommend"].recommend(spec, profiles=profiles)
    pkg.read_persona_files = lambda: iter(deepcopy(profiles))
    pkg.derive_facets = loaded["facets"].derive_facets
    paths = types.ModuleType("sonaloop_data.paths")
    paths.catalog_root = lambda: tmp_path
    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setitem(sys.modules, "sonaloop_data", pkg)
    monkeypatch.setitem(sys.modules, "sonaloop_data.paths", paths)
    return proof


@pytest.fixture
def examples(store, tmp_path, monkeypatch):
    _no_data_pkg(monkeypatch)
    source = Store(tmp_path / "source.db")
    files, profiles = _mini_catalog(source, ["Ada Catalog", "Bert Premium", "Cora Catalog"])
    source.close()
    manifest = json.loads(files["manifest.json"])
    premium = profiles[1]["slug"]
    manifest["personas"][1]["tier"] = "premium"
    files["manifest.json"] = json.dumps(manifest).encode()
    base = native._base_url() + "/"
    def fetch(url):
        assert url.startswith(base), "Only the synthetic catalog transport is allowed"
        path = url[len(base):]
        assert not path.endswith("avatar.png")
        if path == f"personas/{premium}/profile.json":
            raise native.CatalogAuthError("Synthetic premium gate")
        return files.get(path)
    monkeypatch.setattr(native, "_fetch_bytes", fetch)
    # Keep importer temporary snapshots inside this test's ROOT so native
    # reported counts are returned rather than the legacy path-summary fallback.
    monkeypatch.setattr(native.tempfile, "tempdir", str(tmp_path))
    server, result = original_server(), []
    def call(tool, arguments, scenario):
        envelope = server._tool_manager._tools[tool].fn(**arguments)
        assert envelope["ok"]
        value = deepcopy(envelope["data"])
        markup, state = TOOLS[tool](value)
        assert markup and state in {"ready", "empty"}
        result.append({"scenario": scenario, "tool": tool, "input": deepcopy(arguments), "value": value, "state": state})
        return value
    first = call("catalog_search", {"limit": 1}, "catalog-search-first")
    call("catalog_search", {"cursor": first["next_cursor"]}, "catalog-search-last")
    call("catalog_search", {"query": "no-matching-persona"}, "catalog-search-empty")
    call("catalog_search", {"facets": {"tier": ["premium"]}}, "catalog-search-tier")
    call("catalog_recommend", {"spec": {"keywords": ["checklist"], "n": 2}}, "catalog-recommend-unavailable")
    call("catalog_status", {}, "catalog-status-empty")
    call("catalog_pull", {"persona_slugs": [p["slug"] for p in profiles]}, "catalog-pull-mixed")
    call("catalog_pull", {"persona_slugs": [profiles[0]["slug"]]}, "catalog-pull-repeated")
    call("catalog_status", {}, "catalog-status-current")
    _bump_local(store, profiles[0]["slug"])
    call("catalog_status", {}, "catalog-status-local")
    call("catalog_pull", {"persona_slugs": [profiles[0]["slug"]]}, "catalog-pull-preserved")
    for entry in manifest["personas"]:
        entry["updated_at"] = FUTURE
    files["manifest.json"] = json.dumps(manifest).encode()
    call("catalog_status", {}, "catalog-status-diverged-behind")
    manifest["generated_at"] = FUTURE
    del manifest["personas"][2]["updated_at"]
    files["manifest.json"] = json.dumps(manifest).encode()
    call("catalog_status", {}, "catalog-status-coarse")
    manifest["personas"].pop()
    files["manifest.json"] = json.dumps(manifest).encode()
    call("catalog_status", {}, "catalog-status-removed")
    if os.environ.get("RESEARCH_DATA_SOURCE_ROOT"):
        authored = deepcopy(profiles[:2])
        authored[0]["goals"] = ["Keep a useful checklist"]
        with monkeypatch.context() as patch:
            proof = real_recommender(patch, tmp_path, authored)
            call("catalog_recommend", {"spec": {"keywords": ["checklist"], "n": 2, "min_coverage": 3}},
                 "catalog-recommend-ranked")
            result[-1]["fixture_source"] = proof
            call("catalog_search", {"facets": {"tier": ["free"]}}, "catalog-search-local")
            result[-1]["fixture_source"] = proof
    return result


def case(examples, scenario):
    return next(row["value"] for row in examples if row["scenario"] == scenario)


def test_actual_four_native_shapes_and_fixture_export(examples, store, tmp_path):
    assert {row["tool"] for row in examples} == set(TOOLS)
    assert case(examples, "catalog-search-first")["has_more"] is True
    assert "next_cursor" not in case(examples, "catalog-search-last")
    assert case(examples, "catalog-recommend-unavailable")["skipped"] is True
    mixed = case(examples, "catalog-pull-mixed")
    assert len(mixed["landed"]) == 2 and len(mixed["skipped_premium"]) == 1
    assert mixed["counts"]["personas"] == 2 and mixed["counts"]["avatars"] == 0
    assert len(store.list_personas()) == 2
    assert case(examples, "catalog-pull-repeated")["landed"][0]["id"] == mixed["landed"][0]["id"]
    sizes = {row["scenario"]: len(json.dumps({"name": row["tool"], "value": row["value"]},
        ensure_ascii=False, separators=(",", ":")).encode()) for row in examples}
    assert max(sizes.values()) <= 8192
    target = Path(os.environ.get("RESEARCH_CATALOG_FIXTURE_PATH", tmp_path / "catalog-native.json"))
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print("Catalog native fixtures:", target, "count:", len(examples), "sizes:", sizes)


def test_rendering_never_reads_catalog_store_media_clock_or_repeats_pull(examples, monkeypatch):
    before = deepcopy(examples)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        for name in ("read_text", "read_bytes", "exists"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(config, "utc_now_iso", forbidden)
        for name in (*TOOLS, "catalog_avatar"):
            patch.setattr(services, name, forbidden)
        patch.setattr(native, "_data_pkg", forbidden)
        patch.setattr(native, "_fetch_bytes", forbidden)
        for item in examples:
            TOOLS[item["tool"]](item["value"])
    assert examples == before


def test_native_sync_states_nullable_dates_counts_and_skips_are_not_recomputed(examples):
    for scenario, expected in (("catalog-status-current", {"up_to_date"}),
        ("catalog-status-local", {"locally_modified", "up_to_date"}),
        ("catalog-status-diverged-behind", {"diverged", "behind"}),
        ("catalog-status-coarse", {"diverged", "possibly_behind"}),
        ("catalog-status-removed", {"diverged", "removed_upstream"})):
        value = case(examples, scenario)
        assert {row["status"] for row in value["items"]} == expected
        markup, _ = ui.status(value)
        assert all(f"<dd>{status}</dd>" in markup for status in expected)
        assert all(html.escape(note) in markup for note in value.get("notes", []))
    coarse = case(examples, "catalog-status-coarse")
    assert coarse["items"][1]["catalog_updated_at"] is None and "<dd>—</dd>" in ui.status(coarse)[0]
    supplied = deepcopy(coarse)
    supplied["counts"] = {"unknown-native-status": 0, "reported-count": 7}
    assert "<dd>7</dd>" in ui.status(supplied)[0] and "<dd>0</dd>" in ui.status(supplied)[0]
    preserved = case(examples, "catalog-pull-preserved")
    assert preserved["landed"] == [] and preserved["personas"] == []
    assert preserved["skipped_locally_modified"][0]["reason"] in ui.pulled(preserved)[0]


def test_actual_recommendation_scores_order_coverage_and_warnings(examples):
    if not os.environ.get("RESEARCH_DATA_SOURCE_ROOT"):
        pytest.skip("Optional real sonaloop-data algorithm checkout not configured")
    value = case(examples, "catalog-recommend-ranked")
    markup, state = ui.recommendations(value)
    assert state == "ready" and value["personas"][0]["base_score"] > 0
    assert value["personas"][1]["base_score"] == 0
    assert markup.index(value["personas"][0]["display_name"]) < markup.index(value["personas"][1]["display_name"])
    assert all(html.escape(note) in markup for note in value["warnings"])
    for row in value["personas"]:
        assert rows.recommendation_row(row) in markup
        assert all(html.escape(reason) in markup for reason in row["rationale"])
    assert html.escape(value["pull_command"]) in markup and "<button" not in markup and "<form" not in markup


def test_product_title_role_row_and_origin_are_exact_shared_bodies(examples, store):
    from sonaloop.web.pages import personas as product
    from sonaloop.web._components import _label
    from sonaloop.web._i18n import t
    entry = case(examples, "catalog-search-first")["items"][0]
    rendered = product._catalog_row(entry, store, {}, {})
    assert rows.catalog_identity_content(entry) in rendered
    stamp = case(examples, "catalog-pull-mixed")["landed"][0]["provenance"]
    tip = " · ".join(x for x in (stamp.get("ref"), stamp.get("pulled_at")) if x)
    assert rows.provenance_tooltip(stamp) == tip
    assert rows.provenance_badge(stamp) == _label(t("persona_from_catalog"), "var(--accent)", "soft", True, tip or None)
    assert rows.provenance_content(stamp) in ui.pulled(case(examples, "catalog-pull-mixed"))[0]
    with pytest.raises(ValueError):
        rows.catalog_row(entry, passive=True, prepared={"action": "cannot pass Product controls"})


def test_untrusted_text_metadata_and_external_paths_are_inert(examples):
    hostile = '<script>call()</script><img src="https://invalid.test/x" onerror="bad()">'
    value = deepcopy(case(examples, "catalog-pull-mixed"))
    value["landed"][0]["display_name"] = hostile * 50
    value["landed"][0]["provenance"].update(ref=hostile, base_url="javascript:bad()", access_token="NEVER-IN-DOM")
    value["skipped_premium"][0]["reason"] = hostile
    value["note"] = hostile
    value["execution_grant"] = "NEVER-IN-DOM"
    markup, _ = ui.pulled(value)
    assert html.escape(hostile * 50) in markup and "javascript:bad()" in markup
    assert "NEVER-IN-DOM" not in markup
    assert all(tag not in markup for tag in ("<script", "<img", "<a ", "<button", "<form"))


@pytest.mark.parametrize("scenario,key,bad", [("catalog-search-first", "total", True),
    ("catalog-search-first", "facet_summary", {"tier": {"free": -1}}),
    ("catalog-status-current", "counts", {"up_to_date": "one"}),
    ("catalog-pull-mixed", "landed", [{"slug": "fake"}]),
    ("catalog-recommend-unavailable", "skipped", False)])
def test_malformed_native_shapes_fall_back_before_presentation(examples, scenario, key, bad):
    item = next(row for row in examples if row["scenario"] == scenario)
    value = deepcopy(item["value"])
    value[key] = bad
    with pytest.raises(ValueError):
        TOOLS[item["tool"]](value)


def product_client(monkeypatch):
    from sonaloop.web.pages import _catalog_results as product
    app = FastAPI()
    product.register_catalog_results(app)
    monkeypatch.setattr(product, "_layout", lambda title, body, *a, **kw: str(body))
    return TestClient(app)


def test_product_readers_call_native_once_and_never_pull(examples, store, monkeypatch):
    before = list(store.conn.iterdump())
    calls = []
    status, recommend = services.catalog_status, services.catalog_recommend
    def read_status(*a, **kw):
        out = status(*a, **kw); calls.append(("status", out, kw)); return out
    def read_recommend(*a, **kw):
        out = recommend(*a, **kw); calls.append(("recommend", out, kw)); return out
    monkeypatch.setattr(services, "catalog_status", read_status)
    monkeypatch.setattr(services, "catalog_recommend", read_recommend)
    monkeypatch.setattr(services, "catalog_pull", forbidden)
    client = product_client(monkeypatch)
    result = client.get("/personas/catalog/status")
    assert result.status_code == 200 and ui.status(calls[-1][1])[0] in result.text and isinstance(calls[-1][2]["store"], Store)
    result = client.get("/personas/catalog/recommendations?keyword=checklist&n=2&min_coverage=3")
    assert result.status_code == 200 and ui.recommendations(calls[-1][1])[0] in result.text
    assert [name for name, _, _ in calls] == ["status", "recommend"]
    assert client.get("/personas/catalog/recommendations?n=0").status_code == 422
    assert client.get("/personas/catalog/recommendations?min_coverage=101").status_code == 422
    assert before == list(store.conn.iterdump())


def test_product_readonly_filters_and_fetch_failure_are_visible(examples, monkeypatch):
    calls = []
    value = case(examples, "catalog-status-empty")
    def read_status(slugs, ref, *, store):
        calls.append((slugs, ref, store))
        return value
    monkeypatch.setattr(services, "catalog_status", read_status)
    monkeypatch.setattr(services, "catalog_pull", forbidden)
    client = product_client(monkeypatch)
    result = client.get("/personas/catalog/status?persona_slugs=first&persona_slugs=second&ref=fixture-ref")
    assert result.status_code == 200 and ui.status(value)[0] in result.text
    assert calls[0][:2] == (["first", "second"], "fixture-ref") and isinstance(calls[0][2], Store)
    def failed(*a, **kw):
        raise native.CatalogFetchError("PRIVATE-TRANSPORT-DETAIL")
    monkeypatch.setattr(services, "catalog_status", failed)
    response = client.get("/personas/catalog/status")
    assert response.status_code == 503 and "PRIVATE-TRANSPORT-DETAIL" not in response.text
    from sonaloop.web._i18n import t
    assert t("rcat_unavailable") in response.text
    monkeypatch.setattr(services, "catalog_status", lambda *a, **kw: {"items": "unsupported"})
    response = client.get("/personas/catalog/status")
    assert response.status_code == 200 and t("rcat_unavailable") in response.text


def test_real_registered_product_routes_and_origin_consumer(examples, store):
    client = TestClient(web.create_app())
    assert client.get("/personas/catalog/status").status_code == 200
    assert client.get("/personas/catalog/recommendations?n=2").status_code == 200
    # The Product keeps its original catalog row controls and provenance badge.
    landed = case(examples, "catalog-pull-mixed")["landed"][0]
    current_stamp = store.get_persona(landed["id"])["provenance"]["catalog"]
    response = client.get(f'/personas/{landed["id"]}')
    assert response.status_code == 200 and rows.provenance_badge(current_stamp) in response.text


def test_actual_fastmcp_four_schemas_outputs_and_one_native_call(examples, monkeypatch):
    from sonaloop.mcp_server import build_server, _tools_catalog
    original, server = original_server(), build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in TOOLS:
        assert new[name].inputSchema == old[name].inputSchema and new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/catalog/v1"
    envelopes, env = [], _tools_catalog._env
    def capture(*a, **kw):
        value = env(*a, **kw); envelopes.append(deepcopy(value)); return value
    monkeypatch.setattr(_tools_catalog, "_env", capture)
    for name in TOOLS:
        item = next(row for row in examples if row["tool"] == name and
                    (name != "catalog_pull" or row["scenario"] == "catalog-pull-preserved"))
        calls, native_fn = [], getattr(services, name)
        def counted(*a, **kw):
            value = native_fn(*a, **kw); calls.append(deepcopy(value)); return value
        with monkeypatch.context() as patch:
            patch.setattr(services, name, counted)
            before = len(envelopes)
            result = asyncio.run(server.call_tool(name, item["input"]))
        assert not result.isError and len(calls) == 1 and len(envelopes) == before + 1
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(envelopes[-1])
        assert result.content == text and result.structuredContent == structured
        assert result.meta["sonaloop/presentation"]["html"] == TOOLS[name](calls[0])[0]

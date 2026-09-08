"""First-run contract (ticket one-sentence-mcp-install): the cold one-liner install
(`claude mcp add sonaloop -- uvx sonaloop-mcp`) must yield a WORKING server with zero
prior setup, and first contact must orient instead of erroring or returning bare
emptiness — over MCP (the orientation envelope), in `sonaloop info` (wiring checks +
the exact register one-liners), and on the web home (the first-steps checklist)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sonaloop.mcp_server import build_server


def _call(server, name: str, args: dict):
    result = asyncio.run(server.call_tool(name, args))
    return result.structuredContent if hasattr(result, "structuredContent") else result[1]


# ---------- 1. cold start: fresh environment, no .env, no data dir ----------

def test_mcp_boots_cold_in_a_fresh_environment(tmp_path):
    """Simulate the cold uvx start: empty HOME, a data dir whose parents don't exist
    yet, no .env, no API keys. Booting the server module and calling a basic tool must
    work — and the first result must carry the 'you're new here' orientation."""
    home = tmp_path / "home"
    home.mkdir()
    data_dir = tmp_path / "deep" / "nested" / "sonaloop-data"   # parents do NOT exist
    script = (
        "import asyncio, json\n"
        "from sonaloop.mcp_server import build_server\n"
        "s = build_server()\n"
        "_, env = asyncio.run(s.call_tool('list_personas', {}))\n"
        "print(json.dumps(env))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env={"PATH": os.environ.get("PATH", ""), "HOME": str(home),
             "SONALOOP_DATA_DIR": str(data_dir)},
        capture_output=True, text=True, timeout=120,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout.strip().splitlines()[-1])
    # list tools answer the shared pagination envelope (docs/pagination.md)
    assert env["ok"] is True and env["data"]["items"] == []
    assert env["data"]["total"] == 0 and env["data"]["has_more"] is False
    assert "start_project" in env.get("orientation", ""), "fresh DB must orient the host"
    assert (data_dir / "sonaloop.db").exists(), "first touch must create the data dir chain"


def test_store_creates_nested_data_dir_on_first_touch(tmp_path, monkeypatch):
    """StoreBase bootstraps the WHOLE directory chain (a per-user dir under a fresh
    $HOME has no existing parents)."""
    from sonaloop.storage import _base
    from sonaloop.storage import Store

    nested = tmp_path / "a" / "b" / "data"
    monkeypatch.setattr(_base, "DATA_DIR", nested)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{nested / 'sonaloop.db'}")
    store = Store()
    assert store.schema_version() > 0
    assert nested.is_dir()
    store.close()


# ---------- 1b. optional providers degrade in-band, never as errors ----------

def test_generate_avatar_without_key_returns_in_band_note(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env = _call(build_server(), "generate_avatar", {"persona_id": "whoever"})
    assert env["ok"] is True
    assert env["data"]["skipped"] is True and env["data"]["avatar"] is None
    assert "OPENAI_API_KEY" in env["data"]["note"]          # the helpful, actionable message


def test_record_persona_with_avatar_flag_is_fail_soft_without_key(monkeypatch, store):
    from tests.conftest import make_profile
    from sonaloop import services

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    persona = services.record_persona("Avatarless Anna — source", make_profile("Avatarless Anna"),
                                      generate_avatar=True, store=store)
    assert persona["id"]                                     # the persona IS created
    assert "OPENAI_API_KEY" in persona["avatar_note"]        # the skip is explained in-band


def test_proto_open_without_browser_returns_in_band_fallback(monkeypatch):
    from sonaloop import browser

    monkeypatch.setattr(browser, "available", lambda: False)
    env = _call(build_server(), "proto_open", {"url": "http://127.0.0.1:1"})
    assert env["ok"] is True
    assert env["data"]["unavailable"] is True
    assert "sonaloop setup" in env["data"]["note"]           # the fix, plus the browserless path
    assert "brief_flow_walkthrough" in env["data"]["note"]


# ---------- 2. first-contact orientation envelope ----------

def test_entry_tools_carry_orientation_only_while_db_is_empty(store):
    from tests.conftest import create_persona

    server = build_server()
    empty = _call(server, "list_research_projects", {})
    assert "project" in empty["orientation"] and "council" in empty["orientation"]
    assert "guide" in empty["orientation"]                   # points at the guide

    # brief_persona is NOT an entry tool — chains stay clean even on an empty DB
    briefed = _call(server, "brief_persona", {"description": "a skeptical baker"})
    assert "orientation" not in briefed

    create_persona(store, "Orienting Otto")
    after = _call(server, "list_research_projects", {})
    assert "orientation" not in after, "the note must never repeat once real work exists"


# ---------- 3. `sonaloop info` checks the MCP wiring end-to-end ----------

def test_info_payload_reports_wiring_and_exact_register_oneliners(tmp_path, monkeypatch):
    from sonaloop._diagnostics import info_payload

    monkeypatch.setenv("HOME", str(tmp_path))                # no host configs on this "machine"
    monkeypatch.chdir(tmp_path)                              # and no project-level .mcp.json
    payload = info_payload("0.0.0+test")
    wiring = payload["mcp"]
    assert wiring["data_dir_writable"] is True
    assert set(wiring["registered"]) == {"claude_code", "claude_desktop", "cursor"}
    assert all(v is None for v in wiring["registered"].values())
    reg = wiring["register"]                                 # unregistered -> the verbatim one-liners
    assert reg["claude_code"] == "claude mcp add sonaloop -- uvx sonaloop-mcp"
    assert reg["claude_desktop_or_cursor_json"]["mcpServers"]["sonaloop"] == {
        "command": "uvx", "args": ["sonaloop-mcp"]}
    assert reg["getting_started"].startswith("https://jhoetter.github.io/sonaloop-docs/")
    # browser/embeddings status ride along so one call answers "what's missing?"
    assert {"browser_available", "browser_ready", "embeddings_provider"} <= set(payload)


def test_info_detects_an_existing_registration(tmp_path, monkeypatch):
    from sonaloop._diagnostics import mcp_wiring

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"sonaloop": {"command": "uvx", "args": ["sonaloop-mcp"]}}}),
        encoding="utf-8")
    wiring = mcp_wiring()
    assert wiring["registered"]["claude_code"] is True
    assert "register" not in wiring                          # no nagging once it's wired


# ---------- 5. empty-DB web home = first-steps checklist ----------

def test_home_shows_first_steps_checklist_when_db_is_empty(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS

    client = TestClient(web.create_app())
    html = client.get("/?lang=en").text
    assert STRINGS["en"]["first_steps_h"] in html
    assert STRINGS["en"]["fs_step_project_h"] in html
    assert STRINGS["en"]["fs_step_council_h"] in html
    assert "claude mcp add sonaloop" in html                 # the verbatim one-liner
    assert "sonaloop-docs/getting-started" in html           # link to the canonical guide
    # bilingual chrome: the checklist is i18n'd, not English-only
    assert STRINGS["de"]["first_steps_h"] in client.get("/?lang=de").text


def test_home_returns_to_normal_list_once_content_exists(store):
    from starlette.testclient import TestClient
    from sonaloop import services, web
    from sonaloop.web._i18n import STRINGS

    services.create_research_project("First project", "goal", store=store)
    html = TestClient(web.create_app()).get("/?lang=en").text
    assert STRINGS["en"]["first_steps_h"] not in html
    assert "First project" in html

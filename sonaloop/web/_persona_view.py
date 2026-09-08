"""Mount the customer-owned PersonaView on full pages and SPA/drawer fragments.

Only the adapter and stylesheet are global shell assets. Profile data is fetched
through the authenticated native surface API; the request-local CSRF token never
enters a public cached bundle or the portable MCP resource.
"""
from __future__ import annotations

import json
from pathlib import Path

from ._ext import register_slot
from ._forms import current_csrf_token
from ._html import h, raw
from ._i18n import _lang

_MANIFEST = Path(__file__).resolve().parents[1] / "mcp_server" / "ui" / "persona.manifest.json"


def _assets() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["product"]


def persona_view_mount(persona_id: str) -> str:
    seed = json.dumps({"persona_id": persona_id, "locale": _lang(),
                       "csrf_token": current_csrf_token()}, ensure_ascii=False).replace("<", "\\u003c")
    return h("div", {"class_": "sl-persona-view-mount", "data-persona-view": True,
                     "id": "persona-profile"},
             h("script", {"type": "application/json"}, raw(seed)))


def _head(_store=None) -> str:
    return h("link", {"rel": "stylesheet", "href": "/web-assets/" + _assets()["style"]["file"]})


def _body(_store=None) -> str:
    return h("script", {"src": "/web-assets/" + _assets()["script"]["file"], "defer": True})


# Import-time registration follows the existing shell extension pattern. Import
# caching avoids duplicate slots when tests/hosts create more than one app.
register_slot("head_extra", _head)
register_slot("body_end", _body)

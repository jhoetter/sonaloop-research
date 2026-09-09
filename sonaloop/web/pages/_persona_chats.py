"""Read-only, Persona-scoped consumers of durable chats and continuity proposals."""
from __future__ import annotations

from urllib.parse import quote

from ._ctx import *  # noqa: F401,F403
from ...ui_components import chats, chat_proposals
from ...ui_components.library import collection


def _body(render, value):
    try:
        return render(value)[0]
    except (ValueError, TypeError, KeyError):
        return h("p", {"class_": "muted"}, t("rchat_unavailable"))


def _missing(store):
    return HTMLResponse(_layout(t("not_found"), h("p", {}, t("not_found")), store,
                                active="personas"), status_code=404)


def _page(store, persona, body):
    return _layout(t("rchat_chats"), h("div", {"class_": "sl-syn-main"}, h("h1", {}, t("rchat_chats")), body),
        store, active="personas", crumbs=[(t("personas"), "/personas"),
            (persona["display_name"], f'/personas/{persona["id"]}'), (t("rchat_chats"), None)])


def _proposal_cards(values):
    return collection([_body(chat_proposals.proposal, value) for value in values], empty=t("rchat_no_proposals"))


def register_persona_chats(app):
    @app.get("/personas/{persona_id}/chats", response_class=HTMLResponse)
    def persona_chats(persona_id: str, limit: int = 50, offset: int = 0, status: str | None = None):
        store = Store()
        persona = store.get_persona_for_active_workspace(persona_id)
        if not persona:
            return _missing(store)
        pid = persona["id"]
        page = services.list_chats(pid, limit, offset, store=store)
        try:
            proposals = services.list_memory_proposals(pid, status, store=store)
        except ValueError:
            return HTMLResponse(_page(store, persona, h("p", {}, t("rchat_unavailable"))), status_code=400)
        if any(row.get("persona_id") != pid for row in [*page["items"], *proposals]):
            return _missing(store)
        links = [h("li", {}, h("a", {"href": f'/personas/{quote(pid, safe="")}/chats/{quote(row["id"], safe="")}'},
                                  row["id"])) for row in page["items"]]
        next_page = None
        if page["next_offset"] is not None:
            href = f'/personas/{quote(pid, safe="")}/chats?limit={page["limit"]}&offset={page["next_offset"]}'
            if status:
                href += "&status=" + quote(status, safe="")
            next_page = h("a", {"href": href}, t("pager_next"))
        return _page(store, persona, fragment(_body(chats.chats, page),
            h("ul", {}, links) if links else None, next_page,
            h("h2", {}, t("rchat_proposals")), _proposal_cards(proposals)))

    @app.get("/personas/{persona_id}/chats/{chat_id}", response_class=HTMLResponse)
    def persona_chat(persona_id: str, chat_id: str):
        store = Store()
        persona = store.get_persona_for_active_workspace(persona_id)
        if not persona:
            return _missing(store)
        try:
            value = services.get_chat(chat_id, store=store)
        except KeyError:
            return _missing(store)
        if value.get("persona_id") != persona["id"]:
            return _missing(store)
        proposals = services.list_memory_proposals(persona["id"], store=store)
        if any(row.get("persona_id") != persona["id"] for row in proposals):
            return _missing(store)
        return _page(store, persona, fragment(_body(chats.chat, value), h("h2", {}, t("rchat_proposals")),
            _proposal_cards([row for row in proposals if row.get("chat_id") == value["id"]])))

    @app.get("/personas/{persona_id}/chats/{chat_id}/proposals/{proposal_id}", response_class=HTMLResponse)
    def persona_chat_proposal(persona_id: str, chat_id: str, proposal_id: str):
        store = Store()
        persona = store.get_persona_for_active_workspace(persona_id)
        if not persona:
            return _missing(store)
        try:
            chat = services.get_chat(chat_id, store=store)
            if chat.get("persona_id") != persona["id"]:
                return _missing(store)
            proposal = services.get_memory_proposal(proposal_id, store=store)
        except KeyError:
            return _missing(store)
        if proposal.get("persona_id") != persona["id"] or proposal.get("chat_id") != chat["id"]:
            return _missing(store)
        return _page(store, persona, _body(chat_proposals.proposal, proposal))

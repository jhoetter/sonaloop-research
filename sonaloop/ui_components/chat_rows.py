"""Pure semantic bodies for supplied conversations; no context or source lookup."""
from __future__ import annotations

from .library import _kit
from .projects_rows import record, identity, texts, strings, count, fields, disclosure, t


def records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Expected native chat record list")
    return value


def prose(value):
    if type(value) is not str:
        raise ValueError("Expected native chat text")
    h, _, _ = _kit()
    return h("p", {"class_": "sl-research-prose"}, value)


def section(label, *body):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), *body) if any(body) else None


def card(label, *body):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-chat"}, h("h2", {}, label), *body)


def version(value):
    if type(value.get("substrate_version")) is not int or value["substrate_version"] != 1:
        raise ValueError("Unsupported native chat substrate version")


def chat_identity_content(chat_id, persona_id, turns, *, created_at=None, updated_at=None):
    """Shared by native recording receipts, list rows and the stored Product chat."""
    identity({"chat_id": chat_id}, "chat_id")
    identity({"persona_id": persona_id}, "persona_id")
    count(turns)
    _, fragment, _ = _kit()
    details = [("chat_id", chat_id), ("persona_id", persona_id)]
    for key, value in (("created_at", created_at), ("updated_at", updated_at)):
        if value is not None:
            if type(value) is not str:
                raise ValueError("Expected native chat timestamp")
            details.append((key, value))
    return fragment(fields(((t("rchat_turns"), turns),)), disclosure(t("rpx_record_details"), fields(details)))


def refs_content(values):
    from ..web._render import render_ref
    h, _, raw = _kit()
    refs = []
    for value in records(values):
        # Native chat refs have an open dict shape. Display the meaningful
        # supplied reference fields; never resolve a target or assert grounding.
        texts(value, optional=("kind", "id", "anchor", "quote", "text", "role"))
        if not any(value.get(key) for key in ("id", "quote", "text")):
            raise ValueError("No presentable native chat reference")
        refs.append(h("li", {}, raw(render_ref(value, passive=True))))
    return section(t("rchat_refs"), h("ul", {}, refs), prose(t("rchat_refs_notice"))) if refs else None


def turn_content(value):
    record(value)
    count(value.get("idx"))
    texts(value, ("user_message", "persona_reply", "created_at"))
    h, _, _ = _kit()
    return h("section", {"class_": "sl-research-chat-turn"},
        fields(((t("rchat_index"), value["idx"]),)),
        section(t("rchat_user"), prose(value["user_message"])),
        section(t("rchat_reply"), prose(value["persona_reply"])),
        refs_content(value.get("refs")),
        disclosure(t("rpx_record_details"), fields((("created_at", value["created_at"]),))))


def summary_content(value):
    identity(value, "id")
    identity(value, "persona_id")
    texts(value, ("last_message", "created_at", "updated_at"))
    _, fragment, _ = _kit()
    return fragment(chat_identity_content(value["id"], value["persona_id"], value.get("turns"),
        created_at=value["created_at"], updated_at=value["updated_at"]),
        section(t("rchat_last_message"), prose(value["last_message"])) if value["last_message"] else None)

"""Native chat result projections shared with the read-only Product inspector."""
from __future__ import annotations

from .library import _kit, collection
from .chat_rows import (record, identity, texts, count, fields, disclosure, t,
    records, prose, section, card, version, chat_identity_content, turn_content, summary_content)


def opened(value):
    record(value)
    version(value)
    texts(value, ("schema", "display_name", "message", "history", "soul_path", "agent_context", "instructions"))
    if value["schema"] != "persona_chat":
        raise ValueError("Expected native chat preparation result")
    body = chat_identity_content(value.get("chat_id"), value.get("persona_id"), value.get("turns"))
    return card(t("rchat_opened"), prose(value["display_name"]), body,
        section(t("rchat_message"), prose(value["message"])), prose(t("rchat_open_notice")),
        section(t("rchat_history"), prose(value["history"])) if value["history"] else prose(t("rchat_no_turns")),
        prose(t("rchat_conversation_notice")),
        disclosure(t("rchat_context"), fields((("schema", value["schema"]),
            ("substrate_version", value["substrate_version"]), ("soul_path", value["soul_path"]))),
            prose(value["agent_context"]), section(t("rchat_instructions"), prose(value["instructions"])))), "ready"


def recorded(value):
    record(value)
    texts(value, ("updated_at",))
    return card(t("rchat_recorded"),
        chat_identity_content(value.get("chat_id"), value.get("persona_id"), value.get("turns"),
                              updated_at=value["updated_at"]), prose(t("rchat_receipt_notice"))), "ready"


def chat_content(value):
    identity(value, "id")
    identity(value, "persona_id")
    texts(value, ("created_at", "updated_at"))
    turns = records(value.get("turns"))
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-chat-content"},
        chat_identity_content(value["id"], value["persona_id"], len(turns),
                              created_at=value["created_at"], updated_at=value["updated_at"]),
        prose(t("rchat_conversation_notice")),
        [turn_content(turn) for turn in turns] if turns else prose(t("rchat_no_turns")))


def chat(value):
    body = chat_content(value)
    return card(t("rchat_chat"), body), "ready" if value["turns"] else "empty"


def chats(value):
    record(value)
    version(value)
    items = records(value.get("items"))
    for key in ("total", "limit", "offset"):
        count(value.get(key))
    if "next_offset" not in value:
        raise ValueError("Expected native next chat offset")
    if value["next_offset"] is not None:
        count(value["next_offset"])
    _, fragment, _ = _kit()
    return fragment(collection([card(t("rchat_chat"), summary_content(item)) for item in items],
        empty=t("rchat_no_chats"), total=value["total"], has_more=value["next_offset"] is not None),
        disclosure(t("rpx_record_details"), fields([(key, value[key]) for key in
            ("substrate_version", "total", "limit", "offset", "next_offset")]))), "ready" if items else "empty"

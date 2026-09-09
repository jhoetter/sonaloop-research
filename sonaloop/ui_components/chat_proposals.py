"""Supplied review states for chat continuity, without approval or memory effects."""
from __future__ import annotations

from .library import _kit, collection
from .chat_rows import (record, identity, texts, strings, fields, disclosure, t,
    records, prose, section, card, refs_content)


def proposal_content(value):
    identity(value, "id")
    identity(value, "persona_id")
    identity(value, "chat_id")
    texts(value, ("schema", "source_kind", "scope", "status", "created_at", "updated_at"),
          ("decision", "review_reason", "reviewed_at"))
    if value["schema"] != "sonaloop.persona_memory_proposal.v1" or value["source_kind"] != "conversation" \
            or value["scope"] != "conversation_continuity_only":
        raise ValueError("Unsupported native chat continuity scope")
    states = {"pending": t("rchat_pending"), "approved": t("rchat_approved"), "rejected": t("rchat_rejected")}
    if value["status"] not in states:
        raise ValueError("Unknown native proposal review status")
    if "decision" in value and value["decision"] not in {"approve", "reject"}:
        raise ValueError("Unknown native proposal review decision")
    indexes = value.get("turn_indexes")
    # Native selection retains requested indices even when not every target
    # resolves. Preserve signed integers and never manufacture source validation.
    if not isinstance(indexes, list) or any(type(index) is not int for index in indexes):
        raise ValueError("Expected native supplied turn indices")
    proposed = record(value.get("proposal"))
    texts(proposed, ("summary",))
    notes = strings(proposed.get("continuity_notes"))
    h, _, _ = _kit()
    technical = [(key, value[key]) for key in ("id", "persona_id", "chat_id", "schema", "source_kind", "scope",
        "status", "created_at", "updated_at", "decision", "reviewed_at") if key in value]
    return h("div", {"class_": "sl-research-chat-content"},
        prose(states[value["status"]]), prose(proposed["summary"]),
        section(t("rchat_notes"), h("ul", {}, [h("li", {}, note) for note in notes])) if notes else None,
        section(t("rchat_review_reason"), prose(value["review_reason"])) if value.get("review_reason") else None,
        prose(t("rchat_scope_notice")),
        disclosure(t("rpx_record_details"), fields(technical),
            fields(((t("rchat_indexes"), ", ".join(str(index) for index in indexes)),)),
            refs_content(value.get("source_refs"))))


def proposal(value):
    return card(t("rchat_proposal"), proposal_content(value)), "ready"


def proposals(value):
    items = records(value)
    return collection([proposal(item)[0] for item in items], empty=t("rchat_no_proposals")), "ready" if items else "empty"

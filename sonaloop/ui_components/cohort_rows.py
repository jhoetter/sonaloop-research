"""Escaped semantic rows for supplied cohort diagnostics and Product history."""
from __future__ import annotations

import math

from .library import _kit
from .projects_rows import record, identity, texts, strings, count, fields, disclosure as _disclosure, t


def records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Expected native cohort records")
    return value


def number(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("Expected finite native cohort measurement")


def flags(value, *keys):
    record(value)
    if any(type(value.get(key)) is not bool for key in keys):
        raise ValueError("Expected native cohort boolean")


def nullable(value, *keys):
    record(value)
    if any(key not in value or value[key] is not None and type(value[key]) is not str for key in keys):
        raise ValueError("Expected native cohort text or null")


def counts(value):
    record(value)
    for key, item in value.items():
        if type(key) is not str:
            raise ValueError("Expected cohort count label")
        count(item)
    return fields(value.items()) if value else note(t("rcg_no_entries"))


def _has_body(value):
    return any(_has_body(item) for item in value) if isinstance(value, (list, tuple)) else bool(value)


def section(title, *body):
    h, _, _ = _kit()
    if not _has_body(body):
        return None
    return h("section", {"class_": "sl-research-cohort-section"}, h("h3", {}, title), *body)


def disclosure(title, *body):
    return _disclosure(title, *body) if _has_body(body) else None


def text_list(title, value):
    h, _, _ = _kit()
    items = strings(value)
    return section(title, h("ul", {}, [h("li", {}, item) for item in items])) if items else None


def card(title, *body):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-cohort"}, h("h2", {}, title), *body)


def note(value):
    h, _, _ = _kit()
    if type(value) is not str:
        raise ValueError("Expected native cohort prose")
    return h("p", {"class_": "sl-research-prose"}, value)


def refs(value):
    from ..web._render import render_ref
    h, _, raw = _kit()
    result = []
    for item in records(value):
        texts(item, ("kind", "id"))
        result.append(h("li", {}, raw(render_ref(item, passive=True))))
    return h("ul", {}, result) if result else None


def selection_content(persona_ids, rationale):
    """The same selected identities/rationale in a native result or stored revision."""
    _, fragment, _ = _kit()
    if type(rationale) is not str:
        raise ValueError("Expected native cohort selection rationale")
    return fragment(text_list(t("personas"), persona_ids), note(rationale) if rationale else None)


def revisions(value):
    result = []
    for item in records(value):
        texts(item, ("rationale", "created_at"))
        result.append(card(t("rcg_selection"), selection_content(item.get("to"), item["rationale"]),
            disclosure(t("rpx_record_details"), text_list(t("rcg_previous_cohort"), item.get("from")),
                       fields((("created_at", item["created_at"]),)))))
    from .library import collection
    return collection(result, empty=t("rcg_no_revisions"))


def dispatch_status(value):
    """Only returned state/checkpoint facts; grants, tokens and calls stay in MCP."""
    texts(value, ("state",))
    flags(value, "checkpointed")
    return fields((("dispatch_state", value["state"]), ("checkpointed", value["checkpointed"])))

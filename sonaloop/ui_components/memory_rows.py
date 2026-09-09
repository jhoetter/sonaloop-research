"""Pure memory rows shared with the inspector; all resolved context is explicit."""
from __future__ import annotations

import math

from .library import _kit


def t(*args, **kwargs):
    from ..web._i18n import t as translate
    return translate(*args, **kwargs)


def text_record(value, required=(), optional=(), nullable=()):
    if not isinstance(value, dict):
        raise ValueError("Expected native memory record")
    for key in required:
        if not isinstance(value.get(key), str):
            raise ValueError(f"Expected native memory {key}")
    for key in optional:
        if key in value and not isinstance(value[key], str):
            raise ValueError(f"Expected native memory {key}")
    for key in nullable:
        if value.get(key) is not None and not isinstance(value[key], str):
            raise ValueError(f"Expected native memory {key}")
    return value


def records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Expected native memory record list")
    return value


def strings(value):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Expected native memory strings")
    return value


def number(value, *, count=False):
    if (type(value) not in ((int,) if count else (int, float)) or not math.isfinite(value)
            or (count and value < 0)):
        raise ValueError("Expected finite native memory measurement")
    return value


def fields(rows):
    h, fragment, _ = _kit()
    return h("dl", {"class_": "sl-research-fields"},
             [fragment(h("dt", {}, label), h("dd", {}, str(value).lower() if type(value) is bool else value))
              for label, value in rows if value is not None and value != ""])


def references(value):
    from ..web._render import render_ref
    h, _, _ = _kit()
    refs = records(value)
    for ref in refs:
        text_record(ref, nullable=("kind", "id", "anchor", "role", "text", "quote"))
    return h("div", {"class_": "sl-research-references"},
             h("h4", {}, t("rc_source_refs")), [render_ref(ref, passive=True) for ref in refs]) if refs else None


def provenance(value):
    text_record(value, nullable=("source_kind", "review_status", "source_event_id"))
    confidence = value.get("confidence")
    if confidence is not None:
        number(confidence)
    return fields(((t("rc_source_kind"), value.get("source_kind")),
                   (t("rc_review_status"), value.get("review_status")),
                   (t("rc_confidence"), confidence), ("source_event_id", value.get("source_event_id")))), references(value.get("source_refs", []))


def entity_record(value):
    text_record(value, ("id", "persona_id", "kind", "name"),
                nullable=("status", "first_seen", "last_seen", "created_at", "updated_at"))
    strings(value.get("aliases", []))
    return value


def fact_record(value):
    text_record(value, ("t_valid", "fact"), nullable=("id", "persona_id", "entity_id", "status", "t_invalid", "created_at"))
    if "valid" in value and type(value["valid"]) is not bool:
        raise ValueError("Expected native current fact validity")
    if value.get("importance") is not None:
        number(value["importance"])
    provenance(value)
    return value


def thread_record(value):
    return text_record(value, ("id", "persona_id", "text", "status"),
                       nullable=("entity_id", "opened_on", "closed_on", "created_at", "updated_at"))


def source_label(source_kind):
    return {"simulated_episode": t("memory_source_simulated"), "observed": t("memory_source_observed"),
            "real_evidence": t("memory_source_evidence"), "evidence": t("memory_source_evidence"),
            "derived_fact": t("memory_source_derived")}.get(
                source_kind, source_kind.replace("_", " ") if source_kind else t("memory_source_derived"))


def kind_label(kind):
    return {"project": t("active_projects"), "person": t("mem_people"),
            "topic": t("mem_topics"), "tool": t("mem_tools")}.get(kind, kind)


def fact_row(value, *, prepared=None, passive=False):
    """Native full/reduced fact, with optional product date and superseded badge."""
    h, fragment, _ = _kit()
    fact_record(value)
    prepared = prepared or {}
    superseded = bool(value.get("t_invalid"))
    review = value.get("review_status")
    review_label = (t("memory_reviewed") if review == "reviewed" else review
                    if review and review != "unreviewed" else t("memory_unreviewed"))
    details = fields((("id", value.get("id")), (t("persona"), value.get("persona_id")),
                      ("entity_id", value.get("entity_id")), (t("rm_status"), value.get("status")),
                      (t("rm_valid_from"), value["t_valid"]), (t("rm_valid_until"), value.get("t_invalid")),
                      (t("rm_valid_now"), value.get("valid")), (t("rm_importance"), value.get("importance")),
                      (t("rc_created_at"), value.get("created_at")))) if passive else None
    return h("div", {"class_": "mem-fact sl-research-memory-fact" +
                      (" sup sl-research-memory-superseded" if superseded else "")},
             h("span", {"class_": "mem-date sl-research-meta"}, prepared.get("date", value["t_valid"])),
             h("span", {"class_": "mem-fx sl-research-prose"}, value["fact"],
               fragment(" ", prepared.get("superseded", h("span", {}, t("outdated")))) if superseded else None,
               h("span", {"class_": "sl-mem-fx-meta"},
                 f'{source_label(value.get("source_kind") or "")} · {review_label}') if not passive else None),
             details, provenance(value) if passive else None)


def entity_card(value, facts=None, *, prepared=None, passive=False):
    """The inspector entity/timeline body; absent facts mean none were supplied."""
    h, fragment, _ = _kit()
    entity_record(value)
    prepared = prepared or {}
    rows = [fact_row(fact, prepared=(prepared.get("facts") or {}).get(i), passive=passive)
            for i, fact in enumerate(records(facts if facts is not None else []))]
    status = h("span", {"class_": "mem-status"}, value["status"]) if value.get("status") else None
    return h("div", {"class_": "mem-ent sl-research-memory-entity"},
             h("div", {"class_": "mem-ent-h"}, prepared.get("icon"), h("b", {}, value["name"]), status),
             fields((("id", value["id"]), (t("persona"), value["persona_id"]),
                     (t("type_h"), value["kind"]), (t("rm_status_now"), value.get("status")),
                     (t("rm_first_seen"), value.get("first_seen")), (t("rm_last_seen"), value.get("last_seen")),
                     (t("rc_created_at"), value.get("created_at")), ("updated_at", value.get("updated_at")))) if passive else None,
             h("div", {}, h("h3", {}, t("rm_aliases")), h("ul", {}, [h("li", {}, alias) for alias in value.get("aliases", [])]))
             if passive and value.get("aliases") else None,
             h("div", {"class_": "mem-tl"}, fragment(rows)) if rows else
             h("p", {"class_": "muted small"}, "—") if facts is not None else None)


def thread_row(value, *, prepared=None, passive=False):
    h, _, _ = _kit()
    thread_record(value)
    prepared = prepared or {}
    return h("div", {"class_": "mem-loop sl-research-memory-thread"},
             h("span", {"class_": "mem-loop-dot"}), h("span", {"class_": "sl-research-prose"}, value["text"]),
             h("span", {"class_": "muted small"}, f' · {t("since")} {prepared.get("opened", value.get("opened_on") or "")}')
             if not passive else fields((("id", value["id"]), (t("persona"), value["persona_id"]),
                 ("entity_id", value.get("entity_id")), (t("rm_status_now"), value["status"]),
                 (t("rm_opened"), value.get("opened_on")), (t("rm_closed"), value.get("closed_on")),
                 (t("rc_created_at"), value.get("created_at")), ("updated_at", value.get("updated_at")))))


def recall_row(value, *, passive=False):
    h, _, _ = _kit()
    text_record(value, ("obj_type", "obj_id", "text"), nullable=("when",))
    for key in ("score", "semantic", "keyword", "recency", "importance"):
        number(value.get(key))
    provenance(value)
    return h("div", {"class_": "mem-hit sl-research-memory-hit"},
             h("span", {"class_": "muted small sl-research-meta"}, f'{value["obj_type"]} · {value.get("when") or ""}'),
             h("div", {"class_": "sl-research-prose"}, value["text"]),
             h("p", {"class_": "sl-research-meta"}, t("rm_excerpt")) if passive else None,
             fields((("id", value["obj_id"]), (t("rm_score"), value["score"]),
                     (t("rm_semantic"), value["semantic"]), (t("rm_keyword"), value["keyword"]),
                     (t("rm_recency"), value["recency"]), (t("rm_importance"), value["importance"]))) if passive else None,
             provenance(value) if passive else None)

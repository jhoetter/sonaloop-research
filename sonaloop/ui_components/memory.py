"""Native memory projections and the product inspector's shared semantic bodies."""
from __future__ import annotations

from .library import _kit, collection, note_content
from . import memory_rows as rows
from .memory_rows import t


def _card(title, *body):
    return _kit()[0]("article", {"class_": "sl-research-card"}, _kit()[0]("h2", {}, title), *body)


def _list(cards):
    return collection(cards, empty=t("rm_empty")), "ready" if cards else "empty"


def active_projects(value):
    h, _, _ = _kit()
    cards = []
    for item in rows.records(value):
        rows.text_record(item, ("entity_id", "name"), nullable=("status", "last_seen"))
        for key in ("open_loops", "valid_facts"):
            rows.number(item.get(key), count=True)
        cards.append(_card(item["name"], h("p", {"class_": "sl-research-kind"}, t("active_projects")),
            rows.fields((("entity_id", item["entity_id"]), (t("rm_status_now"), item.get("status")),
                         (t("rm_last_seen"), item.get("last_seen")), (t("open_threads"), item["open_loops"]),
                         (t("rm_valid_now") + " · " + t("rm_facts"), item["valid_facts"])))))
    return _list(cards)


def entities(value):
    return _list([_card(t("rm_entities"), rows.entity_card(item, passive=True)) for item in rows.records(value)])


def entity(value):
    if value is None:
        return collection([], empty=t("rm_entity_empty")), "empty"
    return _card(t("rm_entities"), rows.entity_card(value, passive=True)), "ready"


def project(value):
    h, _, _ = _kit()
    rows.text_record(value, nullable=("status_now",))
    if not {"entity", "status_now", "facts", "open_threads", "event_ids"} <= value.keys():
        raise ValueError("Expected native memory project timeline")
    for fact in rows.records(value["facts"]):
        rows.fact_record(fact)
        if type(fact.get("valid")) is not bool:
            raise ValueError("Expected native project fact validity")
    threads_value = rows.records(value["open_threads"])
    events = rows.strings(value["event_ids"])
    return _card(t("active_projects"), rows.entity_card(value["entity"], value["facts"], passive=True),
        rows.fields(((t("rm_status_now"), value["status_now"]),)),
        h("p", {"class_": "sl-research-meta"}, t("rm_project_notice")),
        h("h3", {}, t("open_threads")), [rows.thread_row(item, passive=True) for item in threads_value],
        h("h3", {}, t("rmo_events")), h("ul", {}, [h("li", {}, eid) for eid in events])), "ready"


def knowledge_content(prepared_groups):
    """Product knowledge graph with pre-resolved facts and display-only fragments."""
    h, fragment, _ = _kit()
    sections = []
    for kind, values in prepared_groups:
        sections.append(h("div", {"class_": "mem-group"},
            h("div", {"class_": "mem-group-h"}, rows.kind_label(kind), h("span", {"class_": "mem-n"}, str(len(values)))),
            h("div", {"class_": "mem-ents"}, [rows.entity_card(item, facts, prepared=prepared)
                for item, facts, prepared in values])))
    return h("div", {"class_": "sl-research-memory-knowledge"},
             fragment(sections) if sections else h("p", {"class_": "muted"}, t("none")))


def state_content(value, *, passive=False):
    h, fragment, _ = _kit()
    rows.text_record(value, ("persona_id", "as_of"))
    entities_value = rows.records(value.get("entities"))
    threads_value = rows.records(value.get("open_threads"))
    world_value = rows.records(value.get("world_context"))
    entity_rows = []
    for item in entities_value:
        rows.text_record(item, ("entity_id", "kind", "name"), nullable=("status_at",))
        facts = [rows.fact_row(fact, passive=passive) for fact in rows.records(item.get("facts"))]
        if passive or item.get("status_at"):
            entity_rows.append(h("div", {"class_": "mem-fact sl-research-memory-entity"},
                h("span", {"class_": "mem-date"}, item["kind"]),
                h("span", {"class_": "mem-fx"}, h("b", {}, item["name"]), " → ", item.get("status_at") or "—"),
                h("code", {}, item["entity_id"]) if passive else None, facts if passive else None))
    thread_rows = [rows.thread_row(item, passive=True) for item in threads_value]
    world_rows = []
    for item in world_value:
        rows.text_record(item, ("id", "category", "fact", "t_valid"), nullable=("t_invalid", "created_at"))
        tags = rows.strings(item.get("relevance_tags", []))
        world_rows.append(h("div", {"class_": "sl-research-memory-fact"}, h("p", {"class_": "sl-research-prose"}, item["fact"]),
            rows.fields((("id", item["id"]), (t("type_h"), item["category"]),
                         (t("rm_valid_from"), item["t_valid"]), (t("rm_valid_until"), item.get("t_invalid")),
                         (t("rc_created_at"), item.get("created_at")))), h("ul", {}, [h("li", {}, tag) for tag in tags])))
    return h("div", {"class_": "mem-pane sl-research-memory-state"},
        h("div", {"class_": "mem-pane-h"}, t("state_at", date=value["as_of"])),
        h("p", {"class_": "sl-research-meta"}, value["persona_id"]) if passive else None,
        fragment(entity_rows) if entity_rows else h("p", {"class_": "muted small"}, t("nothing_valid")),
        h("p", {"class_": "muted small"}, t("open_threads_count", n=len(threads_value))),
        h("p", {"class_": "sl-research-meta"}, t("rm_threads_at")) if passive and threads_value else None,
        thread_rows if passive else None,
        h("div", {}, h("h3", {}, t("rm_world")), world_rows) if passive and world_rows else None)


def state_at(value):
    body = state_content(value, passive=True)
    state = "ready" if any(value[key] for key in ("entities", "open_threads", "world_context")) else "empty"
    return _card(t("memory"), body), state


def timeline(value):
    h, _, _ = _kit()
    rows.text_record(value, ("persona_id",), optional=("note",), nullable=("start", "end"))
    facts = rows.records(value.get("facts"))
    events = rows.records(value.get("events"))
    for key, items in (("facts_total", facts), ("events_total", events)):
        if rows.number(value.get(key), count=True) < len(items):
            raise ValueError("Native memory total cannot be less than supplied rows")
    event_rows = []
    for event in events:
        rows.text_record(event, ("timestamp", "task", "event_type"))
        event_rows.append(h("div", {"class_": "sl-research-memory-event"},
                           h("p", {"class_": "sl-research-meta"}, event["timestamp"], " · ", event["event_type"]),
                           h("p", {"class_": "sl-research-prose"}, event["task"])))
    return _card(t("rm_timeline"), h("div", {"class_": "sl-research-memory-timeline"},
        rows.fields(((t("persona"), value["persona_id"]), (t("rm_start"), value.get("start")),
                     (t("rm_end"), value.get("end")), (t("rm_facts_total"), value["facts_total"]),
                     (t("rm_events_total"), value["events_total"]))),
        h("p", {"class_": "sl-research-meta"}, value["note"]) if value.get("note") else None,
        h("h3", {}, t("rm_facts")), [rows.fact_row(item, passive=True) for item in facts],
        h("h3", {}, t("rmo_events")), event_rows)), "ready" if facts or events else "empty"


def threads(value):
    return _list([rows.thread_row(item, passive=True) for item in rows.records(value)])


def recall_content(value, *, passive=False):
    h, fragment, _ = _kit()
    rows.text_record(value, ("persona_id", "query"), nullable=("as_of",))
    if type(value.get("semantic_enabled")) is not bool or type(value.get("k")) is not int:
        raise ValueError("Expected native recall mode and requested count")
    hits = [rows.recall_row(hit, passive=passive) for hit in rows.records(value.get("hits"))]
    mismatch = value.get("embedding_space_mismatch")
    mismatch_body = None
    if mismatch is not None:
        rows.text_record(mismatch, ("note",))
        rows.number(mismatch.get("skipped"), count=True)
        mismatch_body = fragment(rows.fields(((t("rm_vectors_skipped"), mismatch["skipped"]),)),
                                 h("p", {"class_": "sl-research-meta"}, mismatch["note"]))
    return h("div", {"class_": "mem-pane sl-research-memory-recall"},
        h("div", {"class_": "mem-pane-h"}, t("recall")),
        rows.fields(((t("persona"), value["persona_id"]), (t("recall"), value["query"]),
                     (t("rc_recorded_as_of", at=value.get("as_of") or "—"), value.get("as_of")),
                     (t("rm_semantic_enabled"), value["semantic_enabled"]),
                     (t("rm_requested_hits"), value["k"]))) if passive else None,
        fragment(hits) if hits else h("p", {"class_": "muted small"}, t("nothing")),
        mismatch_body if passive else None)


def recall(value):
    body = recall_content(value, passive=True)
    return _card(t("memory"), body), "ready" if value["hits"] else "empty"


def document(value):
    h, _, _ = _kit()
    rows.text_record(value, ("persona_id", "content"))
    return (_card(t("rm_document"), h("p", {"class_": "sl-research-meta"}, value["persona_id"]),
                  h("div", {"class_": "sl-research-memory-document"}, note_content({"text": value["content"]}))),
            "ready" if value["content"] else "empty")


def exported(value):
    h, _, _ = _kit()
    rows.text_record(value, ("persona_id", "path"))
    rows.number(value.get("bytes"), count=True)
    return _card(t("rm_export"), rows.fields(((t("persona"), value["persona_id"]),
                 (t("rm_path"), value["path"]), (t("rm_bytes"), value["bytes"]))),
                 h("p", {"class_": "sl-research-meta"}, t("rm_export_notice"))), "ready"

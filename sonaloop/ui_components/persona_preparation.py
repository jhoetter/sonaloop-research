"""Supplied Persona readiness, immutable contexts and durable build progress."""
from __future__ import annotations

from .library import _kit, collection
from . import persona_preparation_rows as rows
from .persona_preparation_rows import readiness_content, capabilities_content
from .projects_rows import t, disclosure


def _card(title, *body):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-persona-preparation"}, h("h2", {}, title), *body)


def readiness(value):
    h, _, _ = _kit()
    body = readiness_content(value, passive=True)
    critic = value["critic"]
    return _card(t("rpp_preparation"), body,
        h("p", {"class_": "sl-research-meta"}, t("rpp_structural_notice")),
        rows.fields((("next_action", value["next_action"]),)),
        rows.text_list(t("rpp_gaps"), value["gaps"]),
        disclosure(t("rpx_record_details"),
        rows.fields([(key, value[key]) for key in ("persona_id", "level", "score", "memory_level")]),
        rows.fields(value["counts"].items()), rows.section(t("rpp_dimensions"), rows.fields(value["dimensions"].items())),
        rows.section(t("rpp_critic"), rows.fields((("green", critic["green"]), ("created_at", critic["created_at"]))),
                     rows.text_list("low_dimensions", critic["low_dimensions"])) if critic is not None
        else h("p", {"class_": "sl-research-meta"}, t("rpp_no_critic")))), "ready"


def _refs(value):
    from ..web._render import render_ref
    h, _, raw = _kit()
    items = []
    for ref in rows.rows(value):
        rows.texts(ref, ("kind", "id"), ("quote", "text", "anchor", "role"))
        if "score" in ref:
            rows.number(ref["score"])
        items.append(h("li", {}, raw(render_ref(ref, passive=True)),
            rows.fields((("score", ref["score"]),)) if "score" in ref else None))
    return h("ul", {}, items)


def _grounding(value):
    h, _, _ = _kit()
    items = []
    for hit in rows.rows(value):
        rows.texts(hit, ("id", "corpus_id", "text"), ("source", "created_at"))
        rows.number(hit.get("score"))
        if "idx" in hit:
            rows.count(hit["idx"])
        items.append(h("article", {"class_": "sl-research-card"},
            h("p", {"class_": "sl-research-prose"}, hit["text"]), rows.fields([(key, hit[key])
                for key in ("id", "corpus_id", "idx", "source", "created_at", "score") if key in hit])))
    return rows.section(t("rpp_grounding"), items)


def task_readiness(value):
    from .memory import recall_content
    h, _, _ = _kit()
    rows.identity(value, "persona_id")
    rows.texts(value, ("level", "next_action"))
    if value["level"] not in ("ready", "limited", "not_ready"):
        raise ValueError("Expected native task-readiness level")
    rows.nullable(value, ("project_id", "as_of"))
    rows.flags(value, ("ready", "project_cohort_member"))
    rows.counts(value.get("task_signals"), ("memory_hits", "grounding_hits"))
    capability = value.get("capability")
    rows.nullable(capability, ("required",)); rows.flags(capability, ("ok",))
    return _card(t("rpp_task"),
        rows.fields([(key, value[key]) for key in ("level", "ready", "next_action")]),
        h("p", {"class_": "sl-research-meta"}, t("rpp_structural_notice")),
        rows.fields(value["task_signals"].items()), rows.text_list(t("rpp_limits"), value.get("limitations")),
        disclosure(t("rpx_record_details"),
        rows.fields([(key, value[key]) for key in ("persona_id", "project_id", "as_of", "project_cohort_member")]),
        readiness(value.get("global_readiness"))[0],
        rows.fields((("required_capability", capability["required"]), ("capability_ok", capability["ok"]))),
        capabilities_content(capability.get("profile"), passive=True),
        rows.section(t("rpp_refs"), _refs(value.get("refs"))),
        recall_content(value.get("recall"), passive=True), _grounding(value.get("grounding_hits")))), "ready"


_SNAPSHOT_META = ("id", "persona_id", "persona_version", "project_id", "as_of", "memory_cutoff",
                  "required_capability", "context_sha256", "created_at")


def _snapshot_meta(value):
    rows.identity(value, "id"); rows.identity(value, "persona_id")
    rows.texts(value, ("context_sha256", "created_at"))
    rows.nullable(value, ("persona_version", "project_id", "as_of", "memory_cutoff", "required_capability"))
    digest = value["context_sha256"]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Expected native context hash")
    return rows.fields([(key, value[key]) for key in _SNAPSHOT_META])


def snapshot(value):
    h, _, _ = _kit()
    meta = _snapshot_meta(value)
    rows.texts(value, ("schema", "task", "embedding_space", "agent_context", "soul_path"))
    if value["schema"] != "sonaloop.persona_context_snapshot.v1":
        raise ValueError("Expected native immutable Persona context")
    task_body = task_readiness(value.get("readiness"))[0]
    return _card(t("rpp_snapshot"), rows.fields((("task", value["task"]), ("level", value["readiness"]["level"]))),
        h("p", {"class_": "sl-research-meta"}, t("rpp_snapshot_notice")),
        disclosure(t("rpx_record_details"), meta,
        rows.fields([(key, value[key]) for key in ("schema", "embedding_space", "soul_path")]),
        rows.text_list("recent_event_ids", value.get("recent_event_ids")),
        rows.section(t("rpp_refs"), _refs(value.get("loaded_refs"))), task_body),
        disclosure(t("rpp_context"), h("div", {"class_": "sl-research-prose"}, value["agent_context"]))), "ready"


def snapshots(value):
    cards = []
    for item in rows.rows(value):
        meta = _snapshot_meta(item)
        rows.nullable(item, ("readiness_level",))
        cards.append(_card(t("rpp_snapshot"), rows.fields((("created_at", item["created_at"]),
            ("readiness_level", item["readiness_level"]))), disclosure(t("rpx_record_details"), meta)))
    return collection(cards, empty=t("rpp_empty_snapshots")), "ready" if cards else "empty"


def build(value):
    h, _, _ = _kit()
    rows.identity(value, "build_id"); rows.identity(value, "persona_id")
    rows.texts(value, ("schema", "operation_id", "status", "created_at", "updated_at"), ("completed_at",))
    if value["schema"] != "sonaloop.persona_build.v1" or value["status"] not in ("active", "complete"):
        raise ValueError("Expected native Persona build state")
    rows.count(value.get("cursor"))
    window = value.get("window")
    rows.texts(window, ("start", "end")); rows.counts(window, ("days",))
    journal = []
    for entry in rows.rows(value.get("journal")):
        rows.count(entry.get("cursor")); rows.texts(entry, ("dispatch_key", "kind", "tool", "at"))
        # The native dispatch digest is an identity, not an execution credential.
        journal.append(h("li", {}, rows.fields([(key, entry[key]) for key in ("cursor", "kind", "tool", "at", "dispatch_key")])))
    stage = None
    if "dispatch" in value:
        dispatch = value["dispatch"]
        rows.texts(dispatch, ("kind", "tool", "purpose"), ("blocking_reason",))
        if "prior_failed" in dispatch:
            rows.flags(dispatch, ("prior_failed",))
        # Deliberate allowlist: params, grants and dispatch tokens never become
        # visible or executable. The complete original MCP value is untouched.
        stage = rows.section(t("rpp_stage"), rows.fields([(key, dispatch[key]) for key in
            ("kind", "purpose", "blocking_reason", "prior_failed") if key in dispatch]),
            rows.text_list(t("rpp_gaps"), dispatch["gaps"]) if "gaps" in dispatch else None)
    if "created" in value:
        rows.flags(value, ("created",))
    return _card(t("rpp_build"), h("p", {"class_": "sl-research-meta"}, t("rpp_build_notice")),
        rows.fields([(key, value[key]) for key in ("status", "cursor", "created") if key in value]), stage,
        disclosure(t("rpx_record_details"),
        rows.fields([(key, value[key]) for key in ("build_id", "persona_id", "operation_id", "schema", "created_at", "updated_at", "completed_at") if key in value]),
        rows.fields([(key, window[key]) for key in ("start", "end", "days")]),
        readiness(value["readiness"])[0] if "readiness" in value else
        h("p", {"class_": "sl-research-meta"}, t("rpp_no_readiness"))),
        disclosure(t("rpp_journal"), h("ol", {}, journal))), "ready"


def builds(value):
    cards = [build(item)[0] for item in rows.rows(value)]
    return collection(cards, empty=t("rpp_empty_builds")), "ready" if cards else "empty"

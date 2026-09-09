"""Native project results shared with the product header and lineage inspector."""
from __future__ import annotations

from .library import _kit, collection
from . import projects_rows as rows
from .projects_rows import project_body, project_heading, lineage_content, icon_content, t


def _card(title, *body):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-project"}, h("h2", {}, title), *body)


def _project(value):
    rows.identity(value, "id")
    rows.texts(value, ("title", "goal", "slug", "status", "created_at", "updated_at"),
        ("description", "workflow_trace_id", "operation_id", "operation_state", "governance_contract", "url",
         "supersedes_project_id", "superseded_by_project_id"))
    if "methodology" in value and value["methodology"] is not None and type(value["methodology"]) is not str:
        raise ValueError("Expected native methodology text or null")
    rows.strings(value.get("persona_ids"))


def started(value):
    h, _, _ = _kit()
    _project(value)
    warnings = rows.strings(value.get("warnings", []))
    if "idempotent_replay" in value and type(value["idempotent_replay"]) is not bool:
        raise ValueError("Expected native project replay flag")
    return _card(t("rpj_started"), project_body(value, level="h3", description=True, passive=True),
        h("p", {"class_": "sl-research-meta"}, t("rpj_start_notice")),
        rows.fields(((t("rpj_replay"), value["idempotent_replay"]),)) if "idempotent_replay" in value else None,
        h("div", {}, h("h3", {}, t("rpj_warnings")), h("ul", {}, [h("li", {}, warning) for warning in warnings]))
        if warnings else None,
        h("details", {}, h("summary", {}, t("rpj_icon")), icon_content(value["icon"])) if "icon" in value else None), "ready"


def queried(value):
    h, _, _ = _kit()
    rows.record(value)
    if type(value.get("substrate_version")) is not int or value["substrate_version"] != 1:
        raise ValueError("Expected native project substrate version 1")
    for key in ("total", "limit", "offset"):
        rows.count(value.get(key))
    if value["limit"] < 1 or value["limit"] > 200:
        raise ValueError("Expected native project page limit")
    if "next_offset" not in value:
        raise ValueError("Expected native project page continuation")
    if value["next_offset"] is not None:
        rows.count(value["next_offset"])
    if not isinstance(value.get("items"), list):
        raise ValueError("Expected native project page rows")
    cards = []
    for item in value["items"]:
        _project(item)
        for key in ("councils", "artifacts", "assets"):
            rows.count(item.get(key))
        cards.append(h("article", {"class_": "sl-research-card sl-research-project"},
            project_body(item, level="h2", passive=True),
            rows.fields(((t("councils"), item["councils"]), (t("artifacts"), item["artifacts"]),
                         (t("assets_h"), item["assets"])))))
    if len(cards) > value["limit"] or len(cards) > max(0, value["total"] - value["offset"]):
        raise ValueError("Native project page counts cannot be less than supplied rows")
    return h("div", {}, h("p", {"class_": "sl-research-page"},
        t("rpj_query_page", offset=value["offset"], shown=len(cards), total=value["total"])),
        rows.fields((("limit", value["limit"]), ("next_offset", value["next_offset"]))),
        collection(cards, empty=t("no_projects"))), "ready" if cards else "empty"


def _preserved(value):
    rows.identity(value)
    rows.identity(value, "operation_id")
    if value.get("evidence_deleted") is not False or type(value.get("idempotent")) is not bool:
        raise ValueError("Expected native non-destructive project receipt")
    return rows.fields((("project_id", value["project_id"]), (t("rpj_operation"), value["operation_id"]),
                        (t("rpj_replay"), value["idempotent"])))


def superseded(value):
    h, _, _ = _kit()
    receipt = _preserved(value)
    rows.identity(value, "supersedes_project_id")
    rows.identity(value, "reason")
    if value.get("schema") != "sonaloop.project_lineage.v1" or value["project_id"] == value["supersedes_project_id"]:
        raise ValueError("Expected native directed project lineage receipt")
    return _card(t("rpj_superseded"), receipt, lineage_content(value),
        rows.fields(((t("rpj_reason"), value["reason"]),)),
        h("p", {"class_": "sl-research-meta"}, t("rpj_preserved"))), "ready"


def archived(value):
    receipt = _preserved(value)
    if value.get("status") != "archived":
        raise ValueError("Expected native archived project receipt")
    return _card(t("rpj_archived"), receipt, rows.archive_notice(value)), "ready"


def deleted(value):
    h, _, _ = _kit()
    rows.identity(value)
    counters = rows.record(value.get("deleted"))
    for key, number in counters.items():
        if type(key) is not str or not key:
            raise ValueError("Expected native deletion table name")
        rows.count(number)
    if counters.get("research_projects", 0) > 1:
        raise ValueError("Expected at most one deleted project container")
    return _card(t("rpj_deletion"), rows.fields((("project_id", value["project_id"]),)),
        h("p", {}, t("rpj_deleted") if counters.get("research_projects") == 1 else t("rpj_no_delete")),
        h("h3", {}, t("rpj_deleted_rows")), rows.fields(counters.items())), "ready"


def icon(value):
    rows.identity(value)
    return _card(t("rpj_icon"), rows.fields((("project_id", value["project_id"]),)),
                 icon_content(value.get("icon"))), "ready"

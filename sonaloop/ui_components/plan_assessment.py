"""Supplied computed Assessment and Markdown, shared by the Plan inspector/MCP.

The native service owns reads and computation. This presentation neither
evaluates gates nor renders a Health status or a fabricated export file.
"""
from __future__ import annotations

from copy import deepcopy

from . import plan_assessment_rows as rows
from .library import _kit, note_content
from .projects_rows import disclosure, fields, t

public_schema = rows.public_schema


def assessment_view(value):
    if type(value) is not dict or type(value.get("coverage")) is not dict:
        raise ValueError("Expected native Plan assessment")
    if type(value["coverage"].get("evidence_by_kind")) is not dict or type(value.get("tasks_by_bucket")) is not dict:
        raise ValueError("Expected native Plan assessment counts")
    result = deepcopy(value)
    result["coverage"]["evidence_by_kind"] = [{"kind": key, "count": count}
        for key, count in result["coverage"]["evidence_by_kind"].items()]
    buckets = []
    for bucket, counts in result["tasks_by_bucket"].items():
        if type(counts) is not dict or set(counts) != {"done", "total"}:
            raise ValueError("Expected native Plan assessment bucket counts")
        buckets.append({"bucket": bucket, **counts})
    result["tasks_by_bucket"] = buckets
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": "assessment", "value": result})


def document_view(value):
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": "document", "value": deepcopy(value)})


def assessment_content(value):
    """Supplied guidance first; exact detailed computed fields stay inspectable."""
    rows.check(value, rows.ASSESSMENT)
    h, fragment, _ = _kit()
    gates = [rows.section(gate["title"], rows.texts(gate["unmet"]),
        disclosure(t("rpx_record_details"), fields((("task", gate["task"]),)))) for gate in value["open_gates"]]
    return h("div", {"class_": "sl-research-plan-assessment"}, rows.prose(value["goal"]),
        fields(((t("rpa_recommendation"), value["recommendation"]),)), rows.prose(t("rpa_notice")),
        disclosure(t("rpa_completion"), rows.selected(value, ("complete", "tasks_complete"))),
        rows.section(t("rpa_gaps"), rows.texts(value["gaps"])),
        rows.section(t("rpa_ready"), rows.texts(value["ready"])),
        disclosure(t("rpa_open_gates"), fragment(gates) if gates else rows.prose(t("rpa_no_entries"))),
        disclosure(t("rpa_open_questions"), rows.texts(value["open_questions"])), rows.assessment_details(value))


def document_content(markdown):
    """The exact supplied export through the existing escaped Product Markdown body."""
    rows.check({"markdown": markdown}, rows.DOCUMENT)
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-plan-document"}, rows.prose(t("rpa_document_notice")),
        note_content({"text": markdown}) if markdown else rows.prose(t("rpa_no_entries")),
        disclosure(t("rpa_source"), h("pre", {}, markdown)))


def render_view(value):
    rows.validate_view(value)
    h, _, _ = _kit()
    assessment = value["view"] == "assessment"
    body = assessment_content(value["value"]) if assessment else document_content(value["value"]["markdown"])
    title = t("rpa_title") if assessment else t("rpa_document")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, title), body), (
        "ready" if assessment or value["value"]["markdown"] else "empty")


def assessment(value):
    return render_view(assessment_view(value))


def document(value):
    return render_view(document_view(value))

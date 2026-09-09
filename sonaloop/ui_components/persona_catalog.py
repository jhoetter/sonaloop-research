"""Passive native catalog browse, recommendation, status and import outcomes."""
from __future__ import annotations

from . import persona_catalog_rows as rows
from .library import _kit, collection
from .projects_rows import record, texts, strings, count, fields, disclosure, t


def _card(label, *content):
    return _kit()[0]("article", {"class_": "sl-research-card"}, _kit()[0]("h2", {}, label), *content)


def _notes(value):
    texts(value, optional=("note", "hint"))
    return _kit()[1](rows.text_list(value["notes"]) if "notes" in value else None,
        disclosure(t("rpx_record_details"),
            _kit()[1]([rows.prose(value[key]) for key in ("note", "hint") if key in value]))
            if any(key in value for key in ("note", "hint")) else None)


def search(value):
    record(value)
    texts(value, ("source",), ("next_cursor",))
    count(value.get("total"))
    if type(value.get("has_more")) is not bool or "facet_summary" not in value:
        raise ValueError("Expected native catalog page")
    if "limit" in value:
        count(value["limit"])
    summary = None
    if value["facet_summary"] is not None:
        record(value["facet_summary"])
        summary = disclosure(t("rcat_coverage"), _kit()[1]([
            rows.section(key, rows.counts(counts)) for key, counts in value["facet_summary"].items()]))
    metadata = fields([(key, value[key]) for key in ("source", "limit", "next_cursor") if key in value])
    if "manifest" in value:
        manifest = record(value["manifest"])
        rows.nullable_texts(manifest, ("generated_at",))
        if manifest.get("schema_version") is not None:
            count(manifest["schema_version"])
        metadata = _kit()[1](metadata, fields([(key, manifest[key]) for key in
            ("generated_at", "schema_version") if key in manifest]))
    items = rows.records(value.get("items"))
    return _card(t("catalog_h"), rows.prose(t("rcat_source_notice")),
        collection([rows.catalog_row(item, passive=True) for item in items], empty=t("catalog_empty"),
                   total=value["total"], has_more=value["has_more"]), summary,
        _notes(value), disclosure(t("rpx_record_details"), metadata)), "ready" if items else "empty"


def recommendations(value):
    record(value)
    if "skipped" in value:
        if value["skipped"] is not True:
            raise ValueError("Unknown native catalog recommendation boundary")
        texts(value, ("note",))
        return _card(t("rcat_skipped_recommendation"), rows.prose(value["note"])), "ready"
    spec = record(value.get("spec"))
    strings(spec.get("keywords"))
    count(spec.get("n"))
    if spec.get("min_coverage") is not None and type(spec["min_coverage"]) is not int:
        raise ValueError("Expected supplied catalog coverage request")
    spec_body = _kit()[1](rows.section("keywords", rows.text_list(spec["keywords"])),
        rows.facet_values(spec.get("facets")), fields([(key, spec[key]) for key in ("n", "min_coverage") if key in spec]))
    items = rows.records(value.get("personas"))
    texts(value, ("pull_command",))
    return _card(t("rcat_recommendations"), rows.prose(t("rcat_recommendation_notice")),
        collection([rows.recommendation_row(item) for item in items], empty=t("rcat_no_entries")),
        disclosure(t("rcat_coverage"), rows.facet_values(value.get("coverage"))),
        rows.section(t("rcat_warnings"), rows.text_list(value.get("warnings"))),
        disclosure(t("rcat_spec"), spec_body, rows.prose(value["pull_command"]))), "ready" if items else "empty"


def status(value):
    record(value)
    items = rows.records(value.get("items"))
    if "source" not in value:
        raise ValueError("Expected catalog status source")
    rows.nullable_texts(value, ("source",))
    return _card(t("rcat_status"),
        collection([rows.status_row(item) for item in items], empty=t("rcat_no_entries")),
        rows.section(t("rcat_reported_counts"), rows.counts(value.get("counts"))), _notes(value),
        disclosure(t("rpx_record_details"), fields((("source", value["source"]),)))), "ready" if items else "empty"


def pulled(value):
    record(value)
    strings(value.get("personas"))
    landed = rows.records(value.get("landed"))
    texts(value, optional=("source", "repo", "ref", "in_dir", "embeddings"))
    return _card(t("rcat_pull"), rows.prose(t("rcat_pull_notice")),
        rows.section(t("rcat_landed"), collection([rows.landed_row(item) for item in landed], empty=t("rcat_no_entries"))),
        rows.section(t("rcat_skipped_local"), rows.skipped_rows(value["skipped_locally_modified"]))
            if "skipped_locally_modified" in value else None,
        rows.section(t("rcat_skipped_premium"), rows.skipped_rows(value["skipped_premium"]))
            if "skipped_premium" in value else None,
        disclosure(t("rcat_import_counts"), rows.counts(value["counts"])) if "counts" in value else None,
        _notes(value), disclosure(t("rpx_record_details"),
            fields([(key, value[key]) for key in ("source", "repo", "ref", "in_dir", "embeddings") if key in value]),
            rows.section("personas", rows.text_list(value["personas"])))), "ready"

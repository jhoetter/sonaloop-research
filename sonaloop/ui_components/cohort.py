"""Supplied cohort diversity, critique, memory depth, coverage and selection."""
from __future__ import annotations

from . import cohort_rows as r
from .cohort_rows import selection_content


def diversity(value):
    r.identity(value, "id")
    r.texts(value, ("kind", "status", "detail", "created_at"))
    r.flags(value, "green"); r.count(value.get("persona_count"))
    if value["kind"] != "cohort_diversity" or value["status"] not in ("na", "green", "warn", "red"):
        raise ValueError("Expected native diversity assessment")
    metrics = r.record(value.get("metrics"))
    metric_body = None
    if metrics:
        for key in ("mean_pairwise_similarity", "max_segment_share", "distinct_segment_ratio"):
            r.number(metrics.get(key))
        r.count(metrics.get("near_duplicate_pairs"))
        metric_body = r.section(r.t("rcg_measurements"), r.fields((key, metrics[key]) for key in (
            "mean_pairwise_similarity", "near_duplicate_pairs", "max_segment_share", "distinct_segment_ratio")),
            r.section(r.t("rcg_segments"), r.counts(metrics.get("segment_distribution"))))
    elif value["status"] != "na":
        raise ValueError("Expected native diversity measurements")
    pairs = []
    for pair in r.records(value.get("duplicate_pairs")):
        r.texts(pair, ("a", "a_id", "b", "b_id")); r.number(pair.get("similarity"))
        pairs.append(r.card(r.t("rcg_duplicate_pair"), r.fields((key, pair[key]) for key in
            ("a", "b", "similarity")), r.disclosure(r.t("rpx_record_details"),
                r.fields((("a_id", pair["a_id"]), ("b_id", pair["b_id"]))))))
    return r.card(r.t("rcg_diversity"), r.fields((key, value[key]) for key in ("status", "green", "persona_count")),
        r.note(value["detail"]), r.note(r.t("rcg_structural_notice")),
        r.section(r.t("rcg_duplicate_pairs"), pairs), r.disclosure(r.t("rpx_record_details"),
            r.fields((key, value[key]) for key in ("id", "kind", "created_at")), metric_body,
            r.text_list(r.t("personas"), value["personas_evaluated"]) if "personas_evaluated" in value else None)), "ready"


def critic(value):
    r.identity(value, "id"); r.texts(value, ("kind", "cohort_note", "created_at"))
    r.nullable(value, "persona_id"); r.flags(value, "green")
    if value["kind"] != "cohort_critic":
        raise ValueError("Expected native cohort critic")
    outliers = []
    for item in r.records(value.get("outliers")):
        r.identity(item, "persona_id"); r.texts(item, ("persona_name", "reason", "dimension"))
        r.count(item.get("severity"))
        if not 1 <= item["severity"] <= 5:
            raise ValueError("Expected native critic severity 1..5")
        outliers.append(r.card(item["persona_name"] or item["persona_id"], r.note(item["reason"]),
            r.fields((key, item[key]) for key in ("dimension", "severity", "persona_id"))))
    return r.card(r.t("rcg_critic"), r.fields((("green", value["green"]),)), r.note(value["cohort_note"]),
        r.note(r.t("rcg_authored_notice")), r.section(r.t("rcg_outliers"), outliers),
        r.disclosure(r.t("rpx_record_details"), r.fields((key, value[key]) for key in
            ("id", "kind", "persona_id", "created_at")))), "ready"


def depth(value):
    r.texts(value, ("hint",))
    for key in ("personas", "facts", "events"):
        r.count(value.get(key))
    r.number(value.get("avg_per_persona"))
    return r.card(r.t("rcg_depth"), r.fields((key, value[key]) for key in
        ("personas", "facts", "events", "avg_per_persona")), r.note(value["hint"]),
        r.note(r.t("rcg_depth_notice"))), "ready"


def coverage(value):
    r.identity(value, "project_id"); r.texts(value, ("schema",)); r.nullable(value, "job")
    if value["schema"] != "coverage_assessment":
        raise ValueError("Expected native coverage assessment")
    r.count(value.get("panel_size"))
    indicator = value.get("indicator")
    r.texts(indicator, ("level",)); r.count(indicator.get("score")); r.count(indicator.get("gap_count"))
    if indicator["level"] not in ("thin", "ok", "strong"):
        raise ValueError("Expected native coverage level")
    dimensions = []
    for item in r.records(value.get("dimensions")):
        r.texts(item, ("dimension",)); r.nullable(item, "dominant")
        for key in ("distinct", "assessed", "not_assessable"):
            r.count(item.get(key))
        r.number(item.get("dominant_share")); r.flags(item, "over_concentration", "no_signal", "thin")
        dimensions.append(r.card(item["dimension"], r.counts(item.get("counts")), r.fields((key, item[key])
            for key in ("distinct", "assessed", "not_assessable", "dominant", "dominant_share", "over_concentration", "no_signal", "thin"))))
    gaps = []
    for item in r.records(value.get("gaps")):
        r.texts(item, ("kind", "reason"), ("axis",)); r.nullable(item, "dimension")
        gaps.append(r.card(item["kind"], r.note(item["reason"]), r.fields((key, item[key])
            for key in ("dimension", "axis") if key in item)))
    recommendations = []
    for item in r.records(value.get("recommendations")):
        r.texts(item, ("description",)); r.nullable(item, "dimension", "dimension_label", "avoid_value")
        recommendations.append(r.card(item["dimension_label"] or r.t("rcg_recommendations"),
            r.note(item["description"]), r.fields((key, item[key]) for key in ("dimension", "avoid_value"))))
    if "declared_coverage" not in value:
        raise ValueError("Expected explicit declared coverage or null")
    declared = value["declared_coverage"]
    declared_body = r.note(r.t("rcg_no_declared_coverage"))
    if declared is not None:
        r.texts(declared, ("job_id", "job_name", "note"))
        if declared.get("min_personas") is not None:
            r.count(declared["min_personas"])
        declared_body = r.section(r.t("rcg_declared_coverage"), r.fields((key, declared.get(key))
            for key in ("job_id", "job_name", "min_personas")), r.note(declared["note"]),
            r.text_list(r.t("rcg_declared_axes"), declared.get("persona_axes")))
    return r.card(r.t("rcg_coverage"), r.fields((("panel_size", value["panel_size"]),
        ("level", indicator["level"]), ("score", indicator["score"]), ("gap_count", indicator["gap_count"]))),
        r.text_list(r.t("rcg_reasons"), indicator.get("reasons")), r.note(r.t("rcg_structural_notice")),
        r.section(r.t("rcg_gaps"), gaps), r.disclosure(r.t("rcg_dimensions"), dimensions),
        r.disclosure(r.t("rcg_recommendations"), recommendations,
            r.note(value["catalog_hint"]) if "catalog_hint" in value else None),
        r.disclosure(r.t("rpx_record_details"), r.fields((("schema", value["schema"]),
            ("project_id", value["project_id"]), ("job", value["job"]))), declared_body)), "ready"


def selection(value):
    r.identity(value, "project_id"); r.texts(value, ("schema", "selection_rationale"))
    if value["schema"] != "sonaloop.reaction_cohort_selection.v1":
        raise ValueError("Expected native Reaction Test cohort selection")
    r.count(value.get("minimum_personas")); r.flags(value, "idempotent_replay", "gate_passed")
    next_step = value.get("next")
    r.texts(next_step, ("note",))
    return r.card(r.t("rcg_selection"), selection_content(value.get("persona_ids"), value["selection_rationale"]),
        r.fields((key, value[key]) for key in ("minimum_personas", "idempotent_replay", "gate_passed")),
        r.dispatch_status(value.get("dispatch")), r.note(next_step["note"]), r.note(r.t("rcg_selection_notice")),
        r.disclosure(r.t("rpx_record_details"), r.fields((("schema", value["schema"]),
            ("project_id", value["project_id"]))))), "ready"

"""Shared compact Product cohort gate body; prepared context stays outside it."""
from __future__ import annotations

from .library import _kit
from . import cohort_rows as r
from .cohort_rows import t


def _cohort_origin_text(value: str) -> str:
    key = str(value or "unknown")
    labels = {
        "catalog": t("cohort_origin_catalog"),
        "grounded": t("cohort_origin_grounded"),
        "authored": t("cohort_origin_authored"),
        "missing": t("cohort_origin_missing"),
        "unknown": t("cohort_origin_unknown"),
    }
    return labels.get(key, key)


def integrity_content(current, *, prepared, embedded=False, passive=False):
    """Render already supplied status, formatting and row context; never check gates."""
    h, fragment, _ = _kit()
    status, stale = prepared["status"], prepared.get("stale")
    labels = {"pass": t("cohort_status_pass"), "overridden": t("cohort_status_overridden"),
        "needs_deepening": t("cohort_status_needs_deepening"), "needs_reselection": t("cohort_status_needs_reselection"),
        "stale": t("cohort_status_stale")}
    def cls(value):
        if not passive:
            return value
        if value.startswith("sl-integrity sl-integrity--cohort") or value == "sl-integrity-nested":
            return "sl-research-disclosure"
        return "sl-research-cohort-content"
    totals = (current.get("depth") or {}).get("totals") or {}
    lexical_max = prepared.get("lexical_max", 0)
    semantic_max = prepared.get("semantic_max")
    representation = current.get("representation") or {}
    required_work = current.get("required_work") or []
    persona_rows = []
    for index, row in enumerate((current.get("depth") or {}).get("personas") or []):
        if passive and not row.get("exists"):
            persona_rows.append(h("li", {}, row["persona_id"], " · ", t("cohort_origin_missing")))
            continue
        depth = row.get("depth") or {}
        provenance = row.get("source_provenance") or {}
        age_text = prepared["persona_ages"][index]
        persona_rows.append(h(
            "li", {},
            t("cohort_persona_summary", name=row.get("display_name") or row.get("persona_id") or "—",
              items=depth.get("independent_context_items", 0),
              origin=_cohort_origin_text(provenance.get("origin") or "unknown"), age=age_text),
            (" · " + t("cohort_persona_thin") if row.get("thin") else ""),
        ))
    work_rows = [h(
        "li", {}, h("code", {}, row.get("code") or row.get("kind") or "—"),
        (" · " + ", ".join(row.get("tools") or [])) if row.get("tools") else "",
    ) for row in required_work]
    limitation = current.get("override") or {}
    meta = prepared["meta"]
    aria = f'{t("cohort_integrity_h")}: {labels.get(status, status)}. '
    aria += t("cohort_depth_summary", personas=totals.get("personas", 0),
              items=totals.get("independent_context_items", 0), thin=totals.get("thin", 0))
    countervoices = representation.get("countervoice_count", 0)
    countervoice_label = (
        t("cohort_countervoice_one") if countervoices == 1
        else t("cohort_countervoices_n", n=countervoices)
    )

    thin_profiles = totals.get("thin", 0)
    thin_label = (
        t("cohort_no_thin_profiles") if not thin_profiles
        else t("cohort_thin_profile_one") if thin_profiles == 1
        else t("cohort_thin_profiles_n", n=thin_profiles)
    )
    summary = t(
        "cohort_compact_summary",
        personas=totals.get("personas", 0),
        countervoices=countervoice_label,
        thin=thin_label,
    )
    wrapper_class = "sl-integrity sl-integrity--cohort"
    if embedded:
        wrapper_class += " sl-integrity--embedded"
    return h(
        "details", {"class_": cls(wrapper_class), "id": None if passive else "cohort-integrity", "aria-label": None if passive else aria},
        h("summary", {},
          h("span", {"class_": cls("sl-integrity-heading")},
            prepared["icon"],
            h("span", {"class_": cls("sl-integrity-heading-copy")},
              h("strong", {"class_": cls("sl-integrity-title")}, t("cohort_integrity_h")),
              " " if passive else None,
              h("span", {"class_": cls("sl-integrity-summary")}, summary))),
          " " if passive else None,
          h("span", {"class_": cls("sl-integrity-badges")},
            prepared["status_badge"],
            prepared.get("unverified_badge"))),
        h("div", {"class_": cls("sl-integrity-body")},
          h("p", {"class_": cls("sl-integrity-context")},
            t("cohort_integrity_stale_help") if stale else t("cohort_boundary_help")),
        (h("div", {"class_": cls("sl-cohort-required")},
           h("strong", {}, t("cohort_required_work")),
           h("ul", {"class_": cls("sl-integrity-list")}, fragment(*work_rows)))
         if work_rows else None),
        (h("div", {"class_": cls("sl-cohort-limitation")},
           h("strong", {}, t("cohort_override_limitation")), " ", limitation.get("rationale", ""))
         if limitation else None),
          h("details", {"class_": cls("sl-integrity-nested")},
            h("summary", {}, t("cohort_check_details")),
            h("dl", {"class_": cls("sl-integrity-metrics")},
              h("div", {}, h("dt", {}, t("cohort_independent_items")),
                h("dd", {}, str(totals.get("independent_context_items", 0)))),
              h("div", {}, h("dt", {}, t("cohort_lexical_overlap")),
                h("dd", {}, f"{lexical_max:.0%}")),
              h("div", {}, h("dt", {}, t("cohort_semantic_overlap")),
                h("dd", {}, t("cohort_not_calculated") if semantic_max is None
                  else f"{semantic_max:.0%}")),
              h("div", {}, h("dt", {}, t("cohort_policy")),
                h("dd", {"class_": cls("sl-integrity-technical")}, meta)))) if not passive else None,
          h("details", {"class_": cls("sl-integrity-nested")},
            h("summary", {}, t("cohort_persona_basis_n", n=totals.get("personas", 0))),
            h("ul", {"class_": cls("sl-integrity-list")}, fragment(*persona_rows))) if persona_rows or not passive else None,
        ),
    )


def _persona_depth(value):
    r.identity(value, "persona_id"); r.flags(value, "exists", "thin")
    provenance = value.get("source_provenance")
    r.texts(provenance, ("origin",))
    if not value["exists"]:
        return r.card(value["persona_id"], r.fields((("exists", False), ("thin", value["thin"]),
                      ("origin", provenance["origin"]))))
    r.texts(value, ("display_name", "profile_claim_digest", "profile_created_at"))
    r.flags(value, "fresh_profile_at_project_start")
    if value.get("profile_age_hours_at_project_start") is not None:
        r.number(value["profile_age_hours_at_project_start"])
    depth = r.record(value.get("depth"))
    keys = ("facts", "events", "evidence", "independent_facts", "independent_events", "independent_evidence", "independent_context_items")
    for key in keys:
        r.count(depth.get(key))
    sources = []
    for source in r.records(provenance.get("independent_evidence_sources")):
        r.nullable(source, "id", "source_type", "created_at")
        if source.get("age_hours_at_project_start") is not None:
            r.number(source["age_hours_at_project_start"])
        sources.append(r.fields((key, source.get(key)) for key in
            ("id", "source_type", "created_at", "age_hours_at_project_start")))
    event_range = provenance.get("event_range")
    r.texts(event_range, ("oldest", "newest"))
    return r.card(value["display_name"], r.fields((key, value.get(key)) for key in
        ("persona_id", "exists", "thin", "profile_created_at", "profile_age_hours_at_project_start", "fresh_profile_at_project_start", "profile_claim_digest")),
        r.fields((key, depth[key]) for key in keys),
        r.section(t("rcg_post_project"), r.counts(depth.get("post_project_or_stimulus_bound"))),
        r.section(t("rcg_provenance"), r.fields((("origin", provenance["origin"]),)),
            _provenance_fields(r.record(provenance.get("profile"))),
            r.fields(event_range.items()), r.section(t("rcg_sources"), sources)))


def _provenance_fields(value):
    """Named provenance metadata, never a JSON dump or an execution surface."""
    h, fragment, _ = _kit()
    if isinstance(value, dict):
        rows = [fragment(h("dt", {}, key),
            h("dd", {}, _provenance_fields(item))) for key, item in value.items()
            if key not in {"dispatch_token", "execution_grant", "confirmation_token", "approval_token",
                           "access_token", "refresh_token", "preview_token"}]
        return h("dl", {"class_": "sl-research-fields"}, rows) if rows else h("span", {}, t("rcg_no_entries"))
    if isinstance(value, list):
        return h("ul", {}, [h("li", {}, _provenance_fields(item)) for item in value]) if value else h("span", {}, t("rcg_no_entries"))
    if value is None:
        return h("span", {}, "null")
    if type(value) in (int, float):
        r.number(value)
    elif type(value) not in (str, bool):
        raise ValueError("Expected supplied provenance metadata")
    return h("span", {}, str(value).lower() if type(value) is bool else value)


def _leakage(value):
    r.record(value)
    lexical = []
    for item in r.records(value.get("lexical")):
        r.texts(item, ("persona_id", "input_digest", "feature_schema", "algorithm", "matched_stimulus_segment_digest"))
        r.number(item.get("score"))
        for key in ("hypothesis_token_count", "profile_token_count", "shared_token_count", "shared_bigram_count"):
            r.count(item.get(key))
        lexical.append(r.card(item["persona_id"], r.fields((key, item[key]) for key in
            ("score", "hypothesis_token_count", "profile_token_count", "shared_token_count", "shared_bigram_count", "feature_schema", "algorithm", "input_digest", "matched_stimulus_segment_digest")),
            r.text_list(t("rcg_shared_tokens"), item.get("shared_tokens"))))
    semantic = value.get("semantic")
    r.flags(semantic, "provided"); r.texts(semantic, ("schema",), ("feature_version", "model_id"))
    if semantic["schema"] != "sonaloop.semantic_overlap.v1":
        raise ValueError("Expected native semantic overlap schema")
    r.number(semantic.get("threshold"))
    semantic_rows = []
    for item in r.records(semantic.get("scores")):
        r.texts(item, ("persona_id", "input_digest")); r.number(item.get("score"))
        semantic_rows.append(r.fields((key, item[key]) for key in ("persona_id", "input_digest", "score")))
    inputs = r.record(value.get("semantic_inputs"))
    for key, item in inputs.items():
        if type(key) is not str or type(item) is not str:
            raise ValueError("Expected native semantic input identities")
    return r.section(t("rcg_leakage"), r.section(t("cohort_lexical_overlap"), lexical),
        r.section(t("cohort_semantic_overlap"), r.fields((key, semantic[key]) for key in
            ("provided", "schema", "feature_version", "model_id", "threshold") if key in semantic), semantic_rows),
        r.fields(inputs.items()), r.text_list("high_overlap_persona_ids", value.get("high_overlap_persona_ids")),
        r.text_list("circular_persona_ids", value.get("circular_persona_ids")))


def _representation(value):
    r.texts(value, ("schema", "verification_rule")); r.flags(value, "complete", "satisfied")
    if value["schema"] != "sonaloop.cohort_representation.v1":
        raise ValueError("Expected native representation schema")
    r.count(value.get("countervoice_count")); r.count(value.get("required_minimum"))
    declarations = []
    for item in r.records(value.get("declarations")):
        r.texts(item, ("persona_id", "posture", "rationale", "basis_quote", "grounding_status"))
        if "quote_matched_ref" not in item:
            raise ValueError("Expected matched reference or null")
        declarations.append(r.card(item["persona_id"], r.fields((("posture", item["posture"]),
            ("grounding_status", item["grounding_status"]))), r.note(item["rationale"]), r.note(item["basis_quote"]),
            r.section(t("rcg_sources"), r.refs(item.get("evidence_refs"))),
            r.section(t("rcg_matched_ref"), r.refs([item["quote_matched_ref"]]) if item["quote_matched_ref"] is not None else r.note("null")),
            r.section(t("rcg_rejected_refs"), r.refs(item.get("rejected_evidence_refs")))))
    return r.section(t("rcg_representation"), r.fields((key, value[key]) for key in
        ("schema", "complete", "satisfied", "countervoice_count", "required_minimum")), r.note(value["verification_rule"]),
        [r.text_list(key, value.get(key)) for key in ("undeclared_persona_ids", "declared_countervoice_persona_ids",
            "countervoice_persona_ids", "unverified_countervoice_persona_ids", "allowed_counterpostures")], declarations)


def _required_work(value):
    result = []
    for item in r.records(value):
        r.texts(item, ("kind", "code"), ("note",))
        if "minimum" in item:
            r.count(item["minimum"])
        result.append(r.card(item["code"], r.fields((("kind", item["kind"]),)),
            r.note(item["note"]) if "note" in item else None,
            r.fields((("minimum", item["minimum"]),)) if "minimum" in item else None,
            r.counts(item["minimums"]) if "minimums" in item else None,
            [r.text_list(key, item[key]) for key in ("persona_ids", "accepted_postures", "unverified_persona_ids", "tools") if key in item]))
    return r.section(t("cohort_required_work"), result)


def preflight(value):
    h, _, _ = _kit()
    r.identity(value, "id"); r.identity(value, "project_id")
    r.texts(value, ("schema", "policy_version", "status", "raw_status", "evaluated_at", "supersedes"), ("remediation_task_id",))
    if value["schema"] != "sonaloop.cohort_integrity.v1" or value["status"] not in (
            "pass", "needs_deepening", "needs_reselection", "overridden"):
        raise ValueError("Expected native recorded cohort preflight")
    if value["raw_status"] not in ("pass", "needs_deepening", "needs_reselection"):
        raise ValueError("Expected native cohort status before override")
    r.count(value.get("version"))
    thresholds = r.record(value.get("thresholds"))
    for key in ("min_personas", "min_independent_events_per_persona", "min_independent_evidence_per_persona_alternative",
                "min_independent_context_items_per_persona", "max_thin_fraction", "fresh_persona_hours",
                "lexical_overlap_reselection", "semantic_overlap_reselection", "min_countervoices"):
        r.number(thresholds.get(key))
    r.texts(value, ("cohort_ids_digest",))
    r.strings(value.get("cohort_ids"))
    depth = r.record(value.get("depth")); totals = r.record(depth.get("totals"))
    for key in ("personas", "missing", "thin", "facts", "events", "evidence", "independent_context_items"):
        r.count(totals.get(key))
    r.number(totals.get("thin_fraction"))
    personas = [_persona_depth(item) for item in r.records(depth.get("personas"))]
    boundary = r.record(value.get("stimulus_boundary"))
    r.texts(boundary, ("kind", "product_stimulus_digest", "project_goal_description_digest", "effective_hypotheses_digest",
        "product_understanding_id", "independent_target_context", "product_stimulus", "frame_questions_digest",
        "frame_hypotheses_digest", "additional_hypotheses_digest"))
    r.nullable(boundary, "at")
    r.count(boundary.get("frame_questions_count")); r.count(boundary.get("frame_hypotheses_count"))
    r.strings(boundary.get("frame_ids"))
    representation = _representation(value.get("representation"))
    leakage = _leakage(value.get("leakage"))
    work = _required_work(value.get("required_work"))
    override = value.get("override")
    if override is not None:
        r.texts(override, ("rationale", "original_status", "accepted_at"))
    history = []
    for item in r.records(value.get("history", [])):
        r.texts(item, ("id", "status", "raw_status", "evaluated_at", "supersedes")); r.count(item.get("version"))
        history.append(r.fields((key, item[key]) for key in ("id", "version", "status", "raw_status", "evaluated_at", "supersedes")))
    limitations = []
    for item in r.records(value.get("limitations", [])):
        r.texts(item, ("id", "schema", "kind", "cohort_preflight_id", "original_status", "rationale", "created_at"))
        limitations.append(r.card(item["kind"], r.note(item["rationale"]), r.fields((key, item[key])
            for key in ("id", "schema", "cohort_preflight_id", "original_status", "created_at"))))
    if "idempotent_replay" in value:
        r.flags(value, "idempotent_replay")
    prepared = {"status": value["status"], "icon": None, "status_badge": h("span", {}, " · ", value["status"]),
        "meta": None, "persona_ages": [t("cohort_age_unknown") if item.get("profile_age_hours_at_project_start") is None
            else t("rcg_age_exact", n=item["profile_age_hours_at_project_start"]) for item in depth["personas"]]}
    summary = integrity_content(value, prepared=prepared, passive=True)
    return r.card(t("rcg_preflight"), r.fields((("status", value["status"]), ("raw_status", value["raw_status"]),
        ("version", value["version"]), ("evaluated_at", value["evaluated_at"]))), r.note(t("rcg_record_notice")), summary,
        r.disclosure(t("rcg_depth"), r.fields(totals.items()), personas), r.disclosure(t("rcg_representation"), representation),
        r.disclosure(t("rcg_leakage"), leakage), r.disclosure(t("cohort_required_work"), work),
        r.disclosure(t("rpx_record_details"), r.fields((key, value[key]) for key in
            ("id", "project_id", "schema", "policy_version", "supersedes", "cohort_ids_digest", "remediation_task_id", "idempotent_replay") if key in value),
            r.text_list(t("personas"), value["cohort_ids"]), r.section(t("rcg_thresholds"), r.fields(thresholds.items())),
            r.section(t("rcg_boundary"), r.fields((key, item) for key, item in boundary.items() if key != "frame_ids"),
                r.text_list("frame_ids", boundary["frame_ids"])),
            r.fields(override.items()) if override is not None else None,
            r.dispatch_status(value["dispatch"]) if "dispatch" in value else None),
        r.disclosure(t("rcg_history"), history) if "history" in value else None,
        r.disclosure(t("rcg_limitations"), limitations) if "limitations" in value else None), "ready"

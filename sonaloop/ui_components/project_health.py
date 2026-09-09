"""Canonical health presentation; all native projection and I/O stay outside."""
from __future__ import annotations

import math

from .library import _kit
from . import projects_rows as rows
from .projects_rows import t


def action_call(action, *, keep_empty=False):
    args = ", ".join(f"{key}={value!r}" for key, value in (action.get("arguments") or {}).items()
                     if keep_empty or value != "")
    return f"{action.get('tool')}({args})" if action.get("tool") else ""


def attention_text(run_state):
    """The existing product recovery sentence, based only on supplied state."""
    if run_state.get("state") == "waiting" or run_state.get("driver_state") == "waiting_on_preflight":
        gate = str((run_state.get("preflight") or {}).get("gate") or "")
        return (t("health_attention_preflight_product") if gate == "product_understanding"
                else t("health_attention_preflight_selection") if gate == "cohort_selection"
                else t("health_attention_preflight_cohort"))
    if run_state.get("state") == "unverified":
        return t("health_attention_unverified")
    if run_state.get("state") == "expired":
        return t("health_attention_expired")
    if run_state.get("state") == "stalled":
        if run_state.get("driver_state") == "not_started":
            return t("health_attention_not_started")
        if run_state.get("driver_state") == "stopped":
            return t("health_attention_stopped")
        return t("health_attention_stalled")
    return ""


def diagnostics_content(run_state, *, prepared=None, passive=False):
    """Shared product disclosure; prepared copy/link fragments are product-only."""
    h, fragment, _ = _kit()
    prepared = prepared or {}
    unmet = run_state.get("unmet_invariant") or {}
    last = run_state.get("last_successful_operation") or {}
    action = run_state.get("safe_next_action") or {}
    call = action_call(action, keep_empty=passive)
    trace = run_state.get("trace") or {}
    support_ref = str(trace.get("support_ref") or "")
    limitation = str(trace.get("limitation") or "")
    ready_source = run_state.get("next_ready")
    if ready_source is None:
        ready_source = (run_state.get("tasks") or {}).get("next_ready")
    next_ready = [str(step) for step in (ready_source or []) if str(step)]
    project_title = str(run_state.get("title") or "").strip()
    issue_links = prepared.get("issues", {})
    issues = []
    for index, row in enumerate(run_state.get("integrity_findings") or []):
        content = issue_links.get(index, row.get("message") or row.get("code") or "—")
        issues.append(h("li", {"data-integrity-code": row.get("code", "")}, content,
            rows.fields([(key, row[key]) for key in ("code", "severity", "target") if key in row]) if passive else None))
    if not any((unmet, last, action, support_ref, limitation, next_ready, issues)):
        return ""
    action_value = (prepared.get("action", h("code", {}, call)) if call else action.get("reason") or "—")
    trace_value = fragment(h("code", {}, support_ref) if support_ref else None,
        h("span", {"class_": "muted small"}, (" · " if support_ref and limitation else ""),
          t("health_external_limit"), ": ", limitation) if limitation else None)
    summary_attrs = {"aria_label": t("health_diagnostics_for", title=project_title)} if project_title else {}
    return h("details", {"class_": "sl-run-diagnostics" + (" sl-research-health-diagnostics" if passive else ""),
                         "data-run-diagnostics": True},
        h("summary", summary_attrs, t("health_diagnostics")),
        h("p", {"class_": "muted small sl-run-diagnostics-help"}, t("health_diagnostics_help")),
        h("dl", {"class_": "sl-run-diagnostics-grid" + (" sl-research-fields" if passive else "")},
          h("dt", {}, t("health_unmet")), h("dd", {}, unmet.get("message") or t("health_no_issues"),
            rows.fields([(key, unmet[key]) for key in ("code", "severity", "target") if key in unmet]) if passive else None),
          h("dt", {}, t("health_last_success")),
          h("dd", {}, h("code", {}, last.get("key") or last.get("kind") or "—"),
            (f' · {last.get("summary")}' if last.get("summary") else ""),
            rows.fields([(key, last[key]) for key in ("kind", "task_id", "at") if key in last]) if passive else None),
          h("dt", {}, t("health_safe_next")), h("dd", {}, action_value,
            _action_details(action) if passive else None),
          h("dt", {}, t("health_trace")), h("dd", {}, trace_value or "—"),
          fragment(h("dt", {}, t("health_next_ready")),
            h("dd", {}, h("ul", {"class_": "sl-run-diagnostics-tasks"},
              [h("li", {}, h("code", {}, step)) for step in next_ready]))) if next_ready else None,
          fragment(h("dt", {"class_": "sl-run-diagnostics-issues"}, t("health_findings")),
            h("dd", {"class_": "sl-run-diagnostics-issues"}, h("ul", {}, issues))) if issues else None))


def _json(value, depth=0):
    """Only actual JSON arguments can become a literal, non-executable call."""
    if depth > 64:
        raise ValueError("Unsupported nested health argument")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json(item, depth + 1)
        return
    if isinstance(value, dict) and all(type(key) is str for key in value):
        for item in value.values():
            _json(item, depth + 1)
        return
    raise ValueError("Expected native JSON health argument")


def _bools(value, keys):
    rows.record(value)
    if any(type(value.get(key)) is not bool for key in keys):
        raise ValueError("Expected native health boolean")


def _counts(value, keys=None):
    rows.record(value)
    for key in value if keys is None else keys:
        if type(key) is not str:
            raise ValueError("Expected native health count label")
        rows.count(value.get(key))


def _action(value):
    rows.texts(value, ("tool",), ("kind", "reason"))
    rows.record(value.get("arguments"))
    _json(value["arguments"])
    if "required_input_paths" in value:
        rows.strings(value["required_input_paths"])
    if "then" in value:
        _action(value["then"])


def _action_details(value):
    h, fragment, _ = _kit()
    return fragment(h("p", {"class_": "sl-research-meta"}, t("rph_recommendation")),
        rows.fields([(key, value[key]) for key in ("kind", "reason") if key in value]),
        _string_list(t("rph_required_paths"), value["required_input_paths"]) if "required_input_paths" in value else None,
        h("p", {}, t("rph_then"), ": ", h("code", {}, action_call(value["then"], keep_empty=True)))
        if "then" in value else None)


def _string_list(title, values):
    h, _, _ = _kit()
    rows.strings(values)
    return h("div", {}, h("h4", {}, title), h("ul", {}, [h("li", {}, value) for value in values]))


def _section(title, *content):
    h, _, _ = _kit()
    return h("section", {"class_": "sl-research-health-section"}, h("h3", {}, title), *content)


def _native_metadata(value):
    """Escaped ancillary native qualifications, without interpreting authority."""
    h, _, _ = _kit()
    _json(value)
    if isinstance(value, dict):
        return rows.fields((key, _native_metadata(item)) for key, item in value.items()) if value else h("span", {}, "{}")
    if isinstance(value, list):
        return h("ul", {}, [h("li", {}, _native_metadata(item)) for item in value]) if value else h("span", {}, "[]")
    return h("span", {}, "null" if value is None else str(value).lower() if type(value) is bool else value)


def _preflight(value):
    h, _, _ = _kit()
    rows.texts(value, ("state",), ("gate", "kind", "task_id", "code", "message", "status"))
    call = value.get("next_call")
    if "next_call" in value:
        rows.record(call)
    if call:
        _action(call)
    if "action" in value:
        rows.record(value["action"])
        _json(value["action"])
    return _section(t("rph_preflight"), rows.fields([(key, value[key]) for key in
        ("state", "gate", "kind", "task_id", "code", "status") if key in value]),
        h("p", {"class_": "sl-research-prose"}, value["message"]) if "message" in value else None,
        _string_list(t("rph_listed_tools"), value["allowed_tools"]) if "allowed_tools" in value else None,
        h("p", {}, h("code", {}, action_call(call, keep_empty=True))) if call else None,
        _action_details(call) if call else None,
        _section("action", _native_metadata({key: item for key, item in value["action"].items()
            if key not in value or item != value[key]})) if value.get("action") else None)


def _handoff(value):
    rows.record(value)
    boolean_keys = ("exists", "complete", "handed_off", "latest_complete", "lead_missing", "latest_stale")
    _bools(value, boolean_keys)
    rows.texts(value, ("latest_report_id",))
    body = [rows.fields([(key, value[key]) for key in (*boolean_keys, "latest_report_id")])]
    for key in ("completed_report_ids", "incomplete_report_ids", "stale_report_ids", "required_source_ids"):
        body.append(_string_list(key, value.get(key)))
    if not isinstance(value.get("reports"), list):
        raise ValueError("Expected native report handoff rows")
    for report in value["reports"]:
        rows.texts(report, ("report_id", "status"))
        flags = ("complete", "body_empty", "lead_missing", "content_complete")
        _bools(report, flags)
        _counts(report, ("section_count", "authored_section_count"))
        content = [rows.fields([(key, report[key]) for key in
            ("report_id", "status", *flags, "section_count", "authored_section_count")])]
        for key in ("authored_section_ids", "incomplete_section_ids", "required_source_ids", "source_coverage_missing"):
            content.append(_string_list(key, report.get(key)))
        body.append(_section(report["report_id"], *content))
    return _section(t("rph_handoff"), *body)


def _product(value):
    rows.texts(value, ("current_id", "revision", "observed_at"))
    _bools(value, ("required", "present"))
    rows.count(value.get("version"))
    _counts(value.get("capability_counts"))
    rows.record(value.get("target"))
    _json(value["target"])
    return _section(t("rph_product"), rows.fields([(key, value[key]) for key in
        ("required", "present", "current_id", "revision", "observed_at", "version")]),
        _section("target", _native_metadata(value["target"])) if value["target"] else None,
        rows.fields(value["capability_counts"].items()),
        _string_list("contradictory_capability_keys", value.get("contradictory_capability_keys")))


def health(value):
    """Present the native v2 result; component readiness is not run completion."""
    h, _, _ = _kit()
    rows.identity(value)
    rows.texts(value, ("schema", "state", "driver_state", "lifecycle", "persisted_run_status", "last_activity",
                       "run_id", "run_operation_id", "project_operation_id"))
    if value["schema"] != "sonaloop.project_health.v2" or value["state"] not in (
            "running", "waiting", "stalled", "expired", "finished", "unverified", "archived", "superseded"):
        raise ValueError("Expected native project health v2")
    _bools(value, ("engine_finished", "unverified_output"))
    inventory = value.get("run_inventory")
    _counts(inventory, ("active", "historical_finished", "total"))
    tasks = value.get("tasks")
    _counts(tasks, ("done", "total"))
    rows.strings(tasks.get("next_ready"))
    activity = value.get("activity_lifecycle")
    rows.texts(activity, ("state", "expires_at", "note"))
    _counts(activity, ("stale_after_hours", "expires_after_hours"))
    _bools(activity, ("resumable",))
    if not isinstance(value.get("integrity_findings"), list):
        raise ValueError("Expected native integrity findings")
    for finding in [*value["integrity_findings"], *([value["unmet_invariant"]] if value.get("unmet_invariant") is not None else [])]:
        rows.texts(finding, ("code", "message", "severity"), ("target",))
    if "unmet_invariant" not in value:
        raise ValueError("Expected native invariant or null")
    rows.texts(value.get("last_successful_operation"), ("kind", "key", "at"), ("task_id", "summary"))
    _action(value.get("safe_next_action"))
    evidence = rows.record(value.get("evidence"))
    rows.count(evidence.get("orphaned"))
    _counts(evidence.get("posture_counts"))
    _counts(evidence.get("source_counts"))
    trace = value.get("trace")
    rows.texts(trace, ("support_ref", "workflow_trace_id", "local_journal", "external_host_visibility", "limitation"))
    rows.texts(trace.get("cloud_trace_query"), ("project_id",), ("run_id", "operation_id"))
    recovery = value.get("recovery_signals")
    recovery_keys = ("host_connection", "host_connection_note", "retry_result", "dispatch", "evidence", "critic", "audit", "external_host_error")
    rows.texts(recovery, recovery_keys)
    receipt = rows.record(recovery.get("retry_receipt"))
    if receipt:
        rows.texts(receipt, ("run_id", "key"))
        _counts(receipt, ("cursor", "step_idx"))
        if "deduplicated" in receipt:
            _bools(receipt, ("deduplicated",))
    return h("article", {"class_": "sl-research-card sl-research-health"}, h("h2", {}, t("rph_health")),
        rows.fields((("project_id", value["project_id"]), ("schema", value["schema"]), (t("status_h"), value["state"]),
            (t("rph_driver"), value["driver_state"]), (t("rph_lifecycle"), value["lifecycle"]),
            (t("rph_engine_finished"), value["engine_finished"]), (t("rph_persisted_run"), value["persisted_run_status"]),
            (t("rph_unverified"), value["unverified_output"]), (t("run_last_activity"), value["last_activity"]),
            ("run_id", value["run_id"]), ("run_operation_id", value["run_operation_id"]),
            ("project_operation_id", value["project_operation_id"]))),
        h("p", {"class_": "sl-run-attention sl-research-prose"}, attention_text(value)) if attention_text(value) else None,
        _section(t("rph_inventory"), rows.fields(((t("runs_active_h"), inventory["active"]),
            (t("rph_historical_finished"), inventory["historical_finished"]), (t("rph_total"), inventory["total"])))),
        _section(t("rph_tasks"), rows.fields(((t("rph_done"), tasks["done"]), (t("rph_total"), tasks["total"])))),
        _section(t("rph_activity"), rows.fields(((t("status_h"), activity["state"]),
            (t("rph_stale_hours"), activity["stale_after_hours"]), (t("rph_expires_hours"), activity["expires_after_hours"]),
            (t("rph_expires_at"), activity["expires_at"]), (t("rph_resumable"), activity["resumable"]))),
            h("p", {"class_": "sl-research-prose"}, activity["note"]) if activity["note"] else None),
        _preflight(value.get("preflight")), diagnostics_content(value, passive=True),
        _section(t("rph_evidence"), rows.fields(((t("rph_orphaned"), evidence["orphaned"]),)),
            _section(t("rph_posture"), rows.fields(evidence["posture_counts"].items())),
            _section(t("rph_sources"), rows.fields(evidence["source_counts"].items()))),
        _handoff(value.get("report_handoff")), _product(value.get("product_understanding")),
        _section(t("health_trace"), rows.fields([(key, trace[key]) for key in
            ("workflow_trace_id", "local_journal", "external_host_visibility")]), rows.fields(trace["cloud_trace_query"].items())),
        _section(t("rph_recovery"), rows.fields([(key, recovery[key]) for key in recovery_keys]),
            _section(t("rph_retry"), rows.fields([(key, receipt[key]) for key in
                ("run_id", "key", "cursor", "step_idx", "deduplicated") if key in receipt])) if receipt else None)), "ready"

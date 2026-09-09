"""Native Run results → explicit closed presentation DTO → one passive body.

Native scope/correlation tokens and operation aliases are execution context,
not proven authorization bearers. They deliberately are not presentation props.
No arbitrary metadata map or executable call crosses this field allowlist.
"""
from __future__ import annotations

from copy import deepcopy

from . import run_journal_rows as rows
from .library import _kit
from .projects_rows import disclosure, fields, t

public_schema = rows.public_schema


def _record(value):
    if type(value) is not dict:
        raise ValueError("Expected native Run record")
    return value


def _pick(value, names):
    _record(value)
    return {key: deepcopy(value[key]) for key in names if key in value}


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected native Run list")
    return value


def _refs(value):
    return [item if type(item) is str else _pick(item, ("kind", "id", "anchor", "quote", "text"))
            for item in _list(value)]


def _receipt(value):
    return _pick(value, ("run_id", "cursor", "step_idx"))


def _step(value):
    out = _pick(value, ("idx", "task_id", "bucket", "summary", "expected_output_kind", "open_questions"))
    for key in ("evidence", *rows.TRACE_FIELDS):
        if key in value:
            out[key] = _refs(value[key])
    if "receipt" in value:
        out["receipt"] = _receipt(value["receipt"])
    return out


def _dispatch(value):
    out = _pick(value, ("task_id", "step_id", "bucket", "dispatch_cursor", "status", "issued_at",
                       "completed_at", "expected_output_kind", "primary_output_kind", "input_fingerprint"))
    if "output_contract" in value:
        out["output_contract"] = _pick(value["output_contract"], ("schema", "max_primary_outputs",
            "allowed_primary_kinds", "supporting_kinds", "closing_kinds"))
    if "produced_refs" in value:
        out["produced_refs"] = _refs(value["produced_refs"])
    if "receipt" in value:
        out["receipt"] = _receipt(value["receipt"])
    for key, field in (("payload_fingerprints", "fingerprint"), ("payload_revisions", "revision")):
        if key in value:
            out[key] = [{"kind": kind, field: deepcopy(item)} for kind, item in _record(value[key]).items()]
    if "progress_receipts" in value:
        out["progress_receipts"] = [_pick(item, ("id", "kind", "status", "recorded_at", "input_fingerprint",
            "result_digest")) for item in _record(value["progress_receipts"]).values()]
    return out


def journal_view(value):
    """Project a full native start/read journal without guessing omitted state."""
    out = {"schema_version": rows.SCHEMA_VERSION, "view": "journal", **_pick(value,
        ("run_id", "project_id", "methodology", "status", "budget", "cursor", "created_at", "updated_at",
         "workflow_trace_id", "idempotent_replay", "injected_for"))}
    for key, project in (("steps", _step), ("dispatches", _dispatch),
                         ("critic_rounds", lambda row: _pick(row, ("round", "critic_report_id", "passed", "missing")))):
        if key in value:
            out[key] = [project(item) for item in _list(value[key])]
    return rows.validate_view(out)


def resumed_view(value):
    """The native continuation receipt is not a complete Health assessment."""
    out = {"schema_version": rows.SCHEMA_VERSION, "view": "resumed", **_pick(value,
        ("run_id", "project_id", "status", "cursor", "idempotent_replay"))}
    action = _record(value.get("safe_next_action"))
    args = _record(action.get("arguments"))
    if action.get("tool") != "run_step" or args.get("run_id") != value.get("run_id"):
        raise ValueError("Unsupported native Run continuation")
    out["continuation_tool"] = action["tool"]
    if "unmet_invariant" in value:
        out["unmet_invariant"] = (None if value["unmet_invariant"] is None else
            _pick(value["unmet_invariant"], ("code", "message", "severity", "target")))
    if "trace" in value:
        out["trace"] = _pick(value["trace"], ("support_ref", "workflow_trace_id", "local_journal",
                                              "external_host_visibility", "limitation"))
    return rows.validate_view(out)


def finished_view(value):
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": "finished",
        **_pick(value, ("run_id", "status", "steps", "deduplicated"))})


def identity_content(value):
    details = [(key, value[key]) for key in ("run_id", "project_id", "methodology", "created_at", "updated_at",
                                            "workflow_trace_id", "injected_for") if key in value]
    return disclosure(t("rpx_record_details"), fields(details))


def journal_content(value):
    """A validated presentation journal, shared by Product and native MCP."""
    h, fragment, _ = _kit()
    return h("div", {"class_": "sl-research-run-content"},
        fields(((t("rrun_state"), value["status"]), (t("rrun_budget"), value["budget"]),
                (t("rrun_cursor"), value["cursor"]))),
        fields(((t("rrun_replay"), value["idempotent_replay"]),)) if "idempotent_replay" in value else None,
        identity_content(value), rows.prose(t("rrun_scope_notice")),
        rows.section(t("rrun_steps"), fragment([rows.step_content(row) for row in value["steps"]])
                     if value["steps"] else rows.prose(t("rrun_no_steps"))),
        rows.section(t("rrun_dispatches"), fragment([rows.dispatch_content(row) for row in value["dispatches"]])
                     if value["dispatches"] else rows.prose(t("rrun_no_dispatches"))),
        rows.section(t("rrun_critics"), fragment([rows.critic_content(row) for row in value["critic_rounds"]])
                     if value["critic_rounds"] else rows.prose(t("rrun_no_critics"))),
        rows.prose(t("rrun_reference_notice")))


def _resumed_content(value):
    finding = value["unmet_invariant"]
    return _kit()[1](fields(((t("rrun_state"), value["status"]), (t("rrun_cursor"), value["cursor"]),
        (t("rrun_replay"), value["idempotent_replay"]), ("continuation_tool", value["continuation_tool"]))),
        identity_content(value), rows.prose(t("rrun_scope_notice")),
        disclosure(t("rrun_diagnostics"),
            rows.prose(finding["message"]) if finding is not None else None,
            fields([(key, finding[key]) for key in ("code", "severity", "target") if key in finding])
                if finding is not None else None, fields(value["trace"].items())))


def render_view(value):
    """Public authored props enter here directly; never treat them as native DTOs."""
    rows.validate_view(value)
    h, fragment, _ = _kit()
    if value["view"] == "journal":
        title, body = t("rrun_journal"), journal_content(value)
    elif value["view"] == "resumed":
        title, body = t("rrun_resumed"), _resumed_content(value)
    else:
        title, body = t("rrun_outcome"), fragment(fields(((t("rrun_state"), value["status"]),
            (t("rrun_steps"), value["steps"]), (t("rrun_deduplicated"), value["deduplicated"]))),
            identity_content(value), rows.prose(t("rrun_receipt_notice")))
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, title), body), "ready"


def journal(value):
    return render_view(journal_view(value))


def resumed(value):
    return render_view(resumed_view(value))


def finished(value):
    return render_view(finished_view(value))

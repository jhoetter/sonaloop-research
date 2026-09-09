"""Native Product Understanding → explicit public view → shared Product body.

Only known execution aliases are omitted. Target/inventory/verification scalar
attributes retain their exact names and values; unsupported compound extensions
fail presentation without changing native validation, output or persistence.
"""
from __future__ import annotations

from copy import deepcopy

from . import product_understanding_rows as rows
from .library import _kit
from .projects_rows import disclosure, fields, t

public_schema = rows.public_schema


def _mapping(value):
    if type(value) is not dict:
        raise ValueError("Expected native Product Understanding object")
    return value


def _attributes(value):
    return [{"name": key, "value": deepcopy(item)} for key, item in _mapping(value).items()]


def _pick(value, schema, excluded=()):
    value = _mapping(value)
    # Unknown authored fields must remain an honest unsupported-shape fallback.
    if set(value) - set(schema["properties"]) - set(excluded):
        raise ValueError("Unsupported native Product Understanding fields")
    return {key: deepcopy(item) for key, item in value.items() if key not in excluded}


def _inventory(value):
    value = _mapping(value)
    label = value.get("path") or value.get("name") or value.get("label") or value.get("state")
    return {"label": label, "attributes": _attributes({key: item for key, item in value.items()
        if key != "evidence_refs"}), "evidence_refs": deepcopy(value.get("evidence_refs", []))}


def _record(value, view):
    result = _pick(value, rows.VALUES[view], ("operation_id", "operation_fingerprint"))
    target = _mapping(value.get("target"))
    result["target"] = {"title": target.get("name") or target.get("identity") or target.get("url") or "—",
                        "attributes": _attributes(target)}
    for key in ("routes", "flows", "states"):
        if type(value.get(key)) is not list:
            raise ValueError("Expected native Product Understanding inventory")
        result[key] = [_inventory(row) for row in value[key]]
    if type(value.get("capabilities")) is not list:
        raise ValueError("Expected native Product Understanding capabilities")
    for capability in result["capabilities"]:
        _mapping(capability)
        if "verification_attempt" in capability:
            capability["verification_attempt"] = _attributes(capability["verification_attempt"])
    if "dispatch" in result:
        dispatch = _mapping(result["dispatch"])
        # Native scope/correlation values are execution context, not bearer claims.
        dispatch = _pick(dispatch, rows.DISPATCH, ("operation_id", "dispatch_token", "arguments", "key"))
        if "receipt" in dispatch:
            dispatch["receipt"] = _pick(dispatch["receipt"], rows.RECEIPT, ("key",))
        result["dispatch"] = dispatch
    return result


def recorded_view(value):
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": "record", "value": _record(value, "record")})


def stored_view(value):
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": "stored", "value": _record(value, "stored")})


def capability_content(value, *, show_status=True, prepared=None, recorded_details=True):
    h, _, _ = _kit()
    status = str(value.get("status") or "unknown")
    label = t("pu_" + status) if status in {"observed_present", "observed_absent", "inferred", "unknown"} else status
    prepared = prepared or {}
    refs = prepared.get("references")
    if refs is None and value.get("evidence_refs"):
        refs = rows.references(value["evidence_refs"])
    return h("li", {"class_": "sl-pu-claim"},
        prepared.get("status", h("span", {"class_": "lbl"}, label)) if show_status else None,
        " " if show_status else None, value.get("claim", ""),
        h("div", {"class_": "sl-claim-sources"}, refs) if refs else None,
        rows.section(t("rpu_rationale"), rows.prose(value["revision_reason"]))
            if recorded_details and "revision_reason" in value else None,
        disclosure(t("rpu_verification"), rows.attributes(value["verification_attempt"]))
            if recorded_details and "verification_attempt" in value else None,
        disclosure(t("rpx_record_details"), rows.selected(value, ("id", "key", "supersedes")))
            if recorded_details else None)


def record_content(value, *, prepared=None, passive=True, recorded_details=True):
    """Original Product capability content with complete supplied passive details.

    Product keeps its outer controls, full-history summary, prepared reference
    links and local timestamps. Passive input can never provide HTML fragments.
    """
    if passive and (prepared is not None or not recorded_details):
        raise ValueError("Passive Product Understanding cannot accept Product fragments")
    h, fragment, _ = _kit()
    prepared = prepared or {}
    target = value["target"]["title"] if recorded_details else (value.get("target", {}).get("name")
        or value.get("target", {}).get("identity") or value.get("target", {}).get("url") or "—")
    context = prepared.get("context", t("pu_context_summary", target=target,
        revision=value.get("revision") or "—", observed=value.get("observed_at") or ""))
    groups = [(False, t("pu_evidenced_n", n=sum(str(row.get("status") or "unknown") != "unknown"
        for row in value.get("capabilities", [])))), (True, t("pu_open_areas_n", n=sum(
        str(row.get("status") or "unknown") == "unknown" for row in value.get("capabilities", []))))]
    content = []
    for unknown, title in groups:
        group = [(index, row) for index, row in enumerate(value.get("capabilities", []))
            if (str(row.get("status") or "unknown") == "unknown") == unknown]
        if not group:
            continue
        claims = h("ul", {"class_": "sl-integrity-list"}, [capability_content(row,
            show_status=passive or not unknown, prepared=(prepared.get("capabilities") or {}).get(index),
            recorded_details=recorded_details) for index, row in group])
        content.append(rows.section(title, claims) if passive else h("details", {"class_": "sl-integrity-nested"},
            h("summary", {}, title), claims))
    return h("div", {"class_": "sl-integrity-body"},
        h("p", {"class_": "sl-integrity-context"}, context),
        fragment(content), rows.recorded_details(value, passive=passive) if recorded_details else rows.prose(t("rpu_details_unavailable")))


def render_view(value):
    rows.validate_view(value)
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("product_understanding_h")),
        record_content(value["value"])), "ready"


def recorded(value):
    return render_view(recorded_view(value))


def stored(value):
    return render_view(stored_view(value))

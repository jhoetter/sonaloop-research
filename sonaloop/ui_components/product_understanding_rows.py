"""Closed Product Understanding view types and passive semantic detail rows."""
from __future__ import annotations

from copy import deepcopy
import math

from .library import _kit
from .projects_rows import disclosure, fields, t


SCHEMA_VERSION = "sonaloop.product-understanding-view.v1"
TEXT, INTEGER, BOOLEAN = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
COUNT = {"type": "integer", "minimum": 0}
SCALAR = {"anyOf": [TEXT, {"type": "number"}, BOOLEAN, {"type": "null"}]}


def obj(required, optional=None):
    return {"type": "object", "additionalProperties": False,
            "properties": {**required, **(optional or {})}, "required": list(required)}


def array(schema):
    return {"type": "array", "items": schema}


ATTRIBUTES = array(obj({"name": TEXT, "value": SCALAR}))
REFERENCE = obj({"kind": TEXT, "id": TEXT}, {key: TEXT for key in ("anchor", "quote", "text", "role")})
REFERENCES = array(REFERENCE)
INVENTORY = obj({"label": TEXT, "attributes": ATTRIBUTES, "evidence_refs": REFERENCES})
CAPABILITY = obj({key: TEXT for key in ("id", "key", "claim", "status")}, {
    "evidence_refs": REFERENCES, "verification_attempt": ATTRIBUTES,
    "supersedes": TEXT, "revision_reason": TEXT})
MANIFEST = obj({**{key: TEXT for key in ("schema", "manifest_id", "manifest_digest", "target_revision",
    "expected_task", "captured_at")}, "manifest_version": INTEGER})
COVERAGE = obj({"step_index": COUNT, **{key: TEXT for key in
    ("status", "label", "asset_version_id", "content_digest", "notes")}, "evidence_refs": REFERENCES})
HISTORY = obj({**{key: TEXT for key in ("id", "revision", "observed_at", "supersedes")}, "version": INTEGER})
RECEIPT = obj({"run_id": TEXT, "cursor": COUNT, "step_idx": COUNT}, {"deduplicated": BOOLEAN})
DISPATCH = obj({"state": TEXT, "checkpointed": BOOLEAN}, {
    **{key: TEXT for key in ("task_id", "needs", "provenance", "produced_ref")},
    "reconciled_existing_checkpoint": BOOLEAN, "receipt": RECEIPT})
AUTHORING = obj({"schema": TEXT, "manifest_id": TEXT, "served_steps": array(COUNT), "url_role": TEXT})
RECORD = obj({**{key: TEXT for key in ("schema", "id", "project_id", "revision", "observed_at", "supersedes", "created_at")},
    "version": INTEGER, "target": obj({"title": TEXT, "attributes": ATTRIBUTES}),
    **{key: array(INVENTORY) for key in ("routes", "flows", "states")},
    "capabilities": array(CAPABILITY), "evidence_refs": REFERENCES}, {
    "stimulus_manifest": MANIFEST, "coverage_checklist": array(COVERAGE)})
# Manifest/coverage remain optional; writer and getter additions are distinct.
VALUES = {
    "record": obj({key: RECORD["properties"][key] for key in RECORD["required"]}, {
        **{key: RECORD["properties"][key] for key in ("stimulus_manifest", "coverage_checklist")},
        "idempotent_replay": BOOLEAN, "dispatch": DISPATCH, "project_url": TEXT, "bounded_authoring": AUTHORING}),
    "stored": obj({key: RECORD["properties"][key] for key in RECORD["required"]}, {
        **{key: RECORD["properties"][key] for key in ("stimulus_manifest", "coverage_checklist")},
        "history": array(HISTORY), "context": TEXT}),
}


def public_schema(view):
    if type(view) is not str or view not in VALUES:
        raise ValueError("Unknown Product Understanding view")
    return deepcopy(obj({"schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "view": {"type": "string", "const": view}, "value": VALUES[view]}))


def check(value, schema):
    if "anyOf" in schema:
        for child in schema["anyOf"]:
            try:
                check(value, child)
                return
            except ValueError:
                pass
        raise ValueError("Unsupported Product Understanding field")
    kind = schema["type"]
    valid = {"string": type(value) is str, "integer": type(value) is int,
        "number": type(value) in (int, float) and (type(value) is int or math.isfinite(value)),
        "boolean": type(value) is bool, "null": value is None,
        "object": type(value) is dict, "array": type(value) is list}[kind]
    if not valid or "const" in schema and value != schema["const"]:
        raise ValueError("Invalid Product Understanding field")
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError("Invalid Product Understanding count")
    if kind == "object":
        if set(value) - set(schema["properties"]) or set(schema["required"]) - set(value):
            raise ValueError("Unexpected or missing Product Understanding field")
        for key, item in value.items():
            check(item, schema["properties"][key])
    elif kind == "array":
        for item in value:
            check(item, schema["items"])


def validate_view(value):
    if type(value) is not dict or type(value.get("view")) is not str or value["view"] not in VALUES:
        raise ValueError("Expected closed Product Understanding view")
    check(value, public_schema(value["view"]))
    return value


def prose(value):
    return _kit()[0]("p", {"class_": "sl-research-prose"}, value)


def section(label, *body):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), *body)


def selected(value, keys):
    return fields([(key, value[key]) for key in keys if key in value])


def attributes(value):
    return fields([(row["name"], row["value"]) for row in value]) if value else prose(t("rpu_no_entries"))


def references(value):
    h, _, _ = _kit()
    return h("ul", {"class_": "sl-research-references"}, [h("li", {},
        h("span", {"class_": "sl-research-reference"},
          f'{ref["kind"]}:{ref["id"]}' + (f'#{ref["anchor"]}' if "anchor" in ref else "")),
        selected(ref, ("quote", "text", "role"))) for ref in value]) if value else prose(t("rpu_no_entries"))


def inventory_content(value):
    h, _, _ = _kit()
    return disclosure(t("rpu_inventory"), *[section(t("rpu_" + key),
        h("ul", {}, [h("li", {}, h("strong", {}, row["label"]), attributes(row["attributes"]),
            references(row["evidence_refs"])) for row in value[key]])
        if value[key] else prose(t("rpu_no_entries"))) for key in ("routes", "flows", "states")])


def recorded_details(value):
    h, fragment, _ = _kit()
    content = [disclosure(t("rpu_target_details"), attributes(value["target"]["attributes"])),
        inventory_content(value), disclosure(t("rpu_references"), references(value["evidence_refs"])),
        disclosure(t("rpx_record_details"), selected(value, ("schema", "id", "version", "project_id", "revision",
            "observed_at", "created_at", "supersedes", "project_url")))]
    if "stimulus_manifest" in value:
        content.append(disclosure(t("rpu_stimulus"), fields(value["stimulus_manifest"].items())))
    if "coverage_checklist" in value:
        content.append(disclosure(t("rpu_coverage"), fragment([section(row["label"],
            selected(row, ("step_index", "status", "asset_version_id", "content_digest", "notes")),
            references(row["evidence_refs"])) for row in value["coverage_checklist"]])
            if value["coverage_checklist"] else prose(t("rpu_no_entries"))))
    if "bounded_authoring" in value:
        authoring = value["bounded_authoring"]
        content.append(disclosure(t("rpu_authoring"), selected(authoring, ("schema", "manifest_id", "url_role")),
            fields((("served_steps", ", ".join(str(item) for item in authoring["served_steps"])),))))
    if "history" in value:
        content.append(disclosure(t("rpu_history"), h("ol", {}, [h("li", {}, fields(row.items()))
            for row in value["history"]]) if value["history"] else prose(t("rpu_no_entries"))))
    if "context" in value:
        content.append(disclosure(t("rpu_context"), prose(value["context"])))
    if "dispatch" in value:
        dispatch = value["dispatch"]
        content.append(disclosure(t("rpu_dispatch"), selected(dispatch, ("state", "checkpointed", "task_id", "needs",
            "provenance", "produced_ref", "reconciled_existing_checkpoint")),
            section(t("rpu_receipt"), fields(dispatch["receipt"].items())) if "receipt" in dispatch else None))
    return fragment(content)

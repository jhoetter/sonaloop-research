"""Closed Run presentation fields and semantic rows, without execution context."""
from __future__ import annotations

from copy import deepcopy

from .library import _kit
from .projects_rows import disclosure, fields, t


SCHEMA_VERSION = "sonaloop.run-view.v1"
TEXT = {"type": "string"}
INTEGER = {"type": "integer"}
COUNT = {"type": "integer", "minimum": 0}
BOOLEAN = {"type": "boolean"}


def object_schema(required, optional=None):
    return {"type": "object", "additionalProperties": False,
            "properties": {**required, **(optional or {})}, "required": list(required)}


def array_schema(items):
    return {"type": "array", "items": items}


TEXTS = array_schema(TEXT)
REFERENCE = {"anyOf": [TEXT, object_schema({"kind": TEXT, "id": TEXT},
    {"anchor": TEXT, "quote": TEXT, "text": TEXT})]}
REFERENCES = array_schema(REFERENCE)
RECEIPT = object_schema({"run_id": TEXT, "cursor": COUNT, "step_idx": COUNT})
TRACE_FIELDS = ("consume_refs", "optional_context_refs", "produced_refs", "downstream_refs", "parked_refs")
STEP = object_schema({"idx": COUNT, "task_id": TEXT, "bucket": TEXT, "summary": TEXT, "evidence": REFERENCES},
    {**{key: REFERENCES for key in TRACE_FIELDS}, "open_questions": TEXTS,
     "expected_output_kind": TEXT, "receipt": RECEIPT})
OUTPUT_CONTRACT = object_schema({"schema": TEXT, "max_primary_outputs": COUNT,
    "allowed_primary_kinds": TEXTS, "supporting_kinds": TEXTS, "closing_kinds": TEXTS})
PROGRESS = object_schema({"id": TEXT, "kind": TEXT, "status": TEXT, "recorded_at": TEXT,
                         "input_fingerprint": TEXT, "result_digest": TEXT})
DISPATCH = object_schema({key: TEXT for key in ("task_id", "step_id", "bucket", "status", "issued_at",
    "expected_output_kind", "primary_output_kind")} | {"dispatch_cursor": COUNT, "output_contract": OUTPUT_CONTRACT},
    {"completed_at": TEXT, "produced_refs": REFERENCES, "receipt": RECEIPT, "input_fingerprint": TEXT,
     "payload_fingerprints": array_schema(object_schema({"kind": TEXT, "fingerprint": TEXT})),
     "payload_revisions": array_schema(object_schema({"kind": TEXT, "revision": COUNT})),
     "progress_receipts": array_schema(PROGRESS)})
CRITIC = object_schema({"round": COUNT, "critic_report_id": TEXT, "passed": BOOLEAN, "missing": COUNT})
FINDING = object_schema({"code": TEXT, "message": TEXT, "severity": TEXT}, {"target": TEXT})
TRACE = object_schema({key: TEXT for key in ("support_ref", "workflow_trace_id", "local_journal",
                                            "external_host_visibility", "limitation")})


def _root(view, required, optional=None):
    return object_schema({"schema_version": {"type": "string", "const": SCHEMA_VERSION},
                          "view": {"type": "string", "const": view}, **required}, optional)


SCHEMAS = {
    "journal": _root("journal", {**{key: TEXT for key in ("run_id", "project_id", "methodology", "status",
        "created_at", "updated_at")}, "budget": {"anyOf": [INTEGER, {"type": "null"}]}, "cursor": COUNT,
        "steps": array_schema(STEP), "dispatches": array_schema(DISPATCH), "critic_rounds": array_schema(CRITIC)},
        {"workflow_trace_id": TEXT, "idempotent_replay": BOOLEAN, "injected_for": COUNT}),
    "resumed": _root("resumed", {"run_id": TEXT, "project_id": TEXT,
        "status": {"type": "string", "const": "active"}, "cursor": COUNT,
        "idempotent_replay": {"type": "boolean", "const": True},
        "continuation_tool": {"type": "string", "const": "run_step"},
        "unmet_invariant": {"anyOf": [FINDING, {"type": "null"}]}, "trace": TRACE}),
    "finished": _root("finished", {"run_id": TEXT,
        "status": {"type": "string", "enum": ["finished", "stopped", "capped"]},
        "steps": COUNT, "deduplicated": BOOLEAN}),
}


def public_schema(view):
    """The complete closed presentation schema; not a native business schema."""
    if view not in SCHEMAS:
        raise ValueError("Unknown Run presentation")
    return deepcopy(SCHEMAS[view])


def _validate(value, schema, path="value"):
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                _validate(value, branch, path)
                return
            except ValueError:
                pass
        raise ValueError(f"Unsupported Run presentation shape: {path}")
    kind = schema["type"]
    valid = {"string": type(value) is str, "integer": type(value) is int,
             "boolean": type(value) is bool, "null": value is None,
             "object": type(value) is dict, "array": type(value) is list}[kind]
    if not valid or "const" in schema and value != schema["const"] or "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Invalid Run presentation field: {path}")
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError(f"Invalid Run count: {path}")
    if kind == "object":
        if set(value) - set(schema["properties"]) or set(schema["required"]) - set(value):
            raise ValueError(f"Unexpected or missing Run presentation fields: {path}")
        for key, child in value.items():
            _validate(child, schema["properties"][key], f"{path}.{key}")
    elif kind == "array":
        for index, child in enumerate(value):
            _validate(child, schema["items"], f"{path}[{index}]")


def validate_view(value):
    if type(value) is not dict or value.get("view") not in SCHEMAS:
        raise ValueError("Expected a closed Run presentation")
    _validate(value, SCHEMAS[value["view"]])
    return value


def prose(text):
    h, _, _ = _kit()
    return h("p", {"class_": "sl-research-prose"}, text)


def section(label, *content):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), *content)


def text_list(values):
    h, _, _ = _kit()
    return h("ul", {}, [h("li", {}, text) for text in values]) if values else prose(t("rrun_no_entries"))


def refs_content(values):
    """All supplied references remain literal, including unresolved identifiers."""
    h, fragment, _ = _kit()
    rows = []
    for value in values:
        if isinstance(value, str):
            body = h("code", {}, value)
        else:
            label = f'{value["kind"]}:{value["id"]}' + (f'#{value["anchor"]}' if value.get("anchor") else "")
            body = fragment(h("code", {}, label),
                [prose(value[key]) for key in ("quote", "text") if key in value])
        rows.append(h("li", {}, body))
    return h("ul", {}, rows) if rows else prose(t("rrun_no_entries"))


def _record_details(value, keys):
    return fields([(key, value[key]) for key in keys if key in value])


def receipt_content(value):
    return _record_details(value, ("run_id", "cursor", "step_idx"))


def step_content(value):
    h, fragment, _ = _kit()
    references = [section(key, refs_content(value[key])) for key in ("evidence", *TRACE_FIELDS) if key in value]
    return h("section", {"class_": "sl-research-run-step"},
        h("h3", {}, t("rrun_step"), " ", str(value["idx"])), prose(value["summary"]),
        disclosure(t("rpx_record_details"), _record_details(value, ("task_id", "bucket", "expected_output_kind")),
            section(t("rrun_references"), fragment(references)),
            section("open_questions", text_list(value["open_questions"])) if "open_questions" in value else None,
            section("receipt", receipt_content(value["receipt"])) if "receipt" in value else None))


def dispatch_content(value):
    h, _, _ = _kit()
    contract = value["output_contract"]
    return h("div", {"class_": "sl-research-run-dispatch"},
        disclosure(f'{t("rrun_dispatch")} · {value["step_id"]} · {value["status"]}',
            _record_details(value, ("task_id", "step_id", "bucket", "dispatch_cursor", "status", "issued_at",
                "completed_at", "expected_output_kind", "primary_output_kind", "input_fingerprint")),
            section(t("rrun_output_contract"), _record_details(contract, ("schema", "max_primary_outputs")),
                [section(key, text_list(contract[key])) for key in
                 ("allowed_primary_kinds", "supporting_kinds", "closing_kinds")]),
            section("produced_refs", refs_content(value["produced_refs"])) if "produced_refs" in value else None,
            section("receipt", receipt_content(value["receipt"])) if "receipt" in value else None,
            [section(key, [fields(row.items()) for row in value[key]] or prose(t("rrun_no_entries")))
                for key in ("payload_fingerprints", "payload_revisions") if key in value],
            section(t("rrun_progress"), [fields(row.items()) for row in value["progress_receipts"]]
                or prose(t("rrun_no_entries"))) if "progress_receipts" in value else None))


def critic_content(value):
    h, _, _ = _kit()
    return h("section", {"class_": "sl-research-run-critic"},
        h("h3", {}, t("rrun_critic"), " ", str(value["round"])),
        _record_details(value, ("passed", "missing")),
        disclosure(t("rpx_record_details"), fields((("critic_report_id", value["critic_report_id"]),))))

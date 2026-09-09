"""Closed Plan presentation types and shared recorded-detail bodies.

Execution scope/correlation values are deliberately outside this public DTO.
This is a presentation contract, not a replacement native plan validator.
"""
from __future__ import annotations

from copy import deepcopy

from .library import _kit
from .projects_rows import disclosure, fields, t


SCHEMA_VERSION = "sonaloop.research-plan-view.v1"
TEXT, INTEGER, BOOLEAN = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
COUNT, NULL = {"type": "integer", "minimum": 0}, {"type": "null"}


def obj(required, optional=None):
    return {"type": "object", "additionalProperties": False,
            "properties": {**required, **(optional or {})}, "required": list(required)}


def array(schema):
    return {"type": "array", "items": schema}


STRINGS = array(TEXT)
REFERENCE = obj({"kind": TEXT, "id": TEXT})
RECEIPT = obj({"run_id": TEXT, "cursor": COUNT, "step_idx": COUNT}, {"deduplicated": BOOLEAN})
DISPATCH = obj({"state": TEXT, "checkpointed": BOOLEAN}, {
    **{key: TEXT for key in ("task_id", "needs", "provenance", "produced_ref")},
    "reconciled_existing_checkpoint": BOOLEAN, "receipt": RECEIPT})
FRAME = obj({"questions": STRINGS, "hypotheses": STRINGS, "memory_refs": STRINGS})
REQUIRES = obj({"min_inputs": {"anyOf": [INTEGER, NULL]}, "gate_tag": TEXT,
                "artifact_tags": STRINGS, "session_of_tags": STRINGS})
PRESENTATION = obj({}, {key: STRINGS for key in ("forms", "formats", "library")})
TASK = obj({**{key: TEXT for key in ("id", "title", "intent", "phase_intent", "plan_note", "bucket",
    "capability", "expected_output_kind", "step", "status", "loop_back")},
    "consumes": STRINGS, "produces": array(REFERENCE), "requires": REQUIRES,
    "presentation": PRESENTATION, "frame": {"anyOf": [FRAME, NULL]}}, {"dispatch": DISPATCH})
JUDGMENT = obj({"task_id": TEXT, "gate_tag": TEXT, "decided": BOOLEAN, "rationale": TEXT,
                "evidence_refs": STRINGS, "created_at": TEXT}, {"dispatch": DISPATCH})
KIND_COUNT = obj({"kind": TEXT, "count": COUNT})
COVERAGE = obj({"evidence_by_kind": array(KIND_COUNT), **{key: COUNT for key in
    ("artifacts", "sessions", "personas_touched", "tasks_done", "tasks_total")}})
PROGRESS = obj({"task_id": TEXT, "goal": TEXT, "delta": TEXT, "rationale": TEXT,
               "evidence_refs": STRINGS, "coverage": COVERAGE, "created_at": TEXT})
PARKING = obj({"task_id": TEXT, "refs": STRINGS, "reason": TEXT, "created_at": TEXT})
ITERATION = obj({"task_id": TEXT, "loop_back": TEXT, "round": INTEGER, "note": TEXT,
                 "entry": TEXT, "tasks": STRINGS, "created_at": TEXT})
INTEGRITY = obj({}, {"schema": TEXT, **{key: BOOLEAN for key in
    ("product_understanding_required", "cohort_preflight_required", "stimulus_required", "claim_posture_required")}})
PLAN = obj({"project_id": TEXT, "tasks": array(TASK)}, {
    **{key: TEXT for key in ("goal", "methodology", "created_at", "updated_at", "job")},
    "integrity": INTEGRITY, "judgments": array(JUDGMENT), "progress": array(PROGRESS),
    "parked_refs": array(PARKING), "unparked_refs": array(PARKING), "iterations": array(ITERATION)})
VALUES = {"plan": {"anyOf": [PLAN, NULL]}, "task": TASK, "judgment": JUDGMENT,
          "progress": PROGRESS, "parked": PARKING, "unparked": PARKING}


def public_schema(view):
    if view not in VALUES:
        raise ValueError("Unknown Plan presentation")
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
        raise ValueError("Unsupported Plan presentation shape")
    kind = schema["type"]
    valid = {"string": type(value) is str, "integer": type(value) is int, "boolean": type(value) is bool,
             "null": value is None, "object": type(value) is dict, "array": type(value) is list}[kind]
    if not valid or "const" in schema and value != schema["const"]:
        raise ValueError("Invalid Plan presentation value")
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError("Invalid Plan count")
    if kind == "object":
        if set(value) - set(schema["properties"]) or set(schema["required"]) - set(value):
            raise ValueError("Unexpected or missing Plan presentation field")
        for key, item in value.items():
            check(item, schema["properties"][key])
    elif kind == "array":
        for item in value:
            check(item, schema["items"])


def validate_view(value):
    if type(value) is not dict or value.get("view") not in VALUES:
        raise ValueError("Expected closed Plan presentation")
    check(value, public_schema(value["view"]))
    return value


def prose(value):
    return _kit()[0]("p", {"class_": "sl-research-prose"}, value)


def texts(values):
    h, _, _ = _kit()
    return h("ul", {}, [h("li", {}, text) for text in values]) if values else prose(t("rplan_no_entries"))


def section(label, *body):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), *body)


def selected(value, keys):
    return fields([(key, value[key]) for key in keys if key in value])


def frame_content(value):
    h, fragment, _ = _kit()
    return section(t("rplan_frame"), fragment([section(label, texts(value[key])) for key, label in
        (("questions", t("rplan_questions")), ("hypotheses", t("rplan_hypotheses")),
         ("memory_refs", t("rplan_memory_refs")))]))


def dispatch_content(value):
    return disclosure(t("rplan_dispatch"), selected(value, ("state", "checkpointed", "task_id", "needs",
        "provenance", "produced_ref", "reconciled_existing_checkpoint")),
        section(t("rplan_receipt"), selected(value["receipt"], ("run_id", "cursor", "step_idx", "deduplicated")))
        if "receipt" in value else None)


def judgment_content(value):
    return section(t("rplan_judgment"), fields((("gate_tag", value["gate_tag"]),
        (t("rplan_decided"), value["decided"]))), section(t("rplan_rationale"), prose(value["rationale"])), texts(value["evidence_refs"]),
        disclosure(t("rpx_record_details"), selected(value, ("task_id", "created_at"))),
        dispatch_content(value["dispatch"]) if "dispatch" in value else None)


def progress_content(value):
    coverage = value["coverage"]
    return section(t("rplan_progress_record"), prose(value["goal"]),
        fields(((t("rplan_delta"), value["delta"]),)), section(t("rplan_rationale"), prose(value["rationale"])), texts(value["evidence_refs"]),
        disclosure(t("rplan_coverage"), prose(t("rplan_coverage_notice")),
            selected(coverage, ("artifacts", "sessions", "personas_touched", "tasks_done", "tasks_total")),
            fields([(row["kind"], row["count"]) for row in coverage["evidence_by_kind"]])
                if coverage["evidence_by_kind"] else prose(t("rplan_no_entries"))),
        disclosure(t("rpx_record_details"), selected(value, ("task_id", "created_at"))))


def parking_content(value):
    return _kit()[1](prose(value["reason"]), texts(value["refs"]),
        disclosure(t("rpx_record_details"), fields((("task_id", value["task_id"] or t("rplan_plan_scope")),
            ("created_at", value["created_at"])))))


def task_details(value):
    h, fragment, _ = _kit()
    content = [selected(value, ("id", "bucket", "status", "expected_output_kind", "step", "loop_back")),
        *[section(key, prose(value[key])) for key in ("intent", "phase_intent", "plan_note") if value[key]],
        section("consumes", texts(value["consumes"])),
        section("produces", texts([f'{ref["kind"]}:{ref["id"]}' for ref in value["produces"]])),
        section("requires", selected(value["requires"], ("min_inputs", "gate_tag")),
                *[section(key, texts(value["requires"][key])) for key in ("artifact_tags", "session_of_tags")]),
        section(t("rplan_tags"), fragment([section(key, texts(items)) for key, items in value["presentation"].items()]))
            if value["presentation"] else None]
    return disclosure(t("rplan_task_details"), fragment(content)), (
        frame_content(value["frame"]) if value["frame"] is not None else "")


def history_content(value):
    h, fragment, _ = _kit()
    body = []
    for key, label, render in (("judgments", t("rplan_judgments"), judgment_content),
        ("progress", t("rplan_progress"), progress_content), ("parked_refs", t("rplan_parked"), parking_content),
        ("unparked_refs", t("rplan_unparked"), parking_content)):
        if key in value:
            body.append(section(label, fragment([render(row) for row in value[key]])
                                if value[key] else prose(t("rplan_no_entries"))))
    if "iterations" in value:
        records = [fragment(selected(row, ("task_id", "loop_back", "round", "entry", "created_at")),
                            prose(row["note"]), texts(row["tasks"])) for row in value["iterations"]]
        body.append(section(t("rplan_iterations"), fragment(records) if records else prose(t("rplan_no_entries"))))
    if "integrity" in value:
        body.append(section("integrity", fields(value["integrity"].items()) if value["integrity"]
                            else prose(t("rplan_no_entries"))))
    return h("div", {"class_": "sl-research-plan-history"},
             disclosure(t("rplan_history"), fragment(body))) if body else ""

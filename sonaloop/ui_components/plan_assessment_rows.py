"""Closed computed Assessment and supplied Plan-document presentation types."""
from __future__ import annotations

from copy import deepcopy
import math

from .library import _kit
from .projects_rows import disclosure, fields, t


SCHEMA_VERSION = "sonaloop.plan-assessment-view.v1"
TEXT, BOOLEAN = {"type": "string"}, {"type": "boolean"}
COUNT = {"type": "integer", "minimum": 0}
NUMBER = {"type": "number", "minimum": 0}
NULL_TEXT = {"anyOf": [TEXT, {"type": "null"}]}


def obj(required, optional=None):
    return {"type": "object", "additionalProperties": False,
        "properties": {**required, **(optional or {})}, "required": list(required)}


def array(schema):
    return {"type": "array", "items": schema}


STRINGS = array(TEXT)
COVERAGE = obj({"evidence_by_kind": array(obj({"kind": TEXT, "count": COUNT})),
    **{key: COUNT for key in ("artifacts", "sessions", "personas_touched", "tasks_done", "tasks_total")}})
BUCKET = obj({"bucket": TEXT, "done": COUNT, "total": COUNT})
GATE = obj({"task": TEXT, "title": TEXT, "unmet": STRINGS})
SATURATION = obj({"act_done": COUNT, "councils": COUNT, "syntheses": COUNT, "hint": TEXT})
NOVELTY = {"anyOf": [obj({}), obj({"artifact_kinds": STRINGS, "distinct_kinds": COUNT,
    "has_interactive_model": BOOLEAN, "hint": TEXT})]}
MEMORY = {"anyOf": [obj({}), obj({**{key: COUNT for key in ("personas", "facts", "events")},
    "avg_per_persona": NUMBER, "hint": TEXT})]}
REPORT = obj({"report_id": TEXT, "status": TEXT,
    **{key: BOOLEAN for key in ("complete", "body_empty", "lead_missing", "content_complete")},
    "section_count": COUNT, "authored_section_count": COUNT,
    **{key: STRINGS for key in ("authored_section_ids", "incomplete_section_ids", "required_source_ids", "source_coverage_missing")}})
HANDOFF = obj({"latest_report_id": TEXT,
    **{key: BOOLEAN for key in ("exists", "complete", "handed_off", "latest_complete", "lead_missing", "latest_stale")},
    **{key: STRINGS for key in ("completed_report_ids", "incomplete_report_ids", "stale_report_ids", "required_source_ids")},
    "reports": array(REPORT)})
FINISH = obj({**{key: BOOLEAN for key in ("organized", "concluded", "handed_off", "finished")},
    "gaps": STRINGS, "report_handoff": HANDOFF})
SCHEMA_REF = obj({"id": TEXT, "role": TEXT})
CONTRACT = obj({"expected": array(SCHEMA_REF), "missing": array(SCHEMA_REF), "satisfied": BOOLEAN,
    "recorded": array(obj({"id": NULL_TEXT, "schema_id": NULL_TEXT}))})
RUN_STATE = obj({"active_run": BOOLEAN, "tasks_done": COUNT, "tasks_total": COUNT, "note": TEXT})
ASSESSMENT = obj({**{key: TEXT for key in ("project_id", "goal", "url", "recommendation", "next")},
    "complete": BOOLEAN, "tasks_complete": BOOLEAN, "coverage": COVERAGE, "tasks_by_bucket": array(BUCKET),
    "open_gates": array(GATE), "open_questions": STRINGS, "saturation": SATURATION, "novelty": NOVELTY,
    "finish": FINISH, "result_contract": CONTRACT, "memory_depth": MEMORY, "gaps": STRINGS, "ready": STRINGS},
    {"run_state": RUN_STATE})
DOCUMENT = obj({"markdown": TEXT})
VALUES = {"assessment": ASSESSMENT, "document": DOCUMENT}


def public_schema(view):
    if type(view) is not str or view not in VALUES:
        raise ValueError("Unknown Plan assessment view")
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
        raise ValueError("Unsupported Plan assessment field")
    kind = schema["type"]
    valid = {"string": type(value) is str, "integer": type(value) is int,
        "number": type(value) in (int, float) and (type(value) is int or math.isfinite(value)),
        "boolean": type(value) is bool, "null": value is None,
        "object": type(value) is dict, "array": type(value) is list}[kind]
    if not valid or "const" in schema and value != schema["const"]:
        raise ValueError("Invalid Plan assessment field")
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError("Invalid Plan assessment count")
    if kind == "object":
        if set(value) - set(schema["properties"]) or set(schema["required"]) - set(value):
            raise ValueError("Unexpected or missing Plan assessment field")
        for key, item in value.items():
            check(item, schema["properties"][key])
    elif kind == "array":
        for item in value:
            check(item, schema["items"])


def validate_view(value):
    if type(value) is not dict or type(value.get("view")) is not str or value["view"] not in VALUES:
        raise ValueError("Expected closed Plan assessment view")
    check(value, public_schema(value["view"]))
    return value


def prose(value):
    return _kit()[0]("p", {"class_": "sl-research-prose"}, value)


def texts(value):
    h, _, _ = _kit()
    return h("ul", {}, [h("li", {}, item) for item in value]) if value else prose(t("rpa_no_entries"))


def section(title, *body):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, title), *body)


def selected(value, keys):
    return fields([(key, value[key]) for key in keys if key in value])


def coverage_content(value):
    return _kit()[1](selected(value, ("artifacts", "sessions", "personas_touched", "tasks_done", "tasks_total")),
        fields([(row["kind"], row["count"]) for row in value["evidence_by_kind"]])
        if value["evidence_by_kind"] else prose(t("rpa_no_entries")))


def contract_content(value):
    h, _, _ = _kit()
    return _kit()[1](fields((("satisfied", value["satisfied"]),)),
        *[section(key, h("ul", {}, [h("li", {}, fields(row.items())) for row in value[key]])
            if value[key] else prose(t("rpa_no_entries"))) for key in ("expected", "recorded", "missing")])


def assessment_details(value):
    from .project_health import _handoff
    h, fragment, _ = _kit()
    novelty, memory, finish = value["novelty"], value["memory_depth"], value["finish"]
    return fragment(disclosure(t("rpa_coverage"), coverage_content(value["coverage"])),
        disclosure(t("rpa_buckets"), h("ul", {}, [h("li", {}, fields(row.items())) for row in value["tasks_by_bucket"]])
            if value["tasks_by_bucket"] else prose(t("rpa_no_entries"))),
        disclosure(t("rpa_saturation"), prose(value["saturation"]["hint"]),
            selected(value["saturation"], ("act_done", "councils", "syntheses"))),
        disclosure(t("rpa_novelty"), prose(novelty["hint"]),
            selected(novelty, ("distinct_kinds", "has_interactive_model")), texts(novelty["artifact_kinds"]))
            if novelty else disclosure(t("rpa_novelty"), prose(t("rpa_no_entries"))),
        disclosure(t("rpa_memory"), prose(memory["hint"]), selected(memory, ("personas", "facts", "events", "avg_per_persona")))
            if memory else disclosure(t("rpa_memory"), prose(t("rpa_no_entries"))),
        disclosure(t("rpa_finish"), selected(finish, ("organized", "concluded", "handed_off", "finished")),
            texts(finish["gaps"]), _handoff(finish["report_handoff"])),
        disclosure(t("rpa_contract"), contract_content(value["result_contract"])),
        disclosure(t("rpa_run_state"), prose(value["run_state"]["note"]),
            selected(value["run_state"], ("active_run", "tasks_done", "tasks_total"))) if "run_state" in value else None,
        disclosure(t("rpa_next"), prose(value["next"])),
        disclosure(t("rpx_record_details"), selected(value, ("project_id", "url"))))

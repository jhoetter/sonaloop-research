"""Public pure Component entry point over the existing family projections.

These authored view-model props are presentation input, not MCP call arguments.
Selecting a registered projection never executes its corresponding tool.
"""
from __future__ import annotations

import json

from .registry import SURFACES
from . import run_journal, research_plan, product_understanding

_UNDERSTANDING_PROJECTIONS = {"record_product_understanding": product_understanding.recorded_view,
    "record_manifest_product_understanding": product_understanding.recorded_view,
    "get_product_understanding": product_understanding.stored_view}

_RUN_PROJECTIONS = {"start_run": run_journal.journal_view, "run_journal": run_journal.journal_view,
                    "resume_project_run": run_journal.resumed_view, "finish_run": run_journal.finished_view}

_PLAN_PROJECTIONS = {"get_plan": research_plan.plan_view, "add_task": research_plan.task_view,
    "record_frame": research_plan.task_view, "link_evidence": research_plan.task_view,
    "record_judgment": research_plan.judgment_view, "assess_progress": research_plan.progress_view,
    "park_evidence": research_plan.parked_view, "unpark_evidence": research_plan.unparked_view,
    "iterate_task": research_plan.iteration_view}


def public_component_value(name: str, value):
    """Prepare authored public view-model values without altering native MCP output.

    The native remote-registration envelope uses the reserved JS key `prototype`.
    Public examples use `artifact` for that one envelope; Run results use their
    explicit closed run-view.v1 projection. Research Plans similarly use the
    authored research-plan-view.v1 projection. Dispatch/private context is not a
    visual prop. Other projections preserve their existing authored DTO.
    """
    if name in _UNDERSTANDING_PROJECTIONS:
        return _UNDERSTANDING_PROJECTIONS[name](value)
    if name in _PLAN_PROJECTIONS:
        return _PLAN_PROJECTIONS[name](value)
    if name in _RUN_PROJECTIONS:
        return _RUN_PROJECTIONS[name](value)
    if name == "register_remote_prototype":
        if not isinstance(value, dict) or "prototype" not in value:
            raise ValueError("Expected native remote registration envelope")
        return {"artifact": value["prototype"], **({"note": value["note"]} if "note" in value else {})}
    if name in {"select_reaction_test_cohort", "record_cohort_preflight", "get_cohort_preflight"}:
        if not isinstance(value, dict):
            raise ValueError("Expected native cohort record")
        if isinstance(value.get("dispatch"), dict) and "dispatch_token" in value["dispatch"]:
            # This exact authority field is not a public presentation prop.
            # The native result remains untouched; the pure body does not use it.
            return {**value, "dispatch": {key: item for key, item in value["dispatch"].items()
                if key != "dispatch_token"}}
    return value


def render_component_props(component_id: str, props: dict):
    """Render {name, value} through the customer's existing pure projection."""
    if not isinstance(props, dict) or set(props) != {"name", "value"}:
        raise ValueError("Expected public Component name and value props")
    surface = SURFACES.get(props["name"]) if isinstance(props["name"], str) else None
    if surface is None or surface.component_id != component_id:
        raise ValueError("Projection does not belong to this Component")
    pending, nodes = [(props, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 2048 or depth > 12:
            raise ValueError("Public Component props exceed traversal limits")
        if isinstance(value, dict):
            if any(key in {"_meta", "__proto__", "constructor", "prototype"} for key in value):
                raise ValueError("Private metadata is not a public Component prop")
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    if len(json.dumps(props, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()) > 8192:
        raise ValueError("Public Component props exceed the byte limit")
    value = props["value"]
    if props["name"] == "register_remote_prototype":
        if not isinstance(value, dict) or "artifact" not in value or set(value) - {"artifact", "note"}:
            raise ValueError("Expected public remote-registration artifact and optional note")
        value = {"prototype": value["artifact"], **({"note": value["note"]} if "note" in value else {})}
    if props["name"] in _UNDERSTANDING_PROJECTIONS:
        expected = "stored" if props["name"] == "get_product_understanding" else "record"
        if not isinstance(value, dict) or value.get("view") != expected:
            raise ValueError("Product Understanding presentation does not belong to this projection")
        return product_understanding.render_view(value)
    if props["name"] in _RUN_PROJECTIONS:
        expected = {"start_run": "journal", "run_journal": "journal",
                    "resume_project_run": "resumed", "finish_run": "finished"}[props["name"]]
        if not isinstance(value, dict) or value.get("view") != expected:
            raise ValueError("Run presentation does not belong to this projection")
        return run_journal.render_view(value)
    if props["name"] in _PLAN_PROJECTIONS:
        expected = {"get_plan": "plan", "add_task": "task", "record_frame": "task",
                    "link_evidence": "task", "record_judgment": "judgment",
                    "assess_progress": "progress", "park_evidence": "parked",
                    "unpark_evidence": "unparked", "iterate_task": "iteration"}[props["name"]]
        if not isinstance(value, dict) or value.get("view") != expected:
            raise ValueError("Plan presentation does not belong to this projection")
        return research_plan.render_view(value)
    return surface.render(value)

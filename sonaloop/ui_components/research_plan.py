"""Native Plan results → closed public presentation → shared Product/MCP bodies.

Dispatch operation aliases and checkpoint keys are execution context, not
proven authorization bearers. Their deliberate omission never changes native
results, free prose, or stored plan history.
"""
from __future__ import annotations

from copy import deepcopy

from . import research_plan_rows as rows
from .library import _kit
from .projects_rows import disclosure, fields, t

public_schema = rows.public_schema


def _pick(value, schema):
    if type(value) is not dict:
        raise ValueError("Expected native Plan object")
    return {key: deepcopy(value[key]) for key in schema["properties"] if key in value}


def _list(value, project):
    if type(value) is not list:
        raise ValueError("Expected native Plan list")
    return [project(row) for row in value]


def _dispatch(value):
    out = _pick(value, rows.DISPATCH)
    if "receipt" in value:
        out["receipt"] = _pick(value["receipt"], rows.RECEIPT)
    return out


def _task(value):
    out = _pick(value, rows.TASK)
    # These native nested objects are data, never style/HTML instructions.
    # Keep their full supplied shape so unsupported fields fail validation.
    if "dispatch" in value:
        out["dispatch"] = _dispatch(value["dispatch"])
    return out


def _judgment(value):
    out = _pick(value, rows.JUDGMENT)  # operation_id can equal a dispatch token
    if "dispatch" in value:
        out["dispatch"] = _dispatch(value["dispatch"])
    return out


def _progress(value):
    out = _pick(value, rows.PROGRESS)
    if type(value.get("coverage")) is not dict or type(value["coverage"].get("evidence_by_kind")) is not dict:
        raise ValueError("Expected native coverage snapshot")
    out["coverage"] = _pick(value["coverage"], rows.COVERAGE)
    out["coverage"]["evidence_by_kind"] = [{"kind": kind, "count": deepcopy(count)}
        for kind, count in value["coverage"]["evidence_by_kind"].items()]
    return out


def _plan(value):
    if value is None:
        return None
    out = _pick(value, rows.PLAN)
    for key, project in (("tasks", _task), ("judgments", _judgment), ("progress", _progress),
        ("parked_refs", lambda row: _pick(row, rows.PARKING)),
        ("unparked_refs", lambda row: _pick(row, rows.PARKING)),
        ("iterations", lambda row: _pick(row, rows.ITERATION))):
        if key in value:
            out[key] = _list(value[key], project)
    return out


def _view(view, value):
    return rows.validate_view({"schema_version": rows.SCHEMA_VERSION, "view": view, "value": value})


def plan_view(value):
    return _view("plan", _plan(value))


def task_view(value):
    return _view("task", _task(value))


def judgment_view(value):
    return _view("judgment", _judgment(value))


def progress_view(value):
    return _view("progress", _progress(value))


def parked_view(value):
    return _view("parked", _pick(value, rows.PARKING))


def unparked_view(value):
    return _view("unparked", _pick(value, rows.PARKING))


def iteration_view(value):
    out = _pick(value, rows.ITERATION)
    if type(value) is not dict or "cloned" not in value:
        raise ValueError("Expected native iteration record and returned clones")
    out["cloned"] = _list(value["cloned"], _task)
    return _view("iteration", out)


def iteration_content(value):
    """Returned clones describe this invocation; stored history carries IDs only."""
    h, fragment, _ = _kit()
    ids = [task["id"] for task in value["cloned"]]
    if ids != value["tasks"] or len(ids) != len(set(ids)) or value["entry"] not in ids:
        raise ValueError("Iteration record and supplied clones disagree")
    return fragment(rows.prose(value["note"]), fields(((t("rplan_round"), value["round"]),)),
        rows.prose(t("rplan_iteration_notice")),
        disclosure(t("rpx_record_details"), rows.iteration_content(value)),
        h("section", {}, h("h3", {}, t("rplan_cloned_tasks")),
            fragment([task_content(task) for task in value["cloned"]])))


def task_content(value, *, titles=None, prepared=None, passive=True, last=False, recorded_details=True):
    """The original Product task row, plus shared full recorded details."""
    if passive and (prepared is not None or not recorded_details):
        raise ValueError("Passive plan tasks cannot accept Product fragments")
    h, fragment, _ = _kit()
    prepared, titles = prepared or {}, titles or {}
    status = value["status"]
    consumes = " · ".join(titles.get(key, key) for key in value.get("consumes", []))
    requirement = value.get("requires") or {}
    gates = prepared.get("gates")
    if gates is None:
        gates = []
        if requirement.get("min_inputs") is not None:
            gates.append(f'min_inputs: {requirement["min_inputs"]}')
        if requirement.get("gate_tag"):
            gates.append(requirement["gate_tag"])
        gates += [f'{key}: {tag}' for key in ("session_of_tags", "artifact_tags") for tag in requirement.get(key, [])]
    sub = ([f"↳ {consumes}"] if consumes else []) + gates
    evidence = prepared.get("evidence")
    if evidence is None:
        evidence = [h("span", {"class_": "ev sl-research-reference"}, f'{ref["kind"]}:{ref["id"]}')
                    for ref in value.get("produces", [])]
    detail, frame = rows.task_details(value) if recorded_details else ("", "")
    cls = "ptask" + (" is-done" if status == "done" else "") + (" is-last" if last else "")
    return h("div", {"class_": cls + (" sl-research-plan-task" if passive else "")}, prepared.get("mark"),
        h("div", {"class_": "pt-body"},
            h("div", {"class_": "pt-row1"}, h("span", {"class_": "pt-title"}, value.get("title", value["id"])),
                " · " if passive and value.get("capability") else None,
                h("span", {"class_": "pt-cap"}, value["capability"]) if value.get("capability") else ""),
            h("div", {"class_": "pt-sub"}, " · ".join(sub)) if sub else "",
            h("div", {"class_": "pt-evs"}, fragment(evidence)) if evidence else "",
            fields((("status", status),)) if passive else "", frame, detail,
            rows.dispatch_content(value["dispatch"]) if recorded_details and "dispatch" in value else None))


def plan_content(value, *, prepared=None, passive=True, recorded_details=True):
    """Supplied plan progress, ordered tasks and actual stored history.

    Product decorations are prepared outside this pure body. No gate evaluator,
    framework resolver, service or Store is used here.
    """
    if passive and (prepared is not None or not recorded_details):
        raise ValueError("Passive plan cannot accept Product fragments")
    h, fragment, _ = _kit()
    prepared = prepared or {}
    tasks = value.get("tasks", [])
    done = sum(task["status"] == "done" for task in tasks)
    complete = bool(tasks) and done == len(tasks)
    titles = {task["id"]: task.get("title", task["id"]) for task in tasks}
    buckets = [("analyze", t("plan_bucket_analyze")), ("act", t("plan_bucket_act")),
               ("verify", t("plan_bucket_verify"))]
    buckets += [(key, key) for key in dict.fromkeys(task["bucket"] for task in tasks)
                if key not in {"analyze", "act", "verify"}]
    sections = []
    for bucket, label in buckets:
        group = [(index, task) for index, task in enumerate(tasks) if task["bucket"] == bucket]
        if not group:
            continue
        completed = sum(task["status"] == "done" for _, task in group)
        content = [task_content(task, titles=titles, passive=passive, last=n == len(group) - 1,
                    prepared=(prepared.get("tasks") or {}).get(index), recorded_details=recorded_details)
                   for n, (index, task) in enumerate(group)]
        sections.append(h("div", {"class_": "psec"}, h("div", {"class_": "psec-h"},
            h("span", {}, label), " · " if passive else None,
            h("span", {"class_": "psec-n"}, f"{completed}/{len(group)}")),
            h("div", {"class_": "psec-list"}, fragment(content))))
    percent = round(100 * done / len(tasks)) if tasks else 0
    status_text = t("plan_complete") if complete and not passive else t("plan_progress", done=done, n=len(tasks))
    head = h("div", {"class_": "plan-hd"}, h("div", {"class_": "plan-goal"}, value.get("goal", "")),
        prepared.get("framework"), h("div", {"class_": "plan-prog-row"},
            h("div", {"class_": "plan-prog" + (" full" if complete else "")},
                h("i", {"style": f"width:{percent}%"})) if not passive else None,
            h("span", {"class_": "plan-prog-txt"}, status_text)),
        h("div", {"class_": "plan-sub"}, h("span", {"class_": "pt-cap"}, value.get("methodology") or t("plan_freeform")),
            " · " if passive else None,
            h("span", {}, t("n_tasks", n=len(tasks)))))
    return h("div", {"class_": "page" + (" sl-research-plan" if passive else "")}, head,
        rows.prose(t("rplan_task_notice")) if passive else None,
        fragment(sections) if sections else rows.prose(t("rplan_no_entries")),
        rows.prose(t("rplan_details_unavailable")) if not recorded_details else None,
        disclosure(t("rpx_record_details"), rows.selected(value, ("project_id", "created_at", "updated_at", "job"))),
        rows.history_content(value) if recorded_details else None)


def render_view(view):
    """Render authored public presentation directly, without native reconstruction."""
    rows.validate_view(view)
    value, kind = view["value"], view["view"]
    h, _, _ = _kit()
    if kind == "plan":
        title = t("plan_h")
        body = plan_content(value) if value is not None else rows.prose(t("no_plan_yet"))
    elif kind == "task":
        title, body = t("rplan_task"), task_content(value)
    elif kind == "judgment":
        title, body = t("rplan_judgment"), rows.judgment_content(value, heading=False)
    elif kind == "progress":
        title, body = t("rplan_progress_record"), rows.progress_content(value, heading=False)
    elif kind == "iteration":
        title, body = t("rplan_iteration"), iteration_content(value)
    else:
        title = t("rplan_park_record") if kind == "parked" else t("rplan_unpark_record")
        body = rows.parking_content(value)
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, title), body), (
        "empty" if kind == "plan" and (value is None or not value["tasks"]) else "ready")


def plan(value):
    return render_view(plan_view(value))


def task(value):
    return render_view(task_view(value))


def judgment(value):
    return render_view(judgment_view(value))


def progress(value):
    return render_view(progress_view(value))


def parked(value):
    return render_view(parked_view(value))


def unparked(value):
    return render_view(unparked_view(value))


def iteration(value):
    return render_view(iteration_view(value))

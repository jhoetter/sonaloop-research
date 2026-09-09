from __future__ import annotations

from .. import presentation as _pres
from ._i18n import t
from ._components import _icon
from ._graph_outline import _outline_html  # noqa: F401  (split out; import surface preserved)
from ._html import h, raw, fragment
from ._plan_fw import _framework_strip


def _plan_html(plan: dict, store) -> str:
    from ..ui_components import research_plan

    tasks = plan.get("tasks", [])
    # Product-only lookup/decorations. Positions retain each task's evidence ownership.
    status_marks = {"done": ("check", "var(--green)"), "active": ("half", "var(--accent)"),
                    "todo": ("circle", "var(--muted)"), "blocked": ("alert", "var(--red)")}
    syn_ids = {s["id"] for s in store.list_syntheses()}
    protos = {p["id"]: p for p in store.list_prototypes(plan["project_id"])}

    def ev_chip(ref: dict, number: int = 0) -> str:
        rid, kind = ref.get("id", ""), ref.get("kind", "")
        label = _pres.present(kind)["short"] if kind else rid
        if kind == "session" and number:
            label = f"{label} {number}"
        href = None
        if rid in protos:
            proto = protos[rid]
            href, label = f"/prototypes/{proto['slug']}", f"{label} · {proto.get('name', proto['slug'])}"
        elif rid in syn_ids:
            href = f"/syntheses/{rid}"
        elif store.get_council_session(rid):
            href = f"/councils/{rid}"
        return (h("a", {"class_": "ev", "href": href}, label, " ↗") if href
                else h("span", {"class_": "ev"}, label))

    prepared = {}
    for index, task in enumerate(tasks):
        mark, color = status_marks.get(task["status"], ("circle", "var(--faint)"))
        requirement = task.get("requires", {}) or {}
        gates = []
        if requirement.get("min_inputs") is not None:
            gates.append(f"min. {requirement['min_inputs']} Inputs")
        if requirement.get("gate_tag"):
            gates.append(_pres.present(requirement["gate_tag"])["short"])
        for tag in requirement.get("session_of_tags") or []:
            gates.append(f"Session: {_pres.present(tag)['short']}")
        for tag in requirement.get("artifact_tags") or []:
            gates.append(f"Artefakt: {_pres.present(tag)['short']}")
        evidence, number = [], 0
        for ref in task.get("produces", []):
            if ref.get("id") == task["id"]:
                continue
            if ref.get("kind") == "session":
                number += 1
                evidence.append(ev_chip(ref, number))
            else:
                evidence.append(ev_chip(ref))
        prepared[index] = {"mark": h("div", {"class_": "pt-mark", "style": f"color:{color}"}, raw(_icon(mark))),
                           "gates": gates, "evidence": evidence}
    try:
        value = research_plan.plan_view(plan)["value"]
        recorded_details = True
    except (ValueError, TypeError, KeyError):
        # Native extensions historically did not prevent the base Product plan
        # from rendering. Keep that same body; do not call an unsupported shape
        # a valid public DTO or manufacture a writer result from stored history.
        value, recorded_details = plan, False
    return research_plan.plan_content(value, passive=False, recorded_details=recorded_details,
        prepared={"tasks": prepared, "framework": _framework_strip(plan, tasks)})

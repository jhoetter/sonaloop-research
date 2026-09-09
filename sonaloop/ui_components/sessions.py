"""Passive projections of supplied native Session traces, without media reads."""
from __future__ import annotations

from .library import _kit, collection
from .session_steps import StepPresentation, step_content, outcome_banner, predicted_behaviors, reaction_reads, timeline_steps


def _step(value, position):
    if (not isinstance(value, dict) or type(value.get("index")) is not int or value["index"] != position
            or not isinstance(value.get("action"), dict) or not isinstance(value.get("state"), dict)
            or not isinstance(value.get("monologue"), str) or not isinstance(value.get("friction"), dict)
            or not isinstance(value.get("verdict"), dict) or type(value["verdict"].get("would_continue")) is not bool):
        raise ValueError("Expected an ordered native Session step")
    return value


def _full_record(value):
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str)
            or not isinstance(value.get("persona_id"), str) or not isinstance(value.get("subject"), dict)
            or value.get("fidelity") not in {"artifact", "prototype", "live"}
            or not isinstance(value.get("steps"), list) or not isinstance(value.get("outcome"), dict)
            or type(value["outcome"].get("completed")) is not bool):
        raise ValueError("Expected a full native usability Session")
    for position, step in enumerate(value["steps"]):
        _step(step, position)
    drop = value["outcome"].get("dropoff_step")
    if value["outcome"]["completed"]:
        if drop is not None:
            raise ValueError("Completed Session cannot have a drop-off")
    elif type(drop) is not int or not 0 <= drop < len(value["steps"]):
        raise ValueError("Expected the native Session drop-off step")
    return value


def passive_step(session: dict, step: dict):
    from .. import artifacts
    from ..web._i18n import t
    h, fragment, _ = _kit()
    state, action = step["state"], step["action"]
    fields = [h("p", {}, state.get("screen", ""))]
    # A stored screenshot path does not prove that its pixels were transferred or
    # are available to this host. Never probe or fetch the path during rendering.
    fields.append(h("p", {"class_": "muted small"}, t("session_mcp_screen_boundary")))
    if state.get("screenshot"):
        fields.append(h("code", {}, state["screenshot"]))
    focus = state.get("focus")
    if isinstance(focus, dict):
        fields.append(h("p", {"class_": "muted small"}, t("reading_flow_boundary")))
        fields.append(h("p", {}, focus.get("label", "")))
        fields.append(h("code", {}, " · ".join(f"{name}: {focus[name]}%" for name in ("x", "y", "width", "height") if name in focus)))
    screen = h("div", {"class_": "sl-research-session-description"}, fields)
    friction, verdict = step.get("friction") or {}, step.get("verdict") or {}
    meta = next((row for row in artifacts.friction_terms() if row["term"] == friction.get("level")), None)
    level = t(meta["label_key"]) if meta else str(friction.get("level") or "")
    foot = h("div", {"class_": "sl-research-session-foot"},
             h("p", {}, level, f' · {friction["note"]}' if friction.get("note") else None),
             h("p", {}, t("verdict_continue") if verdict["would_continue"] else t("verdict_drop"),
               f' · {verdict["reason"]}' if verdict.get("reason") else None)
             if type(verdict.get("would_continue")) is bool else None)
    return step_content(StepPresentation(step, screen, h("span", {}, action.get("type", "")), foot), passive=True)


def predictions(values):
    from ..web._render import render_ref
    from .. import artifacts
    h, fragment, raw = _kit()
    if not isinstance(values, list):
        raise ValueError("Expected native predicted behaviors")
    likelihoods, references = [], []
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("action"), str):
            raise ValueError("Expected a native predicted behavior")
        original_likelihood = value.get("likelihood")
        term = (original_likelihood.get("value", original_likelihood.get("label"))
                if isinstance(original_likelihood, dict) else original_likelihood)
        likelihood = artifacts.resolve_likelihood(term)
        if likelihood is None:
            likelihoods.append(h("span", {"class_": "sl-research-badge"}, str(term)))
        else:
            probability = f'{likelihood["value"] * 100:g}%'
            likelihoods.append(h("span", {"class_": "sl-research-badge"}, probability,
                                 f' · {likelihood["label"]}' if likelihood.get("label") else None))
        references.append(fragment(*(raw(render_ref(ref, passive=True)) for ref in value.get("refs") or [])))
    return predicted_behaviors(values, references=references, likelihoods=likelihoods, passive=True)


def session(value):
    from ..web._i18n import t
    from ..web._render import render_statements
    h, fragment, raw = _kit()
    record = _full_record(value)
    subject = record["subject"]
    title = subject.get("label") or subject.get("id") or subject.get("url") or record["id"]
    kind = {"artifact": t("session_kind_artifact"), "prototype": t("session_kind_prototype"), "live": t("session_kind_live")}[record["fidelity"]]
    grounded = record.get("grounded_verified")
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, kind), h("h2", {}, title)),
             h("p", {"class_": "muted small"}, record["persona_id"],
               f' · {record["date"]}' if record.get("date") else None),
             h("p", {"class_": "muted small"}, t("grounding_h"), ": ", t("grounded_yes") if grounded else t("grounded_no"))
             if type(grounded) is bool else None,
             h("code", {}, f'{subject.get("kind", "")}:', subject.get("id") or subject.get("url") or ""),
             recorded_context(record),
             outcome_banner(record, passive=True),
             h("div", {"class_": "sl-research-session-steps"},
               fragment(*(passive_step(record, step) for step in record["steps"]))),
             predictions(record["outcome"].get("predicted_behaviors") or []),
             raw(render_statements(record.get("statements") or [], passive=True))), "ready"


def session_write(value):
    if not isinstance(value, dict):
        raise ValueError("Expected the native usability Session write result")
    return session(value.get("usability_session"))


def sessions(value):
    from ..web._i18n import t
    if not isinstance(value, dict) or not isinstance(value.get("sessions"), list):
        raise ValueError("Expected native usability Sessions")
    cards = [session(item)[0] for item in value["sessions"]]
    return collection(cards, empty=t("no_sessions")), "ready" if cards else "empty"


def prototype_session_write(value):
    from ..web._i18n import t
    from ..web._render import render_statements
    h, fragment, raw = _kit()
    record = value.get("prototype_session") if isinstance(value, dict) else None
    if (not isinstance(record, dict) or any(not isinstance(record.get(key), str)
                                           for key in ("id", "persona_id", "prototype_id"))
            or not isinstance(record.get("reaction"), dict)):
        raise ValueError("Expected the native prototype Session write result")
    reaction = record["reaction"]
    steps = reaction.get("steps") or timeline_steps(reaction.get("timeline")) or record.get("steps") or []
    if not isinstance(steps, list) or any(not isinstance(step, dict) or not isinstance(step.get("state"), dict)
                                         or not isinstance(step.get("action"), dict) for step in steps):
        raise ValueError("Expected the supplied native prototype Session steps")
    grounded = record.get("grounded_verified")
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("session_kind_prototype")),
               h("h2", {}, record["prototype_id"])),
             h("p", {"class_": "muted small"}, record["persona_id"],
               f' · {record["date"]}' if record.get("date") else None),
             h("p", {}, t("grounding_h"), ": ", t("grounded_yes") if grounded else t("grounded_no"))
             if type(grounded) is bool else None,
             recorded_context(record),
             fragment(reaction_reads(reaction, passive=True)),
             h("div", {"class_": "sl-research-session-steps"}, fragment(*(passive_step(record, step) for step in steps))),
             predictions(reaction.get("predicted_behaviors") or []),
             raw(render_statements(record.get("statements") or [], passive=True))), "ready"


def recorded_context(record):
    """Literal captured revision/state references, never a current-state lookup."""
    from ..web._i18n import t
    h, fragment, _ = _kit()
    refs = record.get("observed_state_refs") or (record.get("reaction") or {}).get("observed_state_refs") or []
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("Expected recorded native Session state references")
    return fragment(
        h("p", {"class_": "muted small"}, t("session_recorded_version"), ": ", h("code", {}, record["prototype_version"]))
        if record.get("prototype_version") else None,
        h("ul", {"class_": "sl-research-references"}, *(h("li", {}, h("code", {}, ref)) for ref in refs)) if refs else None)

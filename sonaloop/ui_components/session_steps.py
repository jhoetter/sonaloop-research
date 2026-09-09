"""Pure Session reading blocks over explicitly prepared media/label fragments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .library import _kit


@dataclass(frozen=True)
class StepPresentation:
    step: dict
    screen: Any
    action_chip: Any = None
    foot: Any = None
    focus: bool = False
    color: str | None = None


def step_content(row: StepPresentation, *, passive: bool = False):
    """The product's screen/action anatomy; all resolution happened before here."""
    h, _, _ = _kit()
    step, focus = row.step, row.focus
    index = step.get("index", 0)
    state, action = step.get("state") or {}, step.get("action") or {}
    caption = " · ".join(x for x in (state.get("url"), state.get("title")) if x)
    target, detail = (action.get("target") or "").strip(), (action.get("detail") or "").strip()
    monologue = (step.get("monologue") or "").strip()
    def classes(base, marker):
        return base + " sl-research-" + marker if passive else base
    return h("div", {"class_": classes("sess-step sl-session-focus-step" if focus else "sess-step", "session-step"),
                     "id": f"step-{index}", "style": f"--sfc:{row.color}" if row.color else None},
             h("div", {"class_": classes("sess-screen", "session-screen")}, row.screen,
               h("div", {"class_": classes("sess-cap", "session-caption"), "title": caption}, caption) if caption else None),
             h("div", {"class_": classes("sess-act", "session-action")},
               h("div", {"class_": classes("sess-act-h", "session-action-head")},
                 h("span", {"class_": "sess-n"}, str(index + 1) if focus else str(index)),
                 row.action_chip if action.get("type") and not focus else None,
                 h("span", {"class_": classes("sess-target", "session-target")}, target) if target and not focus else None),
               h("p", {"class_": "sess-detail"}, detail) if detail else None,
               h("blockquote", {"class_": classes("sess-mono", "session-monologue")}, monologue) if monologue else None,
               row.foot))


def predicted_behaviors(behaviors: list, *, references: list, likelihoods: list, passive=False):
    """Same native prediction rows; no reference or vocabulary lookup in this core."""
    from ..web._i18n import t
    h, fragment, _ = _kit()
    if len(behaviors) != len(references) or len(behaviors) != len(likelihoods):
        raise ValueError("Every prediction needs its own prepared reference and likelihood")
    if not behaviors:
        return ""
    rows = []
    for behavior, refs, likelihood in zip(behaviors, references, likelihoods, strict=True):
        rows.append(h("div", {"class_": "hyp sl-research-prediction" if passive else "hyp"},
                      h("div", {}, likelihood, " ", h("b", {}, behavior.get("action", ""))),
                      h("p", {"class_": "muted small"}, behavior["trigger"]) if behavior.get("trigger") else None,
                      h("p", {"class_": "muted small"}, t("step_n", n=behavior["step"]))
                      if passive and behavior.get("step") is not None else None,
                      h("p", {"class_": "muted small turn-refs"}, refs) if behavior.get("refs") else None))
    return h("div", {"class_": "sec sl-research-predictions" if passive else "sec", "id": "sec-predicted"},
             h("h2", {}, t("predicted_behaviors_h"), h("span", {"class_": "h1cnt"}, (" · " if passive else "") + str(len(behaviors)))), fragment(*rows))


def outcome_banner(session: dict, *, passive=False):
    from ..web._components import _icon
    from ..web._i18n import t
    h, _, raw = _kit()
    outcome = session.get("outcome") or {}
    summary = (outcome.get("summary") or "").strip()
    cls = "sess-banner sl-research-session-outcome" if passive else "sess-banner"
    if outcome.get("completed"):
        return h("div", {"class_": cls, "style": "--sbc:var(--green)"},
                 None if passive else raw(_icon("check")), h("strong", {}, t("completed")),
                 h("span", {"class_": "muted"}, summary) if summary else None)
    drop = outcome.get("dropoff_step", 0)
    step = next((s for s in session.get("steps") or [] if s.get("index") == drop), {})
    reason = ((step.get("verdict") or {}).get("reason") or summary or "").strip()
    label = t("outcome_dropped", n=drop)
    return h("div", {"class_": cls, "style": "--sbc:var(--red)"},
             None if passive else raw(_icon("warning")),
             h("strong", {}, label if passive else h("a", {"href": f"#step-{drop}"}, label)),
             h("span", {"class_": "muted"}, reason) if reason else None,
             h("p", {}, summary) if passive and summary and summary != reason else None)


def reaction_reads(reaction: dict, *, passive=False):
    from ..web import ui
    from ..web._components import _md, _study_lead
    from ..web._i18n import t
    h, fragment, raw = _kit()
    verdict = (reaction.get("verdict") or "").strip()
    body = raw(_md(verdict))
    lead = (raw(_study_lead(body if passive else ui.clamp(body, threshold=ui.SECTION_CLAMP),
                            t("verdict_h"), qid="sec-verdict")) if verdict else "")
    def read_list(identity, heading, items):
        if not items:
            return ""
        return h("div", {"class_": "sec sl-research-reaction-list" if passive else "sec", "id": identity},
                 h("h2", {}, heading, h("span", {"class_": "h1cnt"}, (" · " if passive else "") + str(len(items)))),
                 fragment(*(h("p", {"class_": "small"}, item) for item in items)))
    return lead, read_list("sec-liked", t("proto_liked_h"), reaction.get("liked") or []), \
        read_list("sec-friction", t("friction_rail_h"), reaction.get("friction") or [])


def timeline_steps(timeline) -> list[dict]:
    """The existing product's free-form reaction timeline projection."""
    if not isinstance(timeline, list):
        return []
    steps = []
    for position, entry in enumerate(item for item in timeline if isinstance(item, dict)):
        try:
            index = int(str(entry.get("step", position)).strip())
        except (TypeError, ValueError):
            index = position
        monologue = next((entry[key] for key in ("monologue", "monolog") if entry.get(key)), "")
        observed = next((entry[key] for key in ("observed", "beobachtung", "screen") if entry.get(key)), "")
        steps.append({"index": index, "action": {"detail": str(entry.get("action") or "")},
                      "monologue": str(monologue), "state": {"screen": str(observed)}})
    return steps

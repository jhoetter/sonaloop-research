"""Recorded planning intentions shared by the persona inspector and passive Apps."""
from __future__ import annotations

from .library import _kit, collection


def _record(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a native plan record")
    for key in ("id", "persona_id", "scope", "period_start", "period_end", "created_at",
                "summary", "mood_trajectory"):
        if not isinstance(value.get(key), str):
            raise ValueError(f"Expected native plan {key}")
    for key in ("intentions", "expected_milestones", "sample_days"):
        if not isinstance(value.get(key), list) or any(not isinstance(x, str) for x in value[key]):
            raise ValueError(f"Expected native plan {key}")
    return value


def plan_content(value):
    """Complete authored intentions; no scheduling, normalization or status inference."""
    from ..web._i18n import t
    h, fragment, _ = _kit()
    value = _record(value)
    sections = []
    for key, label in (("intentions", t("rc_intentions")), ("expected_milestones", t("rc_milestones")),
                       ("sample_days", t("rc_sample_days"))):
        if value[key]:
            sections.append(h("div", {}, h("h3", {}, label), h("ul", {}, [h("li", {}, x) for x in value[key]])))
    return h("div", {"class_": "sl-research-plan"},
             h("p", {}, t("rc_scope"), ": ", value["scope"], " · ", value["period_start"], " → ", value["period_end"]),
             h("p", {"class_": "sl-research-meta"}, value["persona_id"], " · ", value["id"]),
             h("p", {"class_": "sl-research-meta"}, t("rc_created_at"), ": ", value["created_at"]),
             h("p", {"class_": "sl-research-prose"}, value["summary"]) if value["summary"] else None,
             fragment(sections),
             h("div", {}, h("h3", {}, t("rc_mood_trajectory")),
               h("p", {"class_": "sl-research-prose"}, value["mood_trajectory"])) if value["mood_trajectory"] else None,
             h("p", {"class_": "muted small sl-research-meta"}, t("rc_plan_notice")))


def plan(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if value is None:
        return collection([], empty=t("rc_plans_empty")), "empty"
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rc_plans")), plan_content(value)), "ready"


def plans(value):
    from ..web._i18n import t
    if not isinstance(value, list):
        raise ValueError("Expected native plan list")
    cards = [plan(item)[0] if isinstance(item, dict) else _record(item) for item in value]
    return collection(cards, empty=t("rc_plans_empty")), "ready" if cards else "empty"

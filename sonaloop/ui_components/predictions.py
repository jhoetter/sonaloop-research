"""Supplied prediction aggregates shared by Product results and passive MCP."""
from __future__ import annotations

import math

from .library import _kit, collection
from .projects_rows import identity, record, texts, strings, count, fields, t
from .project_graph import records, counts


def predictions_content(value):
    from ..web._render import render_ref
    h, fragment, raw = _kit()
    identity(value)
    for key in ("total", "personas"):
        count(value.get(key))
    scale = strings(value.get("likelihood_scale"))
    groups = []
    for group in records(value.get("groups")):
        texts(group, ("action", "subject")); count(group.get("count"))
        people = strings(group.get("personas")); triggers = strings(group.get("triggers"))
        step = group.get("step")
        if type(step) not in (int, str, type(None)):
            raise ValueError("Expected the native step value")
        likelihood = group.get("likelihood_mean")
        if likelihood is not None and (type(likelihood) not in (int, float) or not math.isfinite(likelihood)):
            raise ValueError("Expected a finite native likelihood or null")
        sources = records(group.get("sources"))
        for source in sources:
            texts(source, ("kind", "id"))
            if source.get("anchor") is not None:
                texts(source, ("anchor",))
        refs = records(group.get("refs"))
        groups.append(h("article", {"class_": "sl-research-card"}, h("h3", {}, group["action"]),
            h("p", {}, group["subject"]), fields(((t("rpr_step"), step), (t("rpr_count"), group["count"]),
                (t("rpr_likelihood"), likelihood))), h("p", {}, t("participants"), ": ", ", ".join(people)),
            h("ul", {}, [h("li", {}, trigger) for trigger in triggers]),
            fragment([raw(render_ref(ref, passive=True)) for ref in refs]), h("h4", {}, t("rpr_sources")),
            h("ul", {}, [h("li", {}, source["kind"], ":", source["id"],
                "#" + source["anchor"] if source.get("anchor") else "") for source in sources])))
    return h("section", {"class_": "sl-research-predictions"}, h("h2", {}, t("rpr_predictions")),
        fields((("project_id", value["project_id"]), (t("rpr_total"), value["total"]),
                (t("participants"), value["personas"]))), h("p", {"class_": "sl-research-meta"}, t("rpr_notice")),
        collection(groups, empty=t("rpr_empty")), h("h3", {}, t("rpr_by_step")), counts(value.get("by_step")),
        h("p", {}, t("rpr_scale"), ": ", ", ".join(scale)))


def predictions(value):
    html = predictions_content(value)
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, html), "ready" if value["groups"] else "empty"

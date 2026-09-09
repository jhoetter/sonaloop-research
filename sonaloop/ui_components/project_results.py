"""The native automation result composed from the shared customer bodies."""
from __future__ import annotations

from .library import _kit, collection
from .projects import _project, project_body
from .projects_rows import record, texts, fields, t
from .project_graph import records, counts, questions_content
from .council_formats import query_council_card
from .predictions import predictions_content
from .syntheses import synthesis


def _unavailable(label):
    h, _, _ = _kit()
    return h("p", {"class_": "sl-research-meta"}, label, ": ", t("rpr_unavailable"))


def _run_state(value):
    """The nullable native summary is separate from the deeper health result."""
    h, _, _ = _kit()
    label = t("rpr_run_state")
    if value is None:
        return _unavailable(label)
    record(value)
    pairs = []
    for key in ("state", "last_activity", "driver_state", "run_id"):
        if key in value and value[key] is not None:
            texts(value, (key,)); pairs.append((key, value[key]))
    for key in ("engine_finished", "unverified_output"):
        if key in value:
            if type(value[key]) is not bool:
                raise ValueError("Expected native run-state flag")
            pairs.append((key, value[key]))
    return h("section", {}, h("h3", {}, label), fields(pairs))


def study(value):
    from .project_health import health
    h, _, _ = _kit()
    record(value)
    if type(value.get("substrate_version")) is not int or value["substrate_version"] != 1:
        raise ValueError("Expected native study-result substrate version 1")
    project = value.get("project"); _project(project)
    councils = [query_council_card(row) for row in records(value.get("councils"))]
    syntheses = [synthesis(row)[0] for row in records(value.get("syntheses"))]
    for key in ("run_state", "project_health", "predictions"):
        if key not in value:
            raise ValueError("Expected explicit nullable native result: " + key)
    return h("article", {"class_": "sl-research-card sl-research-study-result"},
        h("h2", {}, t("rpr_study")), project_body(project, level="h3", passive=True),
        h("p", {"class_": "sl-research-meta"}, t("rpr_study_scope")), counts(value.get("counts")),
        _run_state(value["run_state"]),
        health(value["project_health"])[0] if value["project_health"] is not None else _unavailable(t("rph_health")),
        h("div", {"class_": "sl-research-study-findings"},
            h("section", {}, h("h3", {}, t("councils")), collection(councils, empty=t("no_councils"))),
            h("section", {}, h("h3", {}, t("syntheses")), collection(syntheses, empty=t("rpr_no_syntheses"))),
            questions_content(value.get("open_questions")),
            predictions_content(value["predictions"]) if value["predictions"] is not None else _unavailable(t("rpr_predictions")))), "ready"

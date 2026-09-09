"""Shared recorded digest, experience-summary and Memory processing content."""
from __future__ import annotations

from .library import _kit, collection


def _record(value, strings=(), counts=(), lists=()):
    if not isinstance(value, dict):
        raise ValueError("Expected a native Memory result")
    for key in strings:
        if not isinstance(value.get(key), str):
            raise ValueError(f"Expected native Memory {key}")
    for key in counts:
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError(f"Expected native Memory count {key}")
    for key in lists:
        if not isinstance(value.get(key), list) or any(not isinstance(x, str) for x in value[key]):
            raise ValueError(f"Expected native Memory strings {key}")
    return value


def count_rows(pairs):
    """Explicit native quantities, including zero; never aggregate or infer them."""
    h, _, _ = _kit()
    if any(type(count) is not int or count < 0 for _, count in pairs):
        raise ValueError("Expected supplied nonnegative counts")
    return h("dl", {"class_": "sl-research-fields sl-research-memory-counts"},
             [h(tag, {}, value) for label, count in pairs for tag, value in (("dt", label), ("dd", str(count)))])


def _list(label, values):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), h("ul", {}, [h("li", {}, x) for x in values])) if values else None


def digest_content(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    _record(value, ("id", "persona_id", "scope", "period_start", "period_end", "created_at", "text"),
            lists=("themes", "trends"))
    if not isinstance(value.get("project_arcs"), list):
        raise ValueError("Expected native digest project arcs")
    arcs = [_record(arc, ("name", "arc")) for arc in value["project_arcs"]]
    return h("div", {"class_": "sl-research-memory-digest"},
             h("p", {"class_": "sl-research-meta"}, value["persona_id"], " · ", value["id"]),
             h("p", {}, value["scope"], " · ", value["period_start"], " → ", value["period_end"]),
             h("p", {"class_": "sl-research-meta"}, t("rc_created_at"), ": ", value["created_at"]),
             h("p", {"class_": "sl-research-prose"}, value["text"]),
             _list(t("rmo_themes"), value["themes"]),
             h("section", {}, h("h3", {}, t("rmo_arcs")), [
                 h("div", {}, h("h4", {}, arc["name"]), h("p", {"class_": "sl-research-prose"}, arc["arc"])) for arc in arcs]) if arcs else None,
             _list(t("rmo_trends"), value["trends"]))


def digest(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rmo_digest")), digest_content(value)), "ready"


def digests(values):
    from ..web._i18n import t
    if not isinstance(values, list):
        raise ValueError("Expected native digest list")
    return collection([digest(value)[0] for value in values], empty=t("rmo_digests_empty")), "ready" if values else "empty"


def summary_content(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    _record(value, counts=("days", "events"), lists=("completed", "blockers", "open_loops"))
    persona = _record(value.get("persona"), ("id", "display_name", "slug"))
    period = _record(value.get("period"), ("lens",))
    if any(period.get(key) is not None and not isinstance(period[key], str) for key in ("start", "end")):
        raise ValueError("Expected native summary period")
    pains = value.get("top_pain_points")
    if not isinstance(pains, list) or any(not isinstance(row, (list, tuple)) or len(row) != 2
            or not isinstance(row[0], str) or type(row[1]) is not int or row[1] < 0 for row in pains):
        raise ValueError("Expected native pain frequencies")
    return h("div", {"class_": "sl-research-memory-summary"},
             h("p", {}, persona["display_name"], " · ", persona["id"]),
             h("p", {}, (period.get("start") or "—"), " → ", (period.get("end") or "—"), " · ", period["lens"]),
             count_rows([(t("rmo_days"), value["days"]), (t("rmo_events"), value["events"])]),
             h("section", {}, h("h3", {}, t("pain_points")), count_rows(pains)) if pains else None,
             _list(t("completed"), value["completed"]), _list(t("rmo_blockers"), value["blockers"]),
             _list(t("open_loops"), value["open_loops"]),
             h("p", {"class_": "sl-research-meta"}, t("rmo_summary_selection")))


def summary(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    body = summary_content(value)
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rmo_experience")), body), (
        "ready" if value["events"] or value["days"] else "empty")


def pain_content(values, *, passive=False):
    """The product's existing Finding primitive, with supplied evidence only."""
    from ..artifacts import pain_point_finding
    from ..web._render import render_findings
    if not isinstance(values, list):
        raise ValueError("Expected native pain observations")
    if passive:
        for value in values:
            _record(value, ("id", "persona_id", "issue", "affected_workflow", "opportunity", "created_at"),
                    ("severity", "frequency"), ("evidence_event_ids",))
    return render_findings([pain_point_finding(value) for value in values], passive=passive)


def pain_points(values):
    from ..web._i18n import t
    h, _, _ = _kit()
    # Passive cards require full observations; the product keeps legacy Finding compatibility.
    pain_content(values, passive=True)
    cards = []
    for value in values:
        cards.append(h("article", {"class_": "sl-research-card"}, h("h2", {}, t("pain_points")),
            h("p", {"class_": "sl-research-meta"}, value["persona_id"], " · ", value["id"], " · ", value["created_at"]),
            pain_content([value], passive=True),
            count_rows([(t("rmo_severity"), value["severity"]), (t("rmo_frequency"), value["frequency"])]),
            h("p", {}, t("rmo_workflow"), ": ", value["affected_workflow"]),
            h("p", {"class_": "sl-research-meta"}, t("rmo_no_evidence")) if not value["evidence_event_ids"] else None))
    return collection(cards, empty=t("rmo_pains_empty")), "ready" if cards else "empty"


def _processing(label, value, counts, body=None):
    from ..web._i18n import t
    h, _, _ = _kit()
    _record(value, ("persona_id",))
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, label),
             h("p", {"class_": "sl-research-meta"}, value["persona_id"], " · ", value.get("date", value.get("month", ""))),
             count_rows(counts), body, h("p", {"class_": "sl-research-meta"}, t("rmo_processing_notice"))), "ready"


def consolidation(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    pairs = [("entities_created", t("rmo_entities_created")), ("entities_updated", t("rmo_entities_updated")),
             ("facts", t("rmo_facts_processed")), ("threads_opened", t("rmo_threads_opened")),
             ("threads_resolved", t("rmo_threads_resolved")), ("event_links", t("rmo_event_links"))]
    _record(value, ("persona_id", "date"), [key for key, _ in pairs])
    embeddings = _record(value.get("embeddings"), counts=("embedded", "skipped_existing", "disabled"))
    body = h("section", {}, h("h3", {}, t("rmo_embeddings")), count_rows([
        (t("rmo_embedded"), embeddings["embedded"]), (t("rmo_skipped"), embeddings["skipped_existing"]),
        (t("rmo_disabled"), embeddings["disabled"])]))
    return _processing(t("rmo_consolidation"), value, [(label, value[key]) for key, label in pairs], body)


def day(value):
    from ..web._i18n import t
    _record(value, ("persona_id", "date"), ("activities",))
    counts = [(t("rmo_activities"), value["activities"])]
    for key, label in (("entities", t("rmo_entities_created")), ("facts", t("rmo_facts_processed"))):
        if key in value:
            _record(value, counts=(key,))
            counts.append((label, value[key]))
    return _processing(t("rmo_day_recorded"), value, counts)


def month(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    _record(value, ("persona_id", "month"), ("sample_days",))
    if not isinstance(value.get("days"), list):
        raise ValueError("Expected native sampled day receipts")
    rows = []
    for item in value["days"]:
        _record(item, ("date",), ("activities", "entities", "facts"))
        rows.append(h("section", {}, h("h3", {}, item["date"]), count_rows([
            (t("rmo_activities"), item["activities"]), (t("rmo_entities_created"), item["entities"]),
            (t("rmo_facts_processed"), item["facts"])])))
    return _processing(t("rmo_month_recorded"), value, [(t("rmo_sample_days"), value["sample_days"])], rows)

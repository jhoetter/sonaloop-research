"""Native graph inventory using the Product outline's shared semantic row cells.

The Product supplies its own media, relationships and formatted dates. Passive
rows use only supplied native values, never the Product's enriched graph.
"""
from __future__ import annotations

from .library import _kit, collection, section_card
from .projects_rows import record, texts, identity, strings, count, fields, project_heading, disclosure, t


def outline_cells(title, *, lead=None, relations=None, crew=None, timestamp=None, passive=False):
    """The five cells of the real Product row; prepared fragments stay explicit."""
    h, _, _ = _kit()
    return [lead, h("span", {"class_": "sl-research-outline-title" if passive else "ol-title"}, title), relations, crew,
            h("span", {"class_": "sl-research-outline-time" if passive else "ol-ts"}, timestamp)]


def records(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected native graph record rows")
    return value


def counts(value, *, stance=False):
    record(value)
    for key, number in value.items():
        if not ((type(key) is str and key) or (stance and type(key) is int)):
            raise ValueError("Expected native count label")
        count(number)
    return fields(value.items())


def node_content(value):
    h, fragment, _ = _kit()
    identity(value, "study_id")
    texts(value, ("title",), ("kind", "kind_label", "created_at", "phase", "href", "status"))
    people = records(value.get("personas", []))
    for person in people:
        identity(person, "id")
        texts(person, (), ("display_name",))
    pairs = [("study_id", value["study_id"])]
    for key in ("kind", "phase", "status", "href", "mode", "role"):
        if key in value:
            texts(value, (key,))
            pairs.append((key, value[key]))
    for key in ("voices", "council_count", "recommendations", "n_sessions", "n_sections", "n_statements", "n_findings"):
        if key in value:
            count(value[key]); pairs.append((key, value[key]))
    # Supplied voices are not replaced by the number of available Persona stubs.
    crew = h("span", {"class_": "sl-research-graph-personas"}, "; ".join(
        (person.get("display_name") or person["id"]) + " · " + person["id"] for person in people)) if people else None
    cells = outline_cells(value["title"], lead=h("span", {}, value.get("kind_label") or value.get("kind", "")),
        crew=None, timestamp=None, passive=True)
    extras = []
    for key in ("sentiment", "stance_counts"):
        if key in value:
            extras.append(h("div", {}, h("h4", {}, key), counts(value[key], stance=key == "stance_counts")))
    for key in ("theme_tags", "prototype_ids", "council_ids"):
        if key in value:
            extras.append(h("p", {}, key, ": ", ", ".join(strings(value[key]))))
    return h("article", {"class_": "sl-research-card sl-research-graph-node"},
             h("div", {"class_": "sl-research-graph-row"}, fragment(cells)),
             h("p", {"class_": "sl-research-status"}, value.get("status", "")),
             disclosure(t("rpx_record_details"), crew, fields(pairs),
                h("p", {}, value.get("created_at", "")), extras))


def question_content(value, *, prepared_text=None, passive=True):
    """One recorded question; Product prepares its optional long-text control.

    Native presentation requires a supplied status. HMW reframe rows have their
    own body and cannot become open-question records by rendering them here.
    """
    if passive and prepared_text is not None:
        raise ValueError("Passive questions cannot accept prepared Product HTML")
    identity(value, "id"); texts(value, ("text", "status"), ("created_at", "project_id"))
    if value.get("study_id") is not None:
        texts(value, ("study_id",))
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-question-content"},
        h("div", {"class_": "sl-prose"}, prepared_text if prepared_text is not None else h("p", {}, value["text"])),
        disclosure(t("rpx_record_details"), fields((key, "null" if value[key] is None else value[key])
            for key in ("id", "status", "project_id", "study_id", "created_at") if key in value)))


def questions_content(value, *, heading="h3"):
    h, _, _ = _kit()
    if heading not in {"h2", "h3"}:
        raise ValueError("Expected a question group heading")
    cards = []
    for row in records(value):
        body = question_content(row)
        # The Product inspector already has its status pill outside this body.
        # Native groups show the same supplied status beside each question.
        status = {"open": t("oq_status_open"), "resolved": t("oq_status_resolved")}.get(row["status"], row["status"])
        cards.append(h("li", {}, h("p", {"class_": "sl-research-status"}, status), body))
    return h("div", {}, h(heading, {}, t("open_questions_h")),
             h("ul", {}, cards) if cards else h("p", {"class_": "sl-research-empty"}, t("rpg_no_questions")))


def _native_questions(value):
    rows = records(value)
    for row in rows:
        # The six fields are the actual OpenQuestion DTO. Unknown shapes must
        # retain the ordinary native result instead of silently dropping fields.
        if set(row) != {"id", "text", "status", "project_id", "study_id", "created_at"}:
            raise ValueError("Expected the complete native OpenQuestion record")
        identity(row, "project_id")
    return rows


def recorded_questions(value):
    record(value)
    if set(value) != {"open_questions"}:
        raise ValueError("Expected the native recorded-questions envelope")
    rows = _native_questions(value["open_questions"])
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, questions_content(rows, heading="h2")), "ready" if rows else "empty"


def frontier(value):
    record(value); identity(value, "project_id")
    if set(value) != {"project_id", "open_questions", "open_question_count", "notes"}:
        raise ValueError("Expected the native research frontier")
    rows = _native_questions(value["open_questions"])
    count(value["open_question_count"]); strings(value["notes"])
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rq_frontier")),
        fields(((t("rq_open_count"), value["open_question_count"]),)), questions_content(rows),
        h("section", {}, h("h3", {}, t("rq_notes")), h("ul", {}, [h("li", {}, note) for note in value["notes"]]))
            if value["notes"] else None,
        disclosure(t("rpx_record_details"), fields((("project_id", value["project_id"]),)))), "ready" if rows else "empty"


def _edges(value):
    h, _, _ = _kit()
    items = []
    for edge in records(value):
        texts(edge, ("from_study", "to_study", "type"), ("rationale",))
        items.append(h("li", {}, h("code", {}, edge["from_study"]), " → ", h("code", {}, edge["to_study"]),
            fields((("type", edge["type"]),)), h("p", {}, edge.get("rationale", ""))))
    return h("div", {}, h("h3", {}, t("relations")), h("ul", {}, items) if items
             else h("p", {"class_": "sl-research-empty"}, t("rpg_no_edges")))


def graph(value):
    from . import assets, references, prototypes
    h, fragment, _ = _kit()
    record(value); project = record(value.get("project")); identity(project, "id")
    texts(project, ("title", "goal"))
    nodes = records(value.get("nodes")); grouped = {}
    for node in nodes:
        texts(node, (), ("phase",))
        grouped.setdefault(node.get("phase", ""), []).append(node_content(node))
    # Literal native phase grouping only; unknown phases cannot drop a node.
    groups = [h("section", {}, h("h3", {}, phase or t("rpg_no_phase")), fragment(cards))
              for phase, cards in grouped.items()]
    sections = [section_card(row) for row in records(value.get("sections", []))]
    attachments = []
    for key, render in (("assets", assets.asset), ("artifacts", references.reference), ("prototypes", prototypes.prototype)):
        rows = records(value.get(key, []))
        if rows:
            attachments.append(h("section", {}, h("h3", {}, key), [render(row)[0] for row in rows]))
    reports = []
    for row in [*records(value.get("reports", [])), *records(value.get("job_outcomes", []))]:
        identity(row, "id"); texts(row, ("title",), ("created_at", "status"))
        pairs = [(key, row[key]) for key in ("id", "status", "created_at") if key in row]
        if "n_sections" in row:
            count(row["n_sections"]); pairs.append(("n_sections", row["n_sections"]))
        for key in ("schema_id", "result_kind", "source_study_ids", "legacy_citation_study_ids"):
            if key in row:
                if key.endswith("_ids"):
                    pairs.append((key, ", ".join(strings(row[key]))))
                else:
                    texts(row, (key,)); pairs.append((key, row[key]))
        reports.append(h("article", {"class_": "sl-research-card"}, h("h3", {}, row["title"]), fields(pairs)))
    order = strings(value.get("build_order", []))
    return h("article", {"class_": "sl-research-card sl-research-graph"},
        project_heading(project, level="h2"),
        disclosure(t("rpx_inventory"), fields((("project_id", project["id"]),)),
            h("p", {"class_": "sl-research-meta"}, t("rpg_scope")), counts(value.get("counts"))),
        collection(groups, empty=t("rpg_no_nodes")), disclosure(t("relations"), _edges(value.get("edges"))),
        questions_content(value.get("open_questions")),
        disclosure(t("rpg_build_order"), h("ol", {}, [h("li", {}, x) for x in order])),
        sections, attachments, reports), "ready"

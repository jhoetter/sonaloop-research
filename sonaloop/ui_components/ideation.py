"""Supplied HMW questions, attributed Notes and ranked Council ideation.

The writer has a Council transcript; the getter does not. Product inspectors
and passive results share the question, Note and ideation bodies without reads.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .library import _kit, collection
from .projects_rows import disclosure, fields, t


TOOLS = {"record_hmw_reframe", "record_ideas", "list_ideas",
         "record_ideation_summary", "get_ideation"}


def _object(value):
    if type(value) is not dict:
        raise ValueError("Expected a supplied ideation object")
    return value


def _rows(value):
    if type(value) is not list:
        raise ValueError("Expected supplied ideation rows")
    for row in value:
        _object(row)
    return value


def _text(value, *names):
    if any(type(value.get(name)) is not str for name in names):
        raise ValueError("Expected supplied ideation text")


def _json(value, depth=0):
    """Validate supplemental native fields, including explicit empty/null values."""
    if depth > 12:
        raise ValueError("Ideation details exceed the presentation depth")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError("Expected a named native ideation field")
            _json(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _json(child, depth + 1)
    elif value is not None and (type(value) not in (str, int, float, bool)
                               or type(value) is float and not math.isfinite(value)):
        raise ValueError("Unsupported native ideation detail")


def _details(value):
    """Named native metadata, never a JSON-only substitute for the domain body."""
    h, _, _ = _kit()
    if type(value) is dict:
        return h("dl", {}, [h("div", {}, h("dt", {}, key), h("dd", {}, _details(item)))
                            for key, item in value.items()]) if value else h("span", {}, "{}")
    if type(value) is list:
        return h("ol", {}, [h("li", {}, _details(item)) for item in value]) if value else h("span", {}, "[]")
    return h("span", {}, "null" if value is None else str(value).lower() if type(value) is bool else str(value))


def public_value(name, value):
    """Copy the actual result without changing its native fields.

    The MCP summary writer accepts no dispatch token. Its native contexts carry
    only state/checkpoint/provenance. A future different context fails explicitly
    instead of silently filtering authored values or publishing execution grants.
    """
    if name not in TOOLS:
        raise ValueError("Unknown ideation projection")
    value = deepcopy(_object(value))
    if name == "record_ideation_summary":
        context = _object(value.get("dispatch"))
        _text(context, "state", "provenance")
        if set(context) != {"state", "checkpointed", "provenance"} or type(context["checkpointed"]) is not bool:
            raise ValueError("Unsupported native ideation dispatch context")
        provenance = _object(value.get("dispatch_provenance"))
        _text(provenance, "state")
        if set(provenance) != {"state"}:
            raise ValueError("Unsupported native ideation provenance context")
    _json(value)
    return value


def attribution_content(value):
    """Optional supplied Note attribution; no Persona or HMW resolution."""
    value = _object(value)
    for key in ("persona_id", "hmw_ref", "hmw_question", "cluster"):
        if key in value and value[key] is not None:
            _text(value, key)
    h, _, _ = _kit()
    labels = {"persona_id": t("rid_persona"), "hmw_ref": t("rid_hmw_ref"), "cluster": t("rid_cluster")}
    pairs = [(label, "null" if value[key] is None else value[key]) for key, label in labels.items() if key in value]
    return disclosure(t("rid_attribution"),
        h("p", {}, value["hmw_question"]) if "hmw_question" in value else None,
        fields(pairs)) if pairs or "hmw_question" in value else ""


def hmw_content(value):
    """The same recorded questions in a reframe and a Council's ideation block."""
    h, _, _ = _kit()
    cards = []
    for row in _rows(value):
        _text(row, "id", "question")
        if "hypothesis_id" in row and row["hypothesis_id"] is not None:
            _text(row, "hypothesis_id")
        if set(row) - {"id", "question", "hypothesis_id"}:
            raise ValueError("Unsupported HMW question fields")
        cards.append(h("li", {}, h("p", {}, row["question"]),
            disclosure(t("rid_record_details"), fields((("id", row["id"]),)),
                fields(((t("rid_hypothesis"), "null" if row["hypothesis_id"] is None else row["hypothesis_id"]),))
                if "hypothesis_id" in row else None)))
    return h("div", {"class_": "sl-research-hmw"}, h("ul", {}, cards) if cards
             else h("p", {"class_": "sl-research-empty"}, t("rid_no_questions")))


def _idea(value, *, ranked=False):
    value = _object(value)
    _text(value, "idea_id" if ranked else "id", "text", "persona_id", "hmw_ref")
    if "cluster" in value and value["cluster"] is not None:
        _text(value, "cluster")
    if ranked:
        _text(value, "rationale")
        if type(value.get("rank")) is not int or value["rank"] < 1:
            raise ValueError("Expected a recorded positive idea rank")
    _json(value)
    return value


def _idea_content(value, *, ranked=False):
    from .library import note_content
    value = _idea(value, ranked=ranked)
    h, _, _ = _kit()
    attribution = {key: value[key] for key in ("persona_id", "hmw_ref", "cluster") if key in value}
    extras = {key: item for key, item in value.items()
              if key not in {"text", "persona_id", "hmw_ref", "cluster", "rationale"}}
    return h("li", {"value": value["rank"]} if ranked else {},
        note_content({"text": value["text"]}, attribution=attribution),
        h("p", {}, h("strong", {}, t("rid_rationale"), ": "), value["rationale"]) if ranked else None,
        disclosure(t("rid_record_details"), _details(extras)))


def ideation_content(value):
    """Semantic body shared by the existing Council inspector and both results."""
    value = _object(value)
    _text(value, "problem", "recorded_at")
    if set(value) - {"problem", "recorded_at", "hmw", "ideas", "shortlist"}:
        raise ValueError("Unsupported stored ideation fields")
    h, _, _ = _kit()
    pool = [_idea_content(row) for row in _rows(value.get("ideas"))]
    shortlist = [_idea_content(row, ranked=True) for row in _rows(value.get("shortlist"))]
    return h("div", {"class_": "sl-research-ideation"},
        h("p", {}, h("strong", {}, t("rid_problem"), ": "), value["problem"]),
        h("h3", {}, t("rid_shortlist")), h("ol", {}, shortlist) if shortlist else h("p", {}, t("rid_no_shortlist")),
        disclosure(t("rid_reframe"), hmw_content(value.get("hmw"))),
        disclosure(t("rid_ideas"), h("ul", {}, pool) if pool else h("p", {}, t("rid_no_ideas"))),
        disclosure(t("rid_record_details"), fields(((t("rid_recorded"), value["recorded_at"]),))))


def reframe(value):
    value = public_value("record_hmw_reframe", value)
    _text(value, "schema", "project_id", "problem", "next")
    if value["schema"] != "hmw_reframe" or set(value) != {"schema", "project_id", "problem", "hmw", "next"}:
        raise ValueError("Expected the actual HMW reframe result")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rid_reframe")),
        h("p", {}, value["problem"]), hmw_content(value["hmw"]),
        disclosure(t("rid_next"), h("p", {}, value["next"])),
        disclosure(t("rid_record_details"), fields((key, value[key]) for key in ("schema", "project_id")))), "ready"


def ideas(value):
    from .library import note_card
    value = public_value("list_ideas", value)
    if set(value) != {"ideas"}:
        raise ValueError("Expected the actual idea list envelope")
    cards = []
    for row in _rows(value.get("ideas")):
        _text(row, "id", "title", "text", "kind", "created_at")
        data = _object(row.get("data"))
        _text(data, "persona_id", "hmw_ref")
        # Fail passive rendering on malformed attribution while the Product can
        # still inspect the original Note text through its optional fallback.
        attribution_content({**data, **({"hmw_question": row["hmw_question"]} if "hmw_question" in row else {})})
        h, _, _ = _kit()
        cards.append(h("div", {}, note_card(row), disclosure(t("rid_record_details"),
            _details({key: item for key, item in row.items() if key not in {"title", "text", "hmw_question"}}))))
    return collection(cards, empty=t("rid_no_ideas")), "ready" if cards else "empty"


def _citation(value):
    ref = _object(value)
    _text(ref, "kind", "id", "role")
    return disclosure(t("rid_citation"), _details(ref))


def recorded(value):
    from .councils import council
    value = public_value("record_ideation_summary", value)
    _, fragment, _ = _kit()
    content = ideation_content(value.get("ideation"))
    # This is the supplied full Council, including its real voices/findings.
    body, state = council(value, format_content=content)
    return fragment(body, _citation(value.get("cite_as")),
        disclosure(t("rid_warnings"), _details(value["warnings"])) if "warnings" in value else None,
        disclosure(t("rid_record_details"), _details({key: item for key, item in value.items()
            if key not in {"ideation", "cite_as", "warnings"}}))), state


def stored(value):
    value = public_value("get_ideation", value)
    _text(value, "id", "prompt", "project_id", "created_at")
    allowed = {"id", "prompt", "project_id", "created_at", "cite_as", "problem", "hmw", "ideas", "shortlist", "recorded_at"}
    if set(value) != allowed:
        raise ValueError("Expected the actual flat ideation getter")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("rid_ideation")),
        ideation_content({key: value[key] for key in ("problem", "hmw", "ideas", "shortlist", "recorded_at")}),
        _citation(value["cite_as"]), disclosure(t("rid_record_details"),
            fields((key, value[key]) for key in ("id", "prompt", "project_id", "created_at")))), "ready"

"""Explicit tool/result projections; no tool execution or runtime lookups."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .library import collection, note_card, section_card
from . import bets, councils, discovery, surveys

SCHEMA = "sonaloop.research-presentation.v1"


@dataclass(frozen=True)
class Surface:
    family: str
    render: Callable

    @property
    def component_id(self):
        return f"sonaloop.research.{self.family}-view"

    @property
    def uri(self):
        return f"ui://sonaloop/{self.family}/v1"


def _record(value):
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        raise ValueError("Expected a native record")
    return value


def _note(value):
    record = _record(value)
    if not isinstance(record.get("text"), str):
        raise ValueError("Expected native note text")
    return note_card(record), "ready"


def _notes(value):
    from ..web._i18n import t
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("Expected native note page")
    cards = [_note(item)[0] for item in value["items"]]
    return collection(cards, empty=t("no_notes"), total=value.get("total"), has_more=value.get("has_more", False)), "ready" if cards else "empty"


def _section(value):
    record = _record(value)
    if not isinstance(record.get("member_ids"), list):
        raise ValueError("Expected native section membership")
    return section_card(record), "ready"


def _sections(value):
    from ..web._i18n import t
    if not isinstance(value, list):
        raise ValueError("Expected native section list")
    cards = [_section(item)[0] for item in value]
    return collection(cards, empty=t("no_members")), "ready" if cards else "empty"


def _members(value):
    if not isinstance(value, dict) or not isinstance(value.get("members"), list):
        raise ValueError("Expected native resolved members")
    return section_card(_record(value.get("section")), value["members"]), "ready" if value["members"] else "empty"


SURFACES = {
    "record_survey": Surface("surveys", surveys.survey_write),
    "get_survey": Surface("surveys", surveys.survey),
    "list_surveys": Surface("surveys", surveys.surveys),
    "survey_results": Surface("surveys", surveys.survey_results),
    "import_survey_responses": Surface("surveys", surveys.imported),
    **{name: Surface("councils", councils.council) for name in ("record_council", "get_council")},
    "list_councils": Surface("councils", councils.councils),
    **{name: Surface("hypotheses", bets.hypothesis_write) for name in (
        "record_hypothesis", "record_hypothesis_result", "drop_hypothesis")},
    "get_hypothesis": Surface("hypotheses", bets.hypothesis),
    "list_hypotheses": Surface("hypotheses", bets.hypotheses),
    **{name: Surface("decisions", bets.decision_write) for name in ("record_decision", "update_decision")},
    "get_decision": Surface("decisions", bets.decision),
    "list_decisions": Surface("decisions", bets.decisions),
    "create_research_project": Surface("projects", discovery.project),
    "list_research_projects": Surface("projects", discovery.projects),
    "search": Surface("search", discovery.search),
    "fetch": Surface("search", discovery.fetched),
    **{name: Surface("notes", _note) for name in ("create_note", "set_note_data")},
    "list_notes": Surface("notes", _notes),
    **{name: Surface("sections", _section) for name in (
        "create_section", "update_section", "add_to_section", "remove_from_section", "set_section_members", "get_section")},
    "list_sections": Surface("sections", _sections),
    "get_section_members": Surface("sections", _members),
}


def render_tool(name: str, value):
    """Only a successful native envelope may supply a card. No inferred records."""
    if name in {"search", "fetch"}:
        return SURFACES[name].render(value)
    if not isinstance(value, dict) or "data" not in value:
        raise ValueError("Expected native tool envelope")
    return SURFACES[name].render(value["data"])

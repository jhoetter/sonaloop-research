"""Explicit tool/result projections; no tool execution or runtime lookups."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .library import collection, note_card, section_card
from . import references, assets, prototypes, calendar, plans, bets, councils, council_formats, discovery, surveys, syntheses, sessions, session_funnels
from . import memory, memory_outcomes

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
    "list_active_projects": Surface("memory", memory.active_projects),
    "search_entities": Surface("memory", memory.entities),
    "resolve_entity": Surface("memory", memory.entity),
    "get_project": Surface("memory", memory.project),
    "get_state_at": Surface("memory", memory.state_at),
    "get_timeline": Surface("memory", memory.timeline),
    "get_open_loops": Surface("memory", memory.threads),
    "recall_memory": Surface("memory", memory.recall),
    "get_persona_memory": Surface("memory", memory.document),
    "export_persona_memory": Surface("memory", memory.exported),
    "record_memory_deltas": Surface("memory", memory_outcomes.consolidation),
    "put_digest": Surface("memory", memory_outcomes.digest),
    "list_digests": Surface("memory", memory_outcomes.digests),
    "record_day": Surface("memory", memory_outcomes.day),
    "record_month_bundle": Surface("memory", memory_outcomes.month),
    "summarize_persona_period": Surface("memory", memory_outcomes.summary),
    "extract_pain_points": Surface("memory", memory_outcomes.pain_points),
    **{name: Surface("plans", plans.plan) for name in (
        "put_day_plan", "get_day_plan", "put_period_plan", "get_period_plan")},
    "list_period_plans": Surface("plans", plans.plans),
    "get_current_state": Surface("calendar", calendar.current_state),
    "get_calendar": Surface("calendar", calendar.calendar),
    "get_calendar_period": Surface("calendar", calendar.calendar_period),
    "get_activity": Surface("calendar", calendar.activity),
    **{name: Surface("prototypes", prototypes.prototype) for name in (
        "scaffold_prototype", "register_prototype", "get_prototype")},
    "register_remote_prototype": Surface("prototypes", prototypes.registered_remote),
    "list_prototypes": Surface("prototypes", prototypes.prototypes),
    "run_prototype": Surface("prototypes", prototypes.running),
    "stop_prototype": Surface("prototypes", prototypes.stopped),
    "delete_prototype": Surface("prototypes", prototypes.removed),
    "record_head_to_head": Surface("councils", council_formats.head_to_head_write),
    "get_head_to_head": Surface("councils", council_formats.head_to_head),
    "record_price_ladder": Surface("councils", council_formats.price_ladder_write),
    "get_price_ladder": Surface("councils", council_formats.price_ladder),
    "price_ladder_analysis": Surface("councils", council_formats.price_analysis),
    "record_red_team": Surface("councils", council_formats.red_team_write),
    "get_red_team": Surface("councils", council_formats.red_team),
    "query_councils": Surface("councils", council_formats.query_councils),
    **{name: Surface("references", references.reference) for name in ("add_artifact", "get_artifact")},
    "list_artifacts": Surface("references", references.references),
    "delete_artifact": Surface("references", references.removed),
    **{name: Surface("assets", assets.asset) for name in (
        "attach_asset", "attach_prototype_shot", "admit_remote_screenshot", "get_asset")},
    "list_assets": Surface("assets", assets.assets),
    "remove_asset": Surface("assets", assets.removed),
    **{name: Surface("syntheses", syntheses.synthesis) for name in (
        "record_synthesis", "get_synthesis", "record_synthesis_outline", "record_synthesis_section")},
    "list_syntheses": Surface("syntheses", syntheses.syntheses),
    "record_usability_session": Surface("sessions", sessions.session_write),
    "get_usability_session": Surface("sessions", sessions.session),
    "list_usability_sessions": Surface("sessions", sessions.sessions),
    "record_prototype_session": Surface("sessions", sessions.prototype_session_write),
    **{name: Surface("sessions", session_funnels.funnel) for name in ("get_session_funnel", "flow_funnel")},
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

"""One statement body/grouping renderer over explicitly prepared presentation data.

Rows carry their reference fragments through grouping by position, so legacy
statements without IDs cannot accidentally share another statement's sources.
No Store, avatar lookup, resolver callback or runtime filesystem belongs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .library import _kit


@dataclass(frozen=True)
class StatementPresentation:
    statement: dict
    persona: dict | None = None
    avatar: Any = None
    references: Any = None
    quotes: Any = None
    backlinks: Any = None
    stance: Any = None
    grounded: Any = None
    posture: Any = None


def _classes(base: str, marker: str, passive: bool):
    return f"{base} sl-research-{marker}" if passive else base


def statement_body(row: StatementPresentation, *, clamp_at: int | None = None, passive: bool = False):
    from ..web import ui
    from ..web._components import _icon, _prose
    from ..web._i18n import t
    h, fragment, raw = _kit()
    st = row.statement
    meta = st.get("meta") or {}
    focus = h("p", {"class_": "muted small", "style": "font-style:italic;margin:0 0 4px"}, meta["focus"]) if meta.get("focus") else None
    given = None
    if meta.get("input"):
        given = (h("div", {"class_": "sl-research-input"}, h("p", {"class_": "muted small"}, t("council_input_given")),
                   h("p", {}, meta["input"])) if passive else
                 h("details", {"class_": "turn-input"}, h("summary", {"class_": "muted small"}, t("council_input_given")),
                   h("p", {"class_": "muted small", "style": "white-space:pre-wrap"}, meta["input"])))
    questions = meta.get("pushback") or []
    pushback = fragment(*(h("p", {"class_": "muted small"}, f"• {q}") for q in (questions if passive else questions[:4])))
    shift = st.get("shift") or {}
    shift_html = h("p", {"class_": "muted small"}, None if passive else raw(_icon("exchange")), " ",
                   f'{shift.get("from", "")} → {shift.get("to", "")}',
                   f' · {shift["trigger"]}' if shift.get("trigger") else "") if shift else None
    attrs = {"class_": _classes("turn-ans", "statement-body", passive)}
    if st.get("id"):
        attrs["id"] = st["id"]
    prose = raw(_prose(st.get("text", "")))
    text = h("div", {"class_": _classes("turn-text", "statement-text", passive)},
             ui.clamp(prose, threshold=clamp_at) if clamp_at and not passive else h("p", {}, prose))
    badges = h("div", {"class_": "sl-research-statement-head"}, row.stance, row.grounded, row.posture) if passive and any(
        (row.stance, row.grounded, row.posture)) else None
    context = h("p", {"class_": "muted small"}, meta["context"]) if passive and meta.get("context") else None
    return h("div", attrs, badges, context, focus, given, text, pushback, shift_html, row.quotes, row.references, row.backlinks)


def persona_card(rows: list[StatementPresentation], *, head_extra=None, show_persona=True,
                 clamp_at: int | None = None, passive: bool = False):
    h, fragment, _ = _kit()
    first = rows[0]
    head_st, person = first.statement, first.persona
    pid = head_st.get("persona_id", "")
    who = context_html = None
    if show_persona:
        name = (person or {}).get("display_name") or pid or "—"
        segment = (person or {}).get("segment") or {}
        context = ((head_st.get("meta") or {}).get("context")
                   or " · ".join(x for x in [segment.get("lebensphase"), segment.get("einstellung")] if x)[:130]
                   or ((person or {}).get("source_description") or "")[:130])
        who = (h("a", {"href": f'/personas/{person["id"]}', "class_": "turn-who"}, first.avatar, h("b", {}, name))
               if person and not passive else h("span", {"class_": "turn-who"}, h("b", {}, name)))
        context_html = h("div", {"class_": "muted small turn-ctx"}, context) if context and not passive else None
    stance = next((row.stance for row in rows if row.statement.get("stance")), None)
    relevance = head_st.get("relevance")
    relevance_html = h("span", {"class_": "muted small"}, f" · {relevance}") if relevance else None
    head = h("div", {"class_": _classes("hd", "statement-head", passive)}, who, " " if who else "",
             None if passive else stance, None if passive else first.grounded, None if passive else first.posture,
             head_extra, relevance_html, context_html)
    return h("div", {"class_": _classes("turn" + ("" if show_persona else " turn-bare"), "statement", passive)},
             head, fragment(*(statement_body(row, clamp_at=clamp_at, passive=passive) for row in rows)))


def _by_persona(rows: list[StatementPresentation]):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.statement.get("persona_id"), []).append(row)
    return list(grouped.values())


def render_statements(rows: list[StatementPresentation], *, group_by: str = "persona", prompts: list | None = None,
                      prompt_headers: list | None = None, further_header=None, clamp_at: int | None = None,
                      collapsible: bool = False, passive: bool = False):
    h, fragment, raw = _kit()
    prompts, prompt_headers = prompts or [], prompt_headers or []
    if len(prompts) != len(prompt_headers):
        raise ValueError("Every prompt requires its supplied header presentation")

    def cards(group):
        return fragment(*(persona_card(part, clamp_at=clamp_at, passive=passive) for part in _by_persona(group)))

    def round_group(header, group):
        answers = h("div", {"class_": _classes("qround-a", "round-answers", passive)}, cards(group))
        if collapsible and not passive:
            return h("details", {"class_": "qround", "open": True},
                     h("summary", {}, raw(header), h("span", {"class_": "qround-cnt"},
                       str(len({row.statement.get("persona_id") for row in group})))), answers)
        return h("div", {"class_": _classes("qround", "round", passive)}, raw(header), answers)

    if group_by == "prompt" and prompts:
        ids = {p.get("id") for p in prompts}
        single = len(prompts) == 1
        rounds = []
        for prompt, header in zip(prompts, prompt_headers, strict=True):
            group = rows if single else [row for row in rows if (row.statement.get("about") or {}).get("id") == prompt.get("id")]
            if group:
                rounds.append(round_group(header, group))
        rest = [] if single else [row for row in rows if (row.statement.get("about") or {}).get("id") not in ids]
        if rest:
            rounds.append(round_group(further_header, rest))
        return h("div", {"class_": _classes("qrounds", "rounds", passive)}, fragment(*rounds))
    attrs = {"class_": "sl-research-voices"} if passive else {"style": "display:flex;flex-direction:column;gap:12px"}
    return h("div", attrs, cards(rows))

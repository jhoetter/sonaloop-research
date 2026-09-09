"""Persona calendar navigation; recorded bodies live in ui_components.calendar.

A persona's calendar visualises LIVED activity (a handful of events/day + a daily mood), not a
scheduling tool — so the views favour density + at-a-glance rhythm over a time-grid. Day exposes
the full native calendar blocks. Design follows the Linear/Notion-Calendar language: one accent, hairline grids (via a
1px-gap on a line-coloured container), muted out-of-scope days, today as a filled disc / accent ring.
"""
from __future__ import annotations

from datetime import date, timedelta

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from ._ctx import services, t, h, fragment
from ...ui_components.calendar import _event_chip  # legacy public web export

def _monf() -> list[str]:
    return t("cal_mon_long").split(",")


def _today() -> str:
    try:
        return date.today().isoformat()
    except Exception:                      # date.today is unavailable in some harness contexts
        return ""


def _shift(a: date, view: str, delta: int) -> date:
    if view == "day":
        return a + timedelta(days=delta)
    if view == "week":
        return a + timedelta(days=7 * delta)
    if view == "year":
        return a.replace(year=a.year + delta)
    m = a.month - 1 + delta                                  # month: jump whole months, land on the 1st
    return date(a.year + m // 12, m % 12 + 1, 1)


def _period_title(view: str, period: dict) -> str:
    s = date.fromisoformat(period["period_start"]); e = date.fromisoformat(period["period_end"])
    monf = _monf()
    if view == "day":
        return f"{s.day}. {monf[s.month-1]} {s.year}"
    if view == "year":
        return str(s.year)
    if view == "week":
        if s.month == e.month:
            return f"{s.day}.–{e.day}. {monf[s.month-1]} {s.year}"
        return f"{s.day}. {monf[s.month-1]} – {e.day}. {monf[e.month-1]} {e.year}"
    return f"{monf[s.month-1]} {s.year}"


def _calendar_tabs(persona_id: str, selected_date: str, view: str, period: dict) -> str:
    """Calendar header: ‹ / today / › date navigation + the current-period title + the view switcher."""
    a = date.fromisoformat(period.get("anchor_date", selected_date))
    prev, nxt = _shift(a, view, -1).isoformat(), _shift(a, view, 1).isoformat()
    def go(d: str) -> str:
        return f"/personas/{persona_id}?date={d}&view={view}"
    labels = {"day": t("tab_day"), "week": t("tab_week"), "month": t("tab_month"), "year": t("tab_year")}
    tabs = [h("a", {"class_": "sl-tab" + (" is-active" if view == tab else ""),
                    "href": f"/personas/{persona_id}?date={selected_date}&view={tab}"}, labels[tab])
            for tab in ["day", "week", "month", "year"]]
    return h("div", {"class_": "sl-cal-nav"},
             h("div", {"class_": "sl-cal-nav-l"},
               h("a", {"class_": "sl-cal-arrow", "href": go(prev), "aria-label": t("pager_prev")}, "‹"),
               h("a", {"class_": "sl-cal-arrow", "href": go(nxt), "aria-label": t("pager_next")}, "›"),
               h("a", {"class_": "sl-cal-today", "href": go(_today())}, t("today")),
               h("span", {"class_": "sl-cal-title"}, _period_title(view, period))),
             h("div", {"class_": "sl-tabs sl-tabs--pill"}, *tabs))


def _period_calendar_html(persona_id: str, selected_date: str, view: str, period: dict) -> str:
    from ...ui_components.calendar import period_content
    return period_content(period, persona_id=persona_id, today=_today())

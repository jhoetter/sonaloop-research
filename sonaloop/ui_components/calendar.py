"""Shared recorded state, activities and calendar bodies; all context is explicit."""
from __future__ import annotations

from datetime import date, timedelta
import math

from .library import _kit, collection


def h(*args):
    return _kit()[0](*args)


def fragment(*args):
    return _kit()[1](*args)


def t(*args, **kwargs):
    from ..web._i18n import t as translate
    return translate(*args, **kwargs)


_EVT = {"meeting": "meeting", "focus": "focus", "admin": "admin", "interruption": "interruption",
        "decision": "meeting", "site_visit": "focus"}


# Day/month names follow the UI language — ONE comma-joined i18n key per table
# (cal_wd_short / cal_mon_short / cal_mon_long), split per request.
def _wd() -> list[str]:
    return t("cal_wd_short").split(",")


def _mon() -> list[str]:
    return t("cal_mon_short").split(",")


_POS = {"zufrieden", "produktiv", "fokussiert", "positiv", "gut"}
_NEG = {"gehetzt", "müde", "muede", "angespannt", "gestresst", "negativ", "erschöpft"}


def _evt_cls(ev: dict) -> str:
    return _EVT.get(ev.get("event_type", "focus"), "focus")


def _mood_cls(mood: str) -> str:
    m = (mood or "").strip().lower()
    return "pos" if m in _POS else "neg" if m in _NEG else "neu" if m else ""


def _event_chip(event: dict, *, passive=False) -> str:                          # used in week + month cells
    tm = event.get("timestamp", "")[11:16]
    attrs = {"class_": f'sl-cev {_evt_cls(event)} sl-research-calendar-event',
             "title": f'{tm} · {event.get("task", "")}' }
    if not passive:
        attrs["href"] = f'/activities/{event.get("id", "")}'
    return h("div" if passive else "a", attrs,
             h("span", {"class_": "sl-cev-t"}, tm), event.get("task", ""),
             h("div", {"class_": "sl-research-meta"}, event.get("id", ""), " · ",
               event.get("event_type", ""), " · ", event.get("tool", ""), " · ",
               event.get("timestamp", "")) if passive else None)



def _week_html(persona_id: str, period: dict, summaries: dict, *, today="", passive=False) -> str:
    start = date.fromisoformat(period["period_start"]); days = period["days"]
    cols = []
    for i in range(7):
        d = start + timedelta(days=i); dk = d.isoformat()
        evs = sorted(days.get(dk, []), key=lambda e: e.get("timestamp", ""))
        mood = summaries.get(dk, "")
        if passive and not evs and not mood:
            continue
        head = h("div", {"class_": "sl-cw-h" + (" today" if dk == today else "") + (" we" if i >= 5 else "")},
                 h("div", {"class_": "sl-cw-wd"}, _wd()[i]),
                 h("div", {"class_": "sl-cw-d"}, dk if passive else str(d.day)),
                 h("span", {"class_": f"sl-cw-mood {_mood_cls(mood)}", "title": mood}, mood if passive else None) if mood else "")
        body = (fragment(*(_event_chip(e, passive=passive) for e in evs)) if evs
                else h("div", {"class_": "sl-cw-empty"}, "—"))
        cols.append(h("div", {"class_": "sl-cw-col sl-research-calendar-day" + (" we" if i >= 5 else "")}, head,
                     h("div", {"class_": "sl-cw-body"}, body)))
    return h("div", {"class_": "sl-cal-week sl-research-calendar-week"}, *cols)


def _month_html(persona_id: str, period: dict, summaries: dict, anchor: date, *, today="", passive=False) -> str:
    first = date.fromisoformat(period["period_start"]); last = date.fromisoformat(period["period_end"])
    days = period["days"]
    grid_start = first - timedelta(days=first.weekday())          # Monday on/before the 1st
    grid_end = last + timedelta(days=(6 - last.weekday()))        # Sunday on/after the last
    wd = _wd()
    cells = [] if passive else [h("div", {"class_": "sl-cm-wd" + (" we" if i >= 5 else "")}, wd[i]) for i in range(7)]
    d = grid_start
    while d <= grid_end:
        dk = d.isoformat(); out = d.month != anchor.month; we = d.weekday() >= 5
        evs = sorted(days.get(dk, []), key=lambda e: e.get("timestamp", ""))
        shown = [_event_chip(e, passive=passive) for e in (evs if passive else evs[:3])]
        more = (h("a", {"class_": "sl-cm-more", "href": f"/personas/{persona_id}?date={dk}&view=week"},
                 t("n_more", n=len(evs) - 3)) if len(evs) > 3 and not passive else "")
        mood = summaries.get(dk, "")
        if passive and not evs and not mood:
            d += timedelta(days=1)
            continue
        num_cls = "sl-cm-num" + (" today" if dk == today else "")
        cells.append(h("div", {"class_": "sl-cm-cell sl-research-calendar-day" + (" out" if out else "") + (" we" if we and not out else "")},
                       h("div", {"class_": num_cls}, dk if passive else str(d.day)),
                       fragment(*shown), more,
                       h("span", {"class_": f"sl-cm-mood {_mood_cls(mood)}"}, mood if passive else None) if (mood and not out) else ""))
        d += timedelta(days=1)
    return h("div", {"class_": "sl-cal-month sl-research-calendar-month"}, *cells)


def _year_html(persona_id: str, period: dict, anchor: date, *, today="", passive=False) -> str:
    """GitHub-style 53×7 activity heatmap — fill intensity = events that day; today = accent ring."""
    days = period["days"]; year = anchor.year
    jan1 = date(year, 1, 1); dec31 = date(year, 12, 31)
    grid_start = jan1 - timedelta(days=jan1.weekday())           # pad to a Monday so columns align
    n_weeks = ((dec31 - grid_start).days // 7) + 1
    # cells in column-major order (Mon→Sun per week) so grid-auto-flow:column lays them out right
    cells = []
    d = grid_start
    for _ in range(n_weeks * 7):
        if d < jan1 or d > dec31:
            cells.append(h("span", {"class_": "sl-cy-cell empty"}))
        else:
            n = len(days.get(d.isoformat(), []))
            lvl = 0 if n == 0 else 1 if n == 1 else 2 if n == 2 else 3 if n <= 4 else 4
            cls = f"sl-cy-cell l{lvl}" + (" today" if d.isoformat() == today else "")
            cells.append(h("a", {"class_": cls, "href": f"/personas/{persona_id}?date={d.isoformat()}&view=week",
                                 "title": f"{d.day}. {_mon()[d.month-1]} · {t('n_events', n=n)}"}))
        d += timedelta(days=1)
    # month labels: place each at the column where its 1st day falls
    mlabels = []
    for m in range(1, 13):
        col = (date(year, m, 1) - grid_start).days // 7
        mlabels.append(h("span", {"class_": "sl-cy-mon", "style": f"grid-column:{col+1}"}, _mon()[m - 1]))
    wd = _wd()
    wdcol = h("div", {"class_": "sl-cy-wd"}, *[h("span", {}, wd[i] if i in (0, 2, 4, 6) else "") for i in range(7)])
    legend = h("div", {"class_": "sl-cy-legend"}, h("span", {}, t("less")),
               *[h("span", {"class_": f"sl-cy-swatch l{l}"}) for l in range(5)], h("span", {}, t("more")))
    main = h("div", {"class_": "sl-cy-main"},
             h("div", {"class_": "sl-cy-mons", "style": f"grid-template-columns:repeat({n_weeks},11px)"}, *mlabels),
             h("div", {"class_": "sl-cy-grid"}, *cells))
    # legend lives OUTSIDE the horizontally-scrolling grid so it never clips/overlaps the weekday rail
    return fragment(h("div", {"class_": "sl-cal-year"}, wdcol, main), legend)


def _text_fields(value, required=(), optional=(), nullable=()):
    if not isinstance(value, dict):
        raise ValueError("Expected a native calendar record")
    for key in required:
        if not isinstance(value.get(key), str):
            raise ValueError(f"Expected native calendar {key}")
    for key in optional:
        if key in value and not isinstance(value[key], str):
            raise ValueError(f"Expected native calendar {key}")
    for key in nullable:
        if value.get(key) is not None and not isinstance(value[key], str):
            raise ValueError(f"Expected native calendar {key}")


def _strings(value, key):
    items = value.get(key, [])
    if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
        raise ValueError(f"Expected native calendar {key}")
    return items


def _person(value, *, nullable=False):
    if value is None and nullable:
        return
    _text_fields(value, ("id", "display_name"))


def _activity(value):
    _text_fields(value, ("id", "persona_id", "timestamp", "event_type", "task", "tool", "summary"),
                 ("what_happened", "created_at", "source_kind", "review_status"),
                 ("persona_thought", "collaboration_mode", "decision", "calendar_event_id"))
    for key in ("participants", "key_quotes", "actions_done", "artifacts_touched", "open_loops", "pain_points", "goal_refs"):
        _strings(value, key)
    for key in ("conversation", "source_refs"):
        if not isinstance(value.get(key, []), list):
            raise ValueError(f"Expected native activity {key}")
        for row in value.get(key, []):
            if key == "conversation":
                _text_fields(row, ("speaker", "text"))
            else:
                _text_fields(row, optional=("kind",), nullable=("id", "anchor", "role", "text", "quote"))
    impact = value.get("impact", {})
    if not isinstance(impact, dict) or any(not isinstance(k, str) or (
            v is not None and type(v) not in (str, int, float, bool)) or (
            type(v) is float and not math.isfinite(v)) for k, v in impact.items()):
        raise ValueError("Expected native activity impact measurements")
    confidence = value.get("confidence")
    if confidence is not None and (type(confidence) not in (float, int) or not math.isfinite(confidence)):
        raise ValueError("Expected native activity confidence")
    return value


def _section(label, items):
    return h("div", {"class_": "sec"}, h("h3", {}, label),
             h("ul", {}, [h("li", {}, item) for item in items])) if items else None


def _fields(rows):
    return h("dl", {"class_": "sl-research-fields"},
             [fragment(h("dt", {}, label), h("dd", {}, str(value).lower() if type(value) is bool else value))
              for label, value in rows if value is not None and value != ""])


def current_state_content(value, *, passive=False):
    _text_fields(value, ("persona_id", "display_name", "at_time", "current_activity", "synthetic_notice"),
                 nullable=("current_tool", "collaboration_mode", "mood", "current_thought"))
    if not {"blocked_by", "likely_next"} <= value.keys():
        raise ValueError("Expected native state blockers and likely-next items")
    blocked, likely = _strings(value, "blocked_by"), _strings(value, "likely_next")
    return h("div", {"class_": "sl-card sl-research-current-state"}, h("h3", {}, t("current_state")),
             h("p", {}, h("strong", {}, value["current_activity"])),
             h("p", {"class_": "muted small sl-research-meta"}, " · ".join(x for x in [
                 value.get("current_tool"), value.get("collaboration_mode"),
                 value.get("mood") if passive or value.get("mood") != "unknown" else None] if x) or "—"),
             h("p", {"class_": "thought sl-research-prose"}, value["current_thought"])
             if value.get("current_thought") not in ((None, "") if passive else (None, "", "unknown")) else None,
             h("p", {"class_": "sl-research-meta"}, t("rc_recorded_as_of", at=value["at_time"])),
             _section(t("rc_blocked_by"), blocked), _section(t("rc_likely_next"), likely),
             h("p", {"class_": "sl-research-meta"}, value["synthetic_notice"]))


def current_state(value):
    body = current_state_content(value, passive=True)
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, value["display_name"]),
             h("p", {"class_": "sl-research-meta"}, value["persona_id"]), body), "ready"


def activity_content(value):
    """The product activity detail body, including complete recorded provenance."""
    from ..web._render import render_ref
    from ..web._components import _pills
    _, _, raw = _kit()
    value = _activity(value)
    conv = [h("div", {"class_": "quote sl-research-prose"}, h("strong", {}, c["speaker"]), h("br"), c["text"])
            for c in value.get("conversation", [])]
    return h("div", {"class_": "sl-research-activity"},
        h("div", {"class_": "grid two"},
          h("div", {"class_": "sl-card"}, h("h3", {}, t("what_happened")),
            h("p", {"class_": "sl-research-prose"}, value.get("what_happened", value["summary"]))),
          h("div", {"class_": "sl-card"}, h("h3", {}, t("thought")),
            h("p", {"class_": "thought sl-research-prose"}, value.get("persona_thought") or "—"))),
        h("p", {"class_": "sl-research-prose"}, value["summary"])
        if value.get("what_happened") and value["summary"] != value["what_happened"] else None,
        h("div", {"class_": "sec"}, h("h2", {}, t("conversation")),
          fragment(conv) if conv else h("p", {"class_": "muted"}, t("none_f"))),
        h("div", {"class_": "grid"}, *(h("div", {"class_": "sl-card"}, h("h3", {}, label),
            h("div", {"class_": "sl-research-calendar-pills"}, raw(_pills(value.get(key, [])) or "—"))) for key, label in (
                ("actions_done", t("actions")), ("artifacts_touched", t("artifacts")), ("open_loops", t("open_loops"))))),
        fragment(*(_section(label, value.get(key, [])) for key, label in (
            ("key_quotes", t("rc_quotes")), ("pain_points", t("pain_points")), ("goal_refs", t("rc_goal_refs"))))),
        _fields([(t("rc_source_kind"), value.get("source_kind")), (t("rc_confidence"), value.get("confidence")),
                 (t("rc_review_status"), value.get("review_status")), (t("rc_created_at"), value.get("created_at")),
                 (t("calendar"), value.get("calendar_event_id"))]),
        _section(t("rc_source_refs"), [raw(render_ref(ref, passive=True)) for ref in value.get("source_refs", [])]))


def activity_properties(value, *, persona):
    """Property rows with explicit persona content, for product rail or passive fields."""
    from ..web._components import _pills
    value = _activity(value)
    return [("personas", t("persona"), persona), ("square", t("tool"), value["tool"]),
            ("dot", t("mood"), value.get("impact", {}).get("mood")),
            ("personas", t("participants"), h("div", {"class_": "sl-research-calendar-pills"},
                                             _pills(value.get("participants", []) or [t("alone")]))),
            ("check", t("decision"), value.get("decision")),
            *[("dot", key, measurement) for key, measurement in value.get("impact", {}).items() if key != "mood"]]


def activity(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native activity response")
    _person(value.get("persona"), nullable=True)
    event = _activity(value.get("activity"))
    person = value.get("persona") or {}
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, event["task"]),
             h("p", {"class_": "sl-research-meta"}, event["id"], " · ", event["timestamp"], " · ",
               event["event_type"], " · ", event.get("collaboration_mode")),
             activity_content(event), _fields([(label, content) for _, label, content in activity_properties(
                 event, persona=fragment(person.get("display_name", ""), " · ", event["persona_id"]))])), "ready"


def _period(value):
    _text_fields(value, ("view", "anchor_date", "period_start", "period_end"), ("note",))
    _person(value.get("persona"))
    if value["view"] not in {"day", "week", "month", "year"}:
        raise ValueError("Expected native calendar view")
    for field in ("anchor_date", "period_start", "period_end"):
        date.fromisoformat(value[field])
    start, end = date.fromisoformat(value["period_start"]), date.fromisoformat(value["period_end"])
    if not 0 <= (end - start).days <= 365:
        raise ValueError("Expected one bounded native calendar period")
    span = (end - start).days
    if (value["view"] == "day" and span != 0) or (value["view"] == "week" and span != 6):
        raise ValueError("Expected native day/week boundaries")
    if not isinstance(value.get("days"), dict) or not isinstance(value.get("daily_summaries"), list):
        raise ValueError("Expected native calendar days and summaries")
    for day, events in value["days"].items():
        if not start <= date.fromisoformat(day) <= end:
            raise ValueError("Expected event day inside the supplied calendar period")
        if not isinstance(events, list):
            raise ValueError("Expected native calendar summary rows")
        for event in events:
            _text_fields(event, ("id", "timestamp", "event_type", "task", "tool"))
            if event["timestamp"][:10] != day:
                raise ValueError("Expected native event timestamp to match its calendar day")
    for summary in value["daily_summaries"]:
        _text_fields(summary, ("date",), nullable=("mood",))
        if not start <= date.fromisoformat(summary["date"]) <= end:
            raise ValueError("Expected summary day inside the supplied calendar period")
    if "events_total" in value and (type(value["events_total"]) is not int or value["events_total"] < 0):
        raise ValueError("Expected native calendar event count")
    return value


def _agenda(period, summaries):
    keys = sorted(set(period["days"]) | set(summaries))
    return fragment(*(h("div", {"class_": "sl-research-calendar-day"}, h("h3", {}, day),
                        h("p", {}, summaries[day]) if summaries.get(day) else None,
                        fragment(*(_event_chip(event, passive=True) for event in period["days"].get(day, []))))
                      for day in keys))


def period_content(value, *, persona_id="", today="", passive=False):
    """Extracted native calendar grids; wall clock and navigation context are supplied."""
    value = _period(value)
    summaries = {row["date"]: row.get("mood") or "" for row in value["daily_summaries"]}
    anchor = date.fromisoformat(value["anchor_date"])
    view = value["view"]
    if view == "day" or (view == "year" and passive):
        body = fragment(h("h3", {}, t("rc_supplied_agenda")), _agenda(value, summaries))
    elif view == "week":
        body = _week_html(persona_id, value, summaries, today=today, passive=passive)
    elif view == "year":
        body = _year_html(persona_id, value, anchor, today=today)
    else:
        body = _month_html(persona_id, value, summaries, anchor, today=today, passive=passive)
    return h("div", {"class_": "sl-research-calendar"},
             h("p", {"class_": "sl-research-meta"}, t("rc_period_total", n=value["events_total"]))
             if "events_total" in value else None,
             h("p", {"class_": "sl-research-meta"}, value["note"]) if value.get("note") else None,
             body if value["days"] or value["daily_summaries"] else h("p", {}, t("rc_no_events")))


def calendar_period(value):
    value = _period(value)
    if "events_total" not in value:
        raise ValueError("Expected native MCP calendar summary count")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("calendar")),
             h("p", {}, value["persona"]["display_name"], " · ", value["persona"]["id"]),
             h("p", {"class_": "sl-research-meta"}, value["anchor_date"]),
             h("p", {}, value["view"], " · ", value["period_start"], " → ", value["period_end"]),
             period_content(value, passive=True)), "ready" if value["days"] or value["daily_summaries"] else "empty"


def calendar(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native calendar response")
    _person(value.get("persona"))
    _text_fields(value, nullable=("date",))
    if not isinstance(value.get("blocks"), list):
        raise ValueError("Expected native calendar blocks")
    rows = []
    for block in value["blocks"]:
        _text_fields(block, nullable=("collaboration_mode", "persona_thought"))
        if not {"calendar_event", "activity", "collaboration_mode", "persona_thought", "open_loops"} <= block.keys():
            raise ValueError("Expected complete native calendar block")
        loops = _strings(block, "open_loops")
        event = block.get("calendar_event")
        _text_fields(event, ("id", "persona_id", "start", "end", "title", "location_or_tool", "intent", "outcome", "created_at"))
        participants = _strings(event, "participants")
        episode = block.get("activity")
        if episode is not None:
            _activity(episode)
        rows.append(h("div", {"class_": "sl-research-calendar-day"}, h("h3", {}, event["title"]),
            h("p", {}, event["start"], " → ", event["end"]),
            h("p", {"class_": "sl-research-meta"}, event["id"], " · ", event["persona_id"], " · ", event["created_at"]),
            _fields([(t("tool"), event["location_or_tool"]), (t("rc_intent"), event["intent"]),
                     (t("rc_outcome"), event["outcome"]), (t("participants"), " · ".join(participants)),
                     (t("thought"), block.get("persona_thought")), (t("rc_collaboration_mode"), block.get("collaboration_mode"))]),
            _section(t("open_loops"), loops), h("p", {}, t("rc_recorded_activity") if episode is not None else t("rc_planned_only")),
            activity({"persona": value["persona"], "activity": episode})[0] if episode is not None else None))
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("calendar")),
             h("p", {}, value["persona"]["display_name"], " · ", value["persona"]["id"], " · ", value.get("date")),
             collection(rows, empty=t("rc_no_events"))), "ready" if rows else "empty"

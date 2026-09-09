"""Shared calendar/plan parity using actual native getters and isolated records."""
import asyncio
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path

import pytest

from sonaloop import artifacts, services, web
from sonaloop.models import CalendarEvent, ExperienceEvent, DailySummary
from sonaloop.storage import Store
from sonaloop.ui_components import calendar, plans


PLAN = {"summary": "Keep the handover visible.", "intentions": ["Confirm the owner"],
        "expected_milestones": ["A named next shift"], "mood_trajectory": "Less rushed",
        "sample_days": ["2026-06-02"]}
NAMES = {"put_day_plan": plans.plan, "get_day_plan": plans.plan,
         "put_period_plan": plans.plan, "get_period_plan": plans.plan, "list_period_plans": plans.plans,
         "get_current_state": calendar.current_state, "get_calendar": calendar.calendar,
         "get_calendar_period": calendar.calendar_period, "get_activity": calendar.activity}


@pytest.fixture
def recorded(store):
    from conftest import create_persona
    pid = create_persona(store, "Calendar reader")
    cal = CalendarEvent("cal_fixture", pid, "2026-06-02T09:00:00", "2026-06-02T10:00:00",
                        "Shift handover", ["Jo"], "E-Mail", "Confirm ownership", "Owner confirmed", "2026-06-02T10:00:00").to_dict()
    event = ExperienceEvent(id="event_fixture", persona_id=pid, timestamp=cal["start"], event_type="meeting",
        summary="The owner is named.", task="Shift handover", tool="E-Mail", participants=["Jo"],
        collaboration_mode="pair", what_happened="Jo confirmed the next shift owner.",
        conversation=[{"speaker": "Jo", "text": "I will carry the pending issue."}], key_quotes=["Keep the issue visible."],
        actions_done=["Named the owner"], artifacts_touched=["Handover log"], persona_thought="The open item is still unresolved.",
        decision="Keep it on the log", open_loops=["Confirm the delivery"], impact={"mood": "uncertain", "energy_delta": 0},
        pain_points=["Late delivery"], goal_refs=["goal_fixture"], calendar_event_id=cal["id"], created_at=cal["end"],
        source_kind="simulated_episode", source_refs=[{"kind": "note", "id": "note_fixture", "anchor": "line:2",
            "quote": "A supplied source quote.", "text": "A supplied source description."}], confidence=0,
        review_status="disputed").to_dict()
    store.insert_calendar_event(cal)
    store.insert_calendar_event({**cal, "id": "cal_planned", "title": "Planned review", "start": "2026-06-02T11:00:00",
                                 "end": "2026-06-02T12:00:00", "outcome": ""})
    store.insert_experience_event(event)
    store.upsert_daily_summary(DailySummary("summary_fixture", pid, "2026-06-02", "uncertain", ["Named the owner"],
        ["Waiting for delivery"], ["Confirm the delivery"], ["Late delivery"], ["Owner named"], cal["end"]).to_dict())
    store.commit()
    day = services.put_day_plan(pid, "2026-06-02", PLAN, store=store)
    month = services.put_period_plan(pid, "month", "2026-06-02", PLAN, store=store)
    return pid, event, day, month


def values(store, recorded):
    pid, event, day, month = recorded
    return {"put_day_plan": day, "get_day_plan": services.get_day_plan(pid, "2026-06-02", store=store),
            "put_period_plan": month, "get_period_plan": services.get_period_plan(pid, "month", "2026-06-02", store=store),
            "list_period_plans": services.list_period_plans(pid, store=store),
            "get_current_state": services.get_current_state(pid, "2026-06-02T23:59:00", store=store),
            "get_calendar": services.get_calendar(pid, "2026-06-02", store=store),
            "get_calendar_period": services.get_calendar_period(pid, "2026-06-02", "month", store=store),
            "get_activity": services.get_activity(event["id"], store=store)}


def forbidden(*args, **kwargs):
    pytest.fail("Passive presentation attempted a native, media, file or clock operation")


def native_inputs(recorded):
    pid = recorded[0]
    return {"put_day_plan": {"persona_id": pid, "date": "2026-06-02", "plan": PLAN},
        "get_day_plan": {"persona_id": pid, "date": "2026-06-02"},
        "put_period_plan": {"persona_id": pid, "scope": "month", "date": "2026-06-02", "plan": PLAN},
        "get_period_plan": {"persona_id": pid, "scope": "month", "date": "2026-06-02"},
        "list_period_plans": {"persona_id": pid, "scope": "month"},
        "get_current_state": {"persona_id": pid, "at_time": "2026-06-02T23:59:00"},
        "get_calendar": {"persona_id": pid, "date": "2026-06-02"},
        "get_calendar_period": {"persona_id": pid, "date": "2026-06-02", "view": "month"},
        "get_activity": {"activity_id": recorded[1]["id"]}}


def test_original_native_scenarios_include_null_empty_and_all_period_shapes(recorded, tmp_path):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import _tools_simulation
    server = FastMCP("original-calendar-fixtures")
    _tools_simulation.register_simulation(server)
    inputs = [(name, name, arguments) for name, arguments in native_inputs(recorded).items()]
    pid = recorded[0]
    inputs.extend((f"period-{view}", "get_calendar_period", {"persona_id": pid, "date": "2026-06-02", "view": view})
                  for view in ("day", "week", "year"))
    inputs.extend([
        ("plan-null", "get_day_plan", {"persona_id": pid, "date": "2026-06-03"}),
        ("period-plan-null", "get_period_plan", {"persona_id": pid, "scope": "year", "date": "2025-01-01"}),
        ("plans-empty", "list_period_plans", {"persona_id": pid, "scope": "year"}),
        ("calendar-empty", "get_calendar", {"persona_id": pid, "date": "2026-06-03"}),
        ("period-empty", "get_calendar_period", {"persona_id": pid, "date": "2026-06-03", "view": "day"}),
        ("state-before-events", "get_current_state", {"persona_id": pid, "at_time": "2026-06-01T00:00:00"}),
    ])
    examples = []
    for scenario, name, arguments in inputs:
        envelope = server._tool_manager._tools[name].fn(**arguments)
        assert envelope["ok"]
        value = envelope["data"]
        html, state = NAMES[name](value)
        assert state == ("empty" if scenario.endswith(("null", "empty")) else "ready")
        assert len(json.dumps({"name": name, "value": value}, ensure_ascii=False).encode()) <= 8192
        examples.append({"scenario": scenario, "tool": name, "input": arguments, "value": value, "state": state})
    path = Path(os.environ.get("RESEARCH_CALENDAR_FIXTURE_PATH", tmp_path / "calendar-fixtures.json"))
    path.write_text(json.dumps(examples, indent=2, ensure_ascii=False))
    print("Original native synthetic fixtures:", path)


def test_nine_native_values_are_pure_and_do_not_mutate_inputs(recorded, store, monkeypatch):
    from sonaloop.web import _render
    data = values(store, recorded)
    for name, value in data.items():
        NAMES[name](value)
    before = deepcopy(data)
    class NoClock(date):
        today = classmethod(forbidden)
    with monkeypatch.context() as patch:
        patch.setattr(calendar, "date", NoClock)
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(_render, "_avatar", forbidden)
        for attr in ("open", "read_text", "exists", "is_file"):
            patch.setattr(Path, attr, forbidden)
        for name in NAMES:
            patch.setattr(services, name, forbidden)
        for name, value in data.items():
            html, state = NAMES[name](value)
            assert state == "ready" and "sl-research-card" in html
            assert all(tag not in html for tag in ("<a ", "<img", "<script", "<pre", "<button", "<form"))
    assert data == before


def test_full_activity_retains_prose_measurements_and_literal_provenance(recorded, store):
    value = services.get_activity(recorded[1]["id"], store=store)
    value["activity"]["what_happened"] += " Full context." * 180 + " Final qualifier."
    value["activity"]["source_refs"][0]["quote"] = '<img src=x onerror="bad()">' + " Quote." * 90
    html, state = calendar.activity(value)
    for text in ("Final qualifier.", "note:note_fixture#line:2", "A supplied source description.", "disputed",
                 "simulated_episode", "goal_fixture", "energy_delta", "Keep the issue visible.", "Late delivery",
                 "Handover log", "Recorded confidence", "&lt;img", "cal_fixture"):
        assert text in html
    assert "<img" not in html and "sl-clamp" not in html and ">0<" in html
    value["persona"] = None
    assert recorded[0] in calendar.activity(value)[0]


def test_current_state_and_planned_calendar_block_make_no_completion_claim(recorded, store):
    data = values(store, recorded)
    html, _ = calendar.current_state(data["get_current_state"])
    for text in ("State is simulated unless backed by attached evidence.", "Waiting for delivery", "Confirm the delivery",
                 "2026-06-02T23:59:00", "The open item is still unresolved."):
        assert text in html
    html, _ = calendar.calendar(data["get_calendar"])
    assert "Calendar block without a recorded activity" in html
    assert html.count('class="sl-research-activity"') == 1
    assert "Planned review" in html and "Confirm ownership" in html and "Owner confirmed" in html


@pytest.mark.parametrize("view", ["day", "week", "month", "year"])
def test_period_preserves_all_rows_dates_and_moods_without_passive_truncation(recorded, store, view):
    for n in range(5):
        store.insert_experience_event({**recorded[1], "id": f"extra_{n}", "task": f"Additional activity {n}"})
    store.commit()
    value = services.get_calendar_period(recorded[0], "2026-06-02", view, store=store)
    html, state = calendar.calendar_period(value)
    assert state == "ready" and "2026-06-02" in html and "uncertain" in html
    assert all(f"Additional activity {n}" in html for n in range(5))
    assert "Events in this period: 6" in html and "<a " not in html
    assert html.count('class="sl-cm-cell') <= 1, "Passive month omits empty grid cells"


def test_capped_period_keeps_native_total_note_and_exact_supplied_events(recorded, store):
    for n in range(301):
        store.insert_experience_event({**recorded[1], "id": f"cap_{n}", "timestamp": f"2026-06-02T12:{n // 60:02}:{n % 60:02}",
                                       "task": f"Capped activity {n}"})
    store.commit()
    value = services.get_calendar_period(recorded[0], "2026-06-02", "year", store=store)
    html, _ = calendar.calendar_period(value)
    assert value["events_total"] == 302 and "showing the 300 most recent of 302" in html
    assert sum(len(items) for items in value["days"].values()) == 300
    assert "Capped activity 300" in html and "event_fixture" not in html


def test_empty_and_unknown_plan_fields_are_honest(recorded, store):
    assert plans.plan(services.get_day_plan(recorded[0], "2026-06-03", store=store))[1] == "empty"
    assert plans.plans([])[1] == "empty"
    for name, value in ((calendar.calendar, {"persona": {"id": "p", "display_name": "P"}, "date": None, "blocks": []}),
                        (calendar.calendar_period, {"persona": {"id": "p", "display_name": "P"}, "view": "day",
                         "anchor_date": "2026-06-03", "period_start": "2026-06-03", "period_end": "2026-06-03",
                         "days": {}, "daily_summaries": [], "events_total": 0})):
        html, state = name(value)
        assert state == "empty" and "No activity records supplied." in html
    authored = {**PLAN, "summary": '<script>bad()</script>', "sample_days": ["not a date"]}
    native = services.put_period_plan(recorded[0], "invented", "2026-06-02", authored, store=store)
    html, _ = plans.plan(native)
    assert native["scope"] == "month" and "&lt;script&gt;" in html and "<script>" not in html
    assert "not a date" in html and "does not establish completed activity" in html


@pytest.mark.parametrize("name, mutate", [
    ("get_activity", lambda v: v["activity"].update(conversation=["broken"])),
    ("get_activity", lambda v: v["activity"].update(source_refs=[{"text": {"nested": "bad"}}])),
    ("get_activity", lambda v: v["activity"].update(impact={"mood": {"bad": True}})),
    ("get_calendar", lambda v: v["blocks"][0].update(activity=[])),
    ("get_calendar_period", lambda v: v.update(events_total=True)),
    ("get_calendar_period", lambda v: v.update(days={"bad-date": []})),
    ("get_calendar_period", lambda v: v.update(period_end="9999-12-31")),
    ("get_current_state", lambda v: v.update(likely_next=[{}])),
    ("get_day_plan", lambda v: v.update(intentions=[{}])),
])
def test_malformed_native_shapes_fail_soft_before_markup(recorded, store, name, mutate):
    value = values(store, recorded)[name]
    mutate(value)
    with pytest.raises(ValueError):
        NAMES[name](value)


@pytest.mark.parametrize("name, mutate", [
    ("get_current_state", lambda v, text: v.update(current_activity=text)),
    ("get_calendar", lambda v, text: v["blocks"][0]["calendar_event"].update(title=text)),
    ("get_calendar_period", lambda v, text: v["days"]["2026-06-02"][0].update(task=text)),
])
def test_calendar_and_state_text_cannot_create_active_markup(recorded, store, name, mutate):
    value = values(store, recorded)[name]
    mutate(value, '<svg onload="bad()"><a href="javascript:bad()">payload</a></svg>')
    html, _ = NAMES[name](value)
    assert "&lt;svg" in html and "<svg" not in html and "<a " not in html


def test_product_routes_use_the_same_bodies_and_keep_controls(recorded, store, monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.web.pages import _calendar
    monkeypatch.setattr(_calendar, "_today", lambda: "2026-06-02")
    pid, event, day, month = recorded
    client = TestClient(web.create_app())
    response = client.get(f"/personas/{pid}?date=2026-06-02&view=month")
    assert response.status_code == 200
    for record in (day, month):
        assert plans.plan_content(record) in response.text
    period = services.get_calendar_period(pid, "2026-06-02", "month", store=store)
    assert calendar.period_content(period, persona_id=pid, today="2026-06-02") in response.text
    assert "sl-cal-nav" in response.text and "State is simulated unless backed by attached evidence." in response.text
    response = client.get(f"/personas/{pid}?date=2026-06-02&view=day")
    assert response.status_code == 200
    assert calendar.calendar(services.get_calendar(pid, "2026-06-02", store=store))[0] in response.text
    assert "Planned review" in response.text and "Calendar block without a recorded activity" in response.text
    assert "date=2026-06-03&amp;view=day" in response.text
    response = client.get("/activities/" + event["id"])
    assert response.status_code == 200 and calendar.activity_content(event) in response.text
    assert 'href="/personas/' + pid in response.text
    store.insert_experience_event({**event, "conversation": ["unknown legacy shape"]})
    store.commit()
    response = client.get("/activities/" + event["id"])
    assert response.status_code == 200 and "cannot be displayed in full" in response.text


def test_nine_actual_fastmcp_tools_preserve_schemas_and_exact_outputs(recorded, store, monkeypatch, tmp_path):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_simulation
    original = FastMCP("original-calendar")
    _tools_simulation.register_simulation(original)
    server = build_server()
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in NAMES:
        assert new[name].inputSchema == old[name].inputSchema
        assert new[name].outputSchema == old[name].outputSchema
        family = "plans" if name in list(NAMES)[:5] else "calendar"
        assert new[name].meta["ui"]["resourceUri"] == f"ui://sonaloop/{family}/v1"
    captured = []
    env = _tools_simulation._env
    def capture(name, *args, **kwargs):
        result = env(name, *args, **kwargs)
        captured.append((name, deepcopy(result)))
        return result
    monkeypatch.setattr(_tools_simulation, "_env", capture)
    inputs = native_inputs(recorded)
    examples = []
    for name, arguments in inputs.items():
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError and captured[-1][0] == name
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(captured[-1][1])
        assert result.content == text and result.structuredContent == structured
        presentation = result.meta["sonaloop/presentation"]
        assert presentation["tool"] == name and presentation["state"] == "ready"
        assert presentation["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
        assert "sl-research-card" not in result.content[0].text
        examples.append({"tool": name, "input": arguments, "value": structured["data"]})
    assert len(captured) == 9, "No hidden native follow-up or writer retry"
    destination = Path(os.environ.get("RESEARCH_CALENDAR_EXAMPLES_PATH", tmp_path / "native-calendar-examples.json"))
    destination.write_text(json.dumps(examples, indent=2, ensure_ascii=False))
    print("Native synthetic Calendar9 examples:", destination)

"""Item 2: regression fixtures for the seeded simulation scaffolding. The lived
content is LLM-authored, but the scaffolding (RNG-driven timestamps/gaps) must be
deterministic for a given seed so long-horizon runs are reproducible and
regressions are caught. Content generation is stubbed (no network)."""
from __future__ import annotations

from sonaloop import services
from conftest import create_persona


def test_make_rng_is_deterministic_and_seed_sensitive():
    # Same seed -> identical stream (golden values pin the scaffolding RNG).
    r = services._make_rng("regression-seed")
    assert [round(r.random(), 6) for _ in range(3)] == [0.457066, 0.818739, 0.533061]
    # Re-seeding reproduces exactly.
    r2 = services._make_rng("regression-seed")
    assert [round(r2.random(), 6) for _ in range(3)] == [0.457066, 0.818739, 0.533061]
    # A different seed yields a different stream.
    other = services._make_rng("different-seed")
    assert round(other.random(), 6) != 0.457066


def _host_content(store, pid):
    """Host-authored day_plan + per-block activities (what an MCP host submits to record_day)."""
    tool = (store.get_persona(pid)["tools"] or ["CAD"])[0]
    et = ["focus", "meeting", "focus", "admin", "interruption"]
    blocks = [{"title": f"Block {i}", "duration_minutes": 30 + 10 * i, "event_type": et[i],
               "tool": tool, "participants": (["Client"] if et[i] == "meeting" else []),
               "why_it_happens": "work"} for i in range(5)]
    day_plan = {"mood_forecast": "steady", "blocks": blocks}
    act = {
        "what_happened": "did the work", "conversation": [], "key_quotes": ["quote"],
        "actions_done": ["acted"], "artifacts_touched": ["doc"], "persona_thought": "fine",
        "decision": None, "open_loops": [], "mood": "steady", "energy_delta": -1, "pain_points": [],
    }
    return day_plan, {b["title"]: act for b in blocks}


def test_simulate_day_scaffolding_is_reproducible(store):
    pid = create_persona(store, "Sim")
    dp, acts = _host_content(store, pid)
    run1 = services.simulate_day(pid, "2026-06-02", seed="regression-seed", day_plan=dp, activities=acts, store=store)
    run2 = services.simulate_day(pid, "2026-06-02", seed="regression-seed", day_plan=dp, activities=acts, store=store)

    assert all(event["pain_points"] == [] for event in run1["experience_events"])

    sched1 = [(c["start"], c["end"], c["title"]) for c in run1["calendar_events"]]
    sched2 = [(c["start"], c["end"], c["title"]) for c in run2["calendar_events"]]
    assert sched1 == sched2, "same seed must reproduce identical scaffolding"

    # Golden anchor: the first event's start is driven entirely by the seeded RNG
    # (workday_start 08:00 + offset draw 40 + first gap draw 5 -> 08:45).
    assert sched1, "expected scaffolded calendar events"
    assert sched1[0][0].endswith("08:45"), sched1[0][0]
    # Blocks are laid sequentially with positive gaps (no overlaps / time moves forward).
    starts = [c["start"] for c in run1["calendar_events"]]
    assert starts == sorted(starts)


def test_simulate_day_seed_changes_schedule(store):
    pid = create_persona(store, "Sim2")
    dp, acts = _host_content(store, pid)
    a = services.simulate_day(pid, "2026-06-02", seed="seed-A", day_plan=dp, activities=acts, store=store)
    b = services.simulate_day(pid, "2026-06-02", seed="seed-B", day_plan=dp, activities=acts, store=store)
    # Two unrelated seeds should not produce an identical schedule.
    assert [c["start"] for c in a["calendar_events"]] != [c["start"] for c in b["calendar_events"]]

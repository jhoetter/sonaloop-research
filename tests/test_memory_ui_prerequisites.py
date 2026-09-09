"""Native identity and successful-write prerequisites for shared Memory views."""
import json

import pytest

from sonaloop import services
from sonaloop._persona_native import NativePersona
from sonaloop.mcp_server._annotations import TOOL_ANNOTATIONS
from conftest import create_persona
from test_seeded_scaffolding import _host_content

PLAN = {"summary": "Keep the handover visible.", "intentions": ["Confirm ownership"],
        "expected_milestones": ["A named owner"], "mood_trajectory": "Steady",
        "sample_days": ["2026-06-02"]}
DIGEST = {"text": "The handover remained visible.", "themes": ["Ownership"],
          "project_arcs": [], "trends": []}


def test_timeline_rejects_another_personas_entity_before_reading_facts(store, monkeypatch):
    first, second = create_persona(store, "Timeline one"), create_persona(store, "Timeline two")
    services.record_memory_deltas(second, "2026-06-02", {
        "entities": [{"mention": "Private second project", "kind": "project", "status": "open"}],
        "facts": [{"entity": "Private second project", "fact": "Belongs to the second persona"}],
        "threads": [], "event_links": []}, store=store)
    entity = store.list_entities(second)[0]
    original = store.list_entity_facts
    def forbidden(*args, **kwargs):
        pytest.fail("A mismatched Persona/entity pair reached the facts lookup")
    monkeypatch.setattr(store, "list_entity_facts", forbidden)
    for entity_id in (entity["id"], "unknown-entity"):
        with pytest.raises(KeyError, match="Unknown entity for persona"):
            services.get_timeline(first, entity_id=entity_id, store=store)
    monkeypatch.setattr(store, "list_entity_facts", original)
    own = services.get_timeline(second, entity_id=entity["id"], store=store)
    assert own["persona_id"] == second
    assert own["facts_total"] == len(own["facts"]) == 1
    assert own["facts"][0]["fact"] == "Belongs to the second persona"


@pytest.mark.parametrize("name", ["record_day", "record_month_bundle"])
def test_host_authored_recorders_finish_after_native_persona_persistence(store, monkeypatch, name):
    pid = create_persona(store, "Memory recorder")
    blocks, activities = _host_content(store, pid)
    native_writes = []
    original = store.upsert_persona
    def guarded(persona, *args, **kwargs):
        assert isinstance(persona, NativePersona), "Native snapshot safeguards must survive persistence"
        native_writes.append(persona["id"])
        return original(persona, *args, **kwargs)
    monkeypatch.setattr(store, "upsert_persona", guarded)
    if name == "record_day":
        result = services.record_day(pid, "2026-06-02", blocks, PLAN, activities, store=store)
        assert result == {"persona_id": pid, "date": "2026-06-02", "activities": 5}
    else:
        bundle = {"period_plan": PLAN, "digest": DIGEST, "days": [{
            "date": "2026-06-02", "day_plan": PLAN, "plan": blocks, "activities": activities,
            "deltas": {"entities": [], "facts": [], "threads": [], "event_links": []}}]}
        result = services.record_month_bundle(pid, "2026-06", bundle, store=store)
        assert result == {"persona_id": pid, "month": "2026-06", "sample_days": 1,
                          "days": [{"date": "2026-06-02", "activities": 5, "entities": 0, "facts": 0}]}
    assert json.loads(json.dumps(result)) == result
    assert native_writes and set(native_writes) == {pid}
    assert isinstance(store.get_persona(pid), NativePersona)
    assert len(store.list_experience_events(pid, "2026-06-02", "2026-06-03")) == 5
    assert len(store.list_daily_summaries(pid, "2026-06-02", "2026-06-02")) == 1


def test_pain_extraction_advertises_its_actual_native_write(store):
    from test_persona_memory_hardening import _event
    pid = create_persona(store, "Pain extraction")
    event = _event(pid, "pain-event", "2026-06-02")
    event["pain_points"] = ["Ownership is unclear"]
    store.insert_experience_event(event)
    store.commit()
    before = store.list_pain_points(pid)
    result = services.extract_pain_points(pid, "2026-06-02", "2026-06-03", store=store)
    assert not before and len(result) == 1
    assert store.list_pain_points(pid)[0]["id"] == result[0]["id"]
    assert result[0]["evidence_event_ids"] == []
    assert TOOL_ANNOTATIONS["extract_pain_points"]["readOnlyHint"] is False

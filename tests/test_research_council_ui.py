"""Council native projections and product rendering share one prepared statement core."""
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest

from sonaloop import artifacts, web
from sonaloop.models import CouncilSession
from sonaloop.storage import Store
from sonaloop.ui_components import councils, statements
from sonaloop.web import _render as render
from sonaloop.web._html import raw


def council_record():
    return CouncilSession(
        id="council_fixture", prompt="Where does **handover** fail?", persona_ids=["persona_a", "persona_b"],
        selection_reason="Authored synthetic fixture", proposal="", votes=[], summary="A visible owner helps.",
        exec_summary="Keep the final **handover context**.", created_at="2026-09-09T01:00:00Z",
        prompts=[{"id": "q0", "kind": "question", "text": "Who owns the unresolved issue?"},
                 {"id": "q1", "kind": "question", "text": "What must the next shift know?"}],
        statements=[
            {"persona_id": "persona_a", "text": "The owner is **unclear**.", "about": {"kind": "prompt", "id": "q0"},
             "stance": {"value": -1, "label": "skeptical"}, "meta": {"claim_posture": "simulated"},
             "refs": [{"kind": "council", "id": "source_a", "anchor": "st3", "quote": "Only applies during the pilot."}]},
            {"persona_id": "persona_a", "text": "Keep the final context.", "about": {"kind": "prompt", "id": "q1"},
             "refs": [{"kind": "external", "text": "The second statement has a different source."}]},
            {"persona_id": "persona_b", "text": "An additional concern.", "about": {"kind": "prompt", "id": "unmatched"}},
        ], findings=[{"id": "f1", "kind": "summary", "text": "Ownership needs to stay visible.",
                     "refs": [{"kind": "council", "id": "source_a", "anchor": "st3"}]}],
    ).to_dict()


def forbidden(*args, **kwargs):
    pytest.fail("Passive/shared rendering attempted native resolution or a filesystem probe")


def test_passive_full_record_never_resolves_and_keeps_complete_native_evidence(monkeypatch):
    # Imports/bootstrap occur before the render-only no-I/O boundary.
    avatar_module = import_module("sonaloop.web._avatar")
    value = council_record()
    value["statements"][0]["text"] = "Substantial context. " * 100 + "Final scope qualifier."
    value["statements"][0]["meta"].update(input="The exact supplied input.", pushback=[f"Question {i}" for i in range(6)])
    value["statements"][0]["refs"][0]["quote"] = "Grounding context. " * 30 + "Final evidence qualifier."
    before = deepcopy(value)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(artifacts, "_stance_scale", forbidden)
        patch.setattr(render, "_avatar", forbidden)
        patch.setattr(avatar_module, "_avatar_src", forbidden)
        patch.setattr(Path, "is_file", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "open", forbidden)
        html, state = councils.council(value)
    assert state == "ready" and value == before
    for text in ("persona_a", "persona_b", "Final scope qualifier.", "The exact supplied input.", "Question 5",
                 "Final evidence qualifier.", "council:source_a#st3", "-1 · skeptical", "simulated",
                 "Ownership needs to stay visible.", "Further answers"):
        assert text in html
    assert "<img" not in html and "<button" not in html and "<details" not in html and "sl-clamp" not in html
    assert str(html).count('class="qround sl-research-round"') == 3
    assert "sl-research-claim-notice" not in html, "No trust envelope must not become a verified record"
    # Even an accidentally supplied Store is ignored by the explicit passive route.
    assert "persona_a" in render.render_statements(value["statements"], object(), passive=True)


def test_product_adapter_supplies_identity_media_and_refs_before_pure_grouping(monkeypatch):
    class People:
        def __init__(self):
            self.calls = []
        def get_persona(self, pid):
            self.calls.append(pid)
            return {"id": pid, "display_name": "Mira" if pid == "persona_a" else "Noah",
                    "segment": {"lebensphase": "Working parent"}}
    people = People()
    value = council_record()
    monkeypatch.setattr(render, "_avatar", lambda person, size: raw(f'<span data-fixture-avatar="{person["id"]}"></span>'))
    monkeypatch.setattr(artifacts, "resolve_ref", lambda ref, store: {
        "exists": True, "title": "Resolved source", "text": "Resolved evidence", "href": "/councils/source_a#st3"})
    original = statements.render_statements
    prepared = []
    def inspect(rows, **kwargs):
        prepared.extend(rows)
        with monkeypatch.context() as patch:
            patch.setattr(people, "get_persona", forbidden)
            patch.setattr(render, "_avatar", forbidden)
            patch.setattr(artifacts, "resolve_ref", forbidden)
            patch.setattr(Path, "open", forbidden)
            patch.setattr(Path, "exists", forbidden)
            return original(rows, **kwargs)
    monkeypatch.setattr(statements, "render_statements", inspect)
    html = councils.council_voices(value, people, clamp_at=20)
    assert people.calls == ["persona_a", "persona_b"]
    assert len(prepared) == 3
    assert "Resolved source" in prepared[0].references
    assert "different source" in prepared[1].references
    assert prepared[0].statement.get("id") is None and prepared[1].statement.get("id") is None
    assert '<a href="/personas/persona_a" class="turn-who">' in html
    assert 'data-fixture-avatar="persona_a"' in html and "Mira" in html and "Working parent" in html
    assert '<details class="qround" open>' in html and 'class="sl-clamp"' in html
    assert html.index("The owner is") < html.index("Resolved source") < html.index("Keep the final context") < html.index("different source")


def test_legacy_single_statement_options_keep_product_presentation(monkeypatch):
    value = council_record()["statements"][0]
    value["meta"]["input"] = "Supplied input snapshot"
    html = render.render_statement(value, object(), show_persona=False, head_extra=raw("<b>Source study</b>"), expand_quotes=True)
    assert 'class="turn turn-bare"' in html
    assert "Source study" in html and 'class="turn-input"' in html and 'class="turn-quotes"' in html
    assert "persona_a" not in html and "Supplied input snapshot" in html


def test_passive_group_does_not_apply_the_first_statements_trust_to_later_voices():
    rows = [{"persona_id": "one", "text": "First statement", "stance": {"value": 2, "label": "support"},
             "meta": {"claim_posture": "observed", "context": "First context"}},
            {"persona_id": "one", "text": "Second statement", "stance": {"value": -2, "label": "oppose"},
             "meta": {"claim_posture": "unsupported", "context": "Second context"}}]
    html = render.render_statements(rows, passive=True)
    assert str(html).count('class="turn sl-research-statement"') == 1
    first, second = str(html).split('class="turn-ans sl-research-statement-body"')[1:]
    assert "2 · support" in first and "observed" in first and "First context" in first
    assert "-2 · oppose" in second and "unsupported" in second and "Second context" in second


def test_product_council_detail_calls_the_same_summary_and_statement_core(store, monkeypatch):
    from starlette.testclient import TestClient
    value = council_record()
    store.insert_council_session(value)
    core_calls = []
    original = statements.render_statements
    def observe(rows, **kwargs):
        core_calls.append(rows)
        return original(rows, **kwargs)
    monkeypatch.setattr(statements, "render_statements", observe)
    response = TestClient(web.create_app()).get(f'/councils/{value["id"]}')
    assert response.status_code == 200 and len(core_calls) == 1
    assert str(councils.summary_reads(value)) in response.text
    assert "The owner is <strong>unclear</strong>." in response.text
    assert "What must the next shift know?" in response.text


def test_native_summary_page_uses_only_actual_counts_and_pagination():
    summary = {"id": "council_one", "prompt": "An actual summary", "created_at": "2026-09-09",
               "personas": 7, "turns": 12, "votes": {"support": 2, "oppose": 1}}
    html, state = councils.councils({"items": [summary], "total": 9, "has_more": True, "next_cursor": "opaque"})
    assert state == "ready"
    for text in ("An actual summary", "Participants: 7", "Voices: 12", "support: 2", "oppose: 1", "1 / 9", " · …"):
        assert text in html
    assert "sl-research-statement" not in html and "persona_a" not in html and "opaque" not in html
    empty, state = councils.councils({"items": [], "total": 0, "has_more": False, "next_cursor": None})
    assert state == "empty" and "sl-research-empty" in empty and "sl-research-card" not in empty


@pytest.mark.parametrize("value", [None, [], {}, {"items": []},
    {"id": "legacy", "prompt": "Old record", "persona_ids": [], "turns": [{"content": "Unknown historical shape"}]},
    {"id": "bad", "prompt": "Bad statements", "persona_ids": [], "statements": ["not a statement"]}])
def test_summary_or_unrecognized_legacy_shapes_do_not_become_full_councils(value):
    with pytest.raises(ValueError):
        councils.council(value)


@pytest.mark.parametrize("value", [[], {"items": [], "total": -1, "has_more": False},
    {"items": [], "total": 0, "has_more": "unknown"}, {"items": [council_record()], "total": 1, "has_more": False},
    {"items": [{"id": "c", "prompt": "P", "personas": 1, "turns": 2, "votes": {"future": {"count": 4}}}], "total": 1, "has_more": False}])
def test_malformed_native_pages_do_not_invent_counts(value):
    with pytest.raises(ValueError):
        councils.councils(value)


def test_authored_text_and_reference_addresses_are_escaped():
    value = council_record()
    value["prompt"] = '<img src=x onerror="bad()">'
    value["statements"][0]["text"] = "<script>bad()</script>"
    value["statements"][0]["refs"][0]["anchor"] = '<script>source</script>'
    html, _ = councils.council(value)
    assert "<img" not in html and "<script>" not in html
    assert "&lt;img" in html and "&lt;script&gt;" in html


def test_recorded_trust_and_special_verdicts_are_displayed_without_derivation(monkeypatch):
    value = council_record()
    value["claim_posture"] = {"verified": False, "counts": {"simulated": 3}, "prose_uncovered": True,
        "claims": [{"id": "claim_one", "posture": "simulated", "refs": [{"kind": "external", "text": "Full source qualifier."}]}]}
    value["head_to_head"] = {"result": {"preference": "B", "preference_title": "Recorded winner", "margin": .25,
        "decisive": "clear", "options": [{"label": "A", "title": "First option", "votes": 99},
                                        {"label": "B", "title": "Second option", "votes": 1}]}}
    value["red_team"] = {"case_against": {"theme_count": 1, "voices": 2, "top_blocker": "Recorded blocker",
        "worst_severity": "high", "themes": [{"theme": "Recorded blocker", "count": 2, "severity": "high"}]}}
    monkeypatch.setattr(artifacts, "resolve_ref", forbidden)
    monkeypatch.setattr(artifacts, "vote_tally", forbidden)
    html, _ = councils.council(value)
    assert "B — Recorded winner" in html and "0.25" in html and "Recorded blocker" in html
    assert "claim-notice--unverified" in html and "Full source qualifier." in html
    assert "<details" not in html

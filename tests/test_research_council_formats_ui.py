"""Council format parity against isolated native writes, not mirrored DTO fixtures."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from sonaloop import artifacts, services, web
from sonaloop.storage import Store
from sonaloop.ui_components import council_formats as formats
from sonaloop.web import _render


def authored_inputs(project_id):
    common = {"project_id": project_id, "prompt": "What changes the handover?",
              "persona_ids": ["persona_fixture"], "summary": "A bounded synthetic example.",
              "statements": [{"persona_id": "persona_fixture", "text": "Keep the full final context."}]}
    return {
        "record_head_to_head": {**common, "options": ["Named owner", "Shared inbox"],
            "preferences": [{"persona_id": "persona_fixture", "choice": "A", "reason": "The owner is visible.", "intensity": 0},
                            {"persona_id": "unresolved", "choice": "neither", "reason": "Neither fits the night shift."}],
            "variant_meta": {"variants": {"A": {"id": "variant_a", "version": "v0.2"}},
                             "order_shown": {"persona_fixture": ["B", "A"]}}},
        "record_price_ladder": {**common, "price_points": ["10 / month", "20 / month", "30 / month"],
            "responses": [{"persona_id": "persona_fixture", "price": 10, "band": "bargain", "quote": "Fits the small budget."},
                          {"persona_id": "persona_fixture", "price": 10, "band": "bargain", "quote": "Repeated authored response."},
                          {"persona_id": "persona_fixture", "price": 20, "band": "too_expensive", "quote": "No approval above this point."}]},
        "record_red_team": {**common, "stance": "both",
            "objections": [{"persona_id": "persona_fixture", "theme": "Ownership", "text": "The final owner can still be absent.", "severity": "unknown-native-token"}],
            "endorsements": [{"persona_id": "unresolved", "theme": "Clarity", "text": "The next shift sees the pending issue."}]},
    }


@pytest.fixture
def recorded(store):
    project = services.create_research_project("Council format test", "Synthetic local compatibility", store=store)
    inputs = authored_inputs(project["id"])
    records = {name: getattr(services, name)(**arguments, store=store) for name, arguments in inputs.items()}
    return project, inputs, records


def getter_values(store, records):
    return {
        "head_to_head": services.get_head_to_head(records["record_head_to_head"]["id"], store=store),
        "price_ladder": services.get_price_ladder(records["record_price_ladder"]["id"], store=store),
        "price_analysis": services.price_ladder_analysis(records["record_price_ladder"]["id"], store=store),
        "red_team": services.get_red_team(records["record_red_team"]["id"], store=store),
        "query_councils": services.query_councils(limit=1, store=store),
    }


def forbidden(*args, **kwargs):
    pytest.fail("Presentation tried to resolve, probe media or recompute native results")


def test_all_native_projections_are_pure_and_leave_inputs_unchanged(recorded, store, monkeypatch):
    _, _, records = recorded
    values = {**getter_values(store, records),
              **{name.removeprefix("record_") + "_write": value for name, value in records.items()}}
    # Bootstrap before blocking runtime/file access; the render itself is pure.
    for name, value in values.items():
        getattr(formats, name)(value)
    before = deepcopy(values)
    with monkeypatch.context() as patch:
        patch.setattr(Store, "__init__", forbidden)
        patch.setattr(artifacts, "resolve_ref", forbidden)
        patch.setattr(artifacts, "_stance_scale", forbidden)
        patch.setattr(_render, "_avatar", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "is_file", forbidden)
        patch.setattr(Path, "open", forbidden)
        for name in ("record_head_to_head", "record_red_team", "record_price_ladder", "get_head_to_head",
                     "get_red_team", "get_price_ladder", "price_ladder_analysis", "query_councils"):
            patch.setattr(services, name, forbidden)
        for name, value in values.items():
            html, state = getattr(formats, name)(value)
            assert state == "ready" and "sl-research-card" in html
            for forbidden_tag in ("<img", "<button", "<details", "<script", "<pre"):
                assert forbidden_tag not in html
    assert values == before


def test_price_table_keeps_native_duplicate_counts_nulls_range_and_cliff(recorded, store):
    record = recorded[2]["record_price_ladder"]
    value = services.get_price_ladder(record["id"], store=store)
    overall = value["result"]["overall"]
    assert overall["respondents"] == 1 and overall["points"][0]["respondents"] == 2
    assert overall["points"][2]["acceptance"] is None
    html, _ = formats.price_ladder(value)
    for text in ("Participants: 1", "Responses: 2", "bargain: 2", "Not answered", "30 / month",
                 "Repeated authored response.", "No approval above this point.", "10 / month (10.0) → 20 / month (20.0): 1.0"):
        assert text in html
    assert "sl-research-council-voices" not in html
    assert 'scope="row"' in html and 'scope="col"' in html
    analysis, _ = formats.price_analysis(services.price_ladder_analysis(record["id"], store=store))
    assert str(formats.price_result_content(value["result"])) in analysis
    assert "Repeated authored response." not in analysis, "Analytics has no raw response records"


def test_flat_getters_keep_supplied_detail_without_inventing_voices(recorded, store):
    values = getter_values(store, recorded[2])
    head, _ = formats.head_to_head(values["head_to_head"])
    for text in ("Neither fits the night shift.", "Intensity: 0", "Abstentions: 1", "B → A", "variant_a", "v0.2"):
        assert text in head
    red, _ = formats.red_team(values["red_team"])
    for text in ("The final owner can still be absent.", "unknown-native-token", "The next shift sees the pending issue.", "unresolved"):
        assert text in red
    # Native grouping counts unknown participant IDs, while voices counts resolved
    # personas. Do not force those different native counts to be equal.
    assert values["red_team"]["case_against"]["voices"] == 0
    assert values["red_team"]["case_against"]["themes"][0]["count"] == 1
    assert "Keep the full final context." not in head + red
    assert "sl-research-statement" not in head + red


def test_recorded_verdicts_and_acceptance_are_not_rederived(recorded, store):
    values = getter_values(store, recorded[2])
    head = values["head_to_head"]
    head["result"].update(preference="B", preference_title="Recorded alternative", margin=.125, decisive="narrow")
    html, _ = formats.head_to_head(head)
    assert "B — Recorded alternative" in html and "0.125" in html
    price = values["price_analysis"]
    price["overall"]["points"][0]["acceptance"] = .123
    html, _ = formats.price_analysis(price)
    assert "Recorded acceptance: 0.123" in html, "Counts never replace the actual stored result"


@pytest.mark.parametrize("writer, getter, arguments, expected", [
    ("record_head_to_head", "get_head_to_head", {"options": ["First", "Second"]}, "Abstentions: 0"),
    ("record_price_ladder", "get_price_ladder", {"price_points": [10, 20]}, "Not answered"),
    ("record_red_team", "get_red_team", {}, "No substantive objections"),
])
def test_native_record_without_responses_is_ready_without_invented_reactions(store, writer, getter, arguments, expected):
    project = services.create_research_project("Empty response fixture", "Empty native aggregate", store=store)
    record = getattr(services, writer)(project["id"], "What is supplied?", **arguments, store=store)
    value = getattr(services, getter)(record["id"], store=store)
    html, state = getattr(formats, getter.removeprefix("get_"))(value)
    assert state == "ready" and expected in html
    assert "sl-research-council-voices" not in html and "sl-research-statement" not in html


def test_red_team_resolved_participant_has_full_recorded_role_lens(store, monkeypatch):
    from conftest import create_persona
    pid = create_persona(store, "Council role reader")
    project = services.create_research_project("Resolved role fixture", "Local native role shape", store=store)
    record = services.record_red_team(project["id"], "Where does ownership fail?", persona_ids=[pid],
        objections=[{"persona_id": pid, "theme": "Absence", "text": "The owner may be absent.", "severity": "high"}], store=store)
    value = services.get_red_team(record["id"], store=store)
    role = value["roles"][pid]
    assert set(role) == {"id", "name", "lens"}
    monkeypatch.setattr(Store, "get_persona", forbidden)
    html, _ = formats.red_team(value)
    for text in (pid, role["id"], role["name"], role["lens"]):
        assert text in html


def test_writer_views_retain_full_council_content_and_native_trust(recorded):
    for name, value in recorded[2].items():
        html, state = getattr(formats, name.removeprefix("record_") + "_write")(value)
        assert state == "ready" and "Keep the full final context." in html
        assert "sl-research-council-voices" in html
        assert "claim-notice--unverified" in html, "Native derived unsupported findings remain visibly unsupported"


@pytest.mark.parametrize("writer, key, helper", [
    ("record_head_to_head", "head_to_head", "head_to_head_content"),
    ("record_price_ladder", "price_ladder", "price_ladder_content"),
    ("record_red_team", "red_team", "red_team_content"),
])
def test_product_council_detail_reuses_each_full_format_body(recorded, writer, key, helper):
    from starlette.testclient import TestClient
    value = recorded[2][writer]
    response = TestClient(web.create_app()).get('/councils/' + value["id"])
    assert response.status_code == 200
    assert str(getattr(formats, helper)(value[key])) in response.text
    assert "Keep the full final context." in response.text
    if key == "price_ladder":
        assert 'id="price-ladder"' in response.text and 'href="#price-ladder"' in response.text


def test_native_query_page_preserves_offset_and_counts_and_empty(recorded, store):
    page = services.query_councils(limit=1, offset=1, store=store)
    html, state = formats.query_councils(page)
    assert state == "ready" and "Offset 1 · 1 / 3" in html
    assert "1 statements · 0 votes · 0 questions" in html
    assert "persona_fixture" in html and "sl-research-statement" not in html
    assert " · …" in html
    empty = services.query_councils(limit=1, offset=20, store=store)
    html, state = formats.query_councils(empty)
    assert state == "empty" and "Offset 20 · 0 / 3" in html and "sl-research-empty" in html
    assert "sl-research-card" not in html


@pytest.mark.parametrize("name,mutation", [
    ("head_to_head", lambda v: v["result"].pop("abstentions")),
    ("head_to_head", lambda v: v["result"].update(options=[{"label": "A"}])),
    ("head_to_head", lambda v: v["result"].update(margin=True)),
    ("head_to_head", lambda v: v.update(preferences=["not a row"])),
    ("price_ladder", lambda v: v.update(responses=[{"price": "10"}])),
    ("price_analysis", lambda v: v["overall"]["points"][0]["counts"].pop("bargain")),
    ("price_analysis", lambda v: v["overall"]["points"][0].update(acceptance="unknown")),
    ("price_analysis", lambda v: v["overall"].pop("cliff")),
    ("red_team", lambda v: v["case_against"]["themes"][0].update(items=["not an item"])),
    ("red_team", lambda v: v.update(roles=["unresolved"])),
    ("query_councils", lambda v: v["items"][0].update(votes={"support": 1})),
    ("query_councils", lambda v: v.update(next_offset="opaque-cursor")),
])
def test_malformed_native_formats_fail_before_presentation_helpers(recorded, store, name, mutation, monkeypatch):
    from sonaloop.ui_components import councils
    value = getter_values(store, recorded[2])[name]
    mutation(value)
    monkeypatch.setattr(councils, "h2h_result_html", forbidden)
    monkeypatch.setattr(councils, "red_team_result_html", forbidden)
    with pytest.raises(ValueError):
        getattr(formats, name)(value)


def test_authored_text_is_escaped_without_clamping(recorded, store):
    value = services.get_head_to_head(recorded[2]["record_head_to_head"]["id"], store=store)
    value["options"][0]["text"] = "<script>unsafe</script>" + "Full context. " * 200 + "Final qualifier."
    value["preferences"][0]["reason"] = '<img src="x" onerror="bad()">'
    html, _ = formats.head_to_head(value)
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html and "Final qualifier." in html and "&lt;img" in html
    assert "sl-clamp" not in html


def test_eight_actual_fastmcp_tools_preserve_schemas_and_exact_native_outputs(store, monkeypatch, tmp_path):
    from mcp.server.fastmcp import FastMCP
    from sonaloop.mcp_server import build_server, _tools_council, _tools_substrate
    original = FastMCP("original-council-formats")
    _tools_council.register_council(original)
    _tools_substrate.register_substrate(original)
    server = build_server()
    names = ["record_head_to_head", "get_head_to_head", "record_price_ladder", "get_price_ladder",
             "price_ladder_analysis", "record_red_team", "get_red_team", "query_councils"]
    old = {tool.name: tool for tool in asyncio.run(original.list_tools())}
    new = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in names:
        assert new[name].inputSchema == old[name].inputSchema
        assert new[name].outputSchema == old[name].outputSchema
        assert new[name].meta["ui"]["resourceUri"] == "ui://sonaloop/councils/v1"
    captured = []
    for module in (_tools_council, _tools_substrate):
        env = module._env
        def capture(name, *args, _env=env, **kwargs):
            value = _env(name, *args, **kwargs)
            captured.append((name, deepcopy(value)))
            return value
        monkeypatch.setattr(module, "_env", capture)
    examples = []
    def call(name, arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.isError
        assert captured[-1][0] == name
        text, structured = original._tool_manager._tools[name].fn_metadata.convert_result(captured[-1][1])
        assert result.content == text and result.structuredContent == structured
        presentation = result.meta["sonaloop/presentation"]
        assert presentation["tool"] == name and presentation["state"] == "ready"
        assert presentation["text_sha256"] == hashlib.sha256(result.content[0].text.encode()).hexdigest()
        assert "sl-research-card" not in result.content[0].text
        examples.append({"tool": name, "input": arguments, "value": structured["data"]})
        return structured["data"]
    project = services.create_research_project("MCP Council formats", "Isolated native examples", store=store)
    inputs = authored_inputs(project["id"])
    # Include a genuinely resolved participant so native Red-Team role objects
    # (id/name/lens), not just the empty unresolved map, cross the SDK boundary.
    from conftest import create_persona
    pid = create_persona(store, "MCP Council role reader")
    inputs["record_red_team"] = deepcopy(inputs["record_red_team"])
    inputs["record_red_team"]["persona_ids"] = [pid]
    inputs["record_red_team"]["objections"][0]["persona_id"] = pid
    inputs["record_red_team"]["statements"][0]["persona_id"] = pid
    for write, read in (("record_head_to_head", "get_head_to_head"),
                        ("record_price_ladder", "get_price_ladder"), ("record_red_team", "get_red_team")):
        written = call(write, inputs[write])
        fetched = call(read, {"session_id": written["id"]})
        block = written[write.removeprefix("record_")]
        assert all(fetched[key] == value for key, value in block.items())
        if write == "record_price_ladder":
            analysis = call("price_ladder_analysis", {"session_id": written["id"]})
            assert analysis["overall"] == block["result"]["overall"]
    page = call("query_councils", {"project_id": project["id"], "limit": 1})
    assert page["total"] == 3 and page["next_offset"] == 1
    assert len(captured) == len(names), "Each native writer executes once"
    # Private isolated examples aid independent fixture review; these are native
    # temporary-Store test results, never a live/customer execution receipt.
    example_path = tmp_path / "native-council-format-examples.json"
    example_path.write_text(json.dumps(examples, indent=2))
    print("Native synthetic examples:", example_path)

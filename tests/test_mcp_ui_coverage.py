"""Static ledger gate: new tools and native drift cannot silently escape coverage."""
from __future__ import annotations

import builtins
from copy import deepcopy
import json

import pytest

from sonaloop.ui_components.coverage import coverage_data, coverage_errors


@pytest.fixture
def source_tree(tmp_path):
    server = tmp_path / "sonaloop/mcp_server"
    server.mkdir(parents=True)
    (server / "__init__.py").write_text(
        "from ._tools_native import register_native\n"
        "def build_server():\n"
        "    register_native(mcp)\n")
    (server / "_tools_native.py").write_text(
        "def register_native(mcp):\n"
        "    @mcp.tool()\n"
        "    def read_note(note_id: str):\n"
        "        return services.get_note(note_id)\n"
        "\n"
        "    @mcp.tool()\n"
        "    def write_note(note_id: str, *, operation_id: str):\n"
        "        return services.update_note(note_id, operation_id)\n"
        "\n"
        "raise AssertionError('Tool module must never be imported')\n")
    (server / "_annotations.py").write_text(
        "TOOL_ANNOTATIONS = {'read_note': R('Read note'), 'write_note': W('Write note')}\n")
    ledger = {
        "schema_version": "sonaloop.mcp-ui-coverage.v1",
        "native_source": {"repository": "https://example.test/customer", "commit": "a" * 40},
        "scope": "Core registrations; external extensions remain outside this source inventory.",
        "tools": [
            {"tool": "read_note", "family": "note", "treatment": "surface", "status": "planned",
             "reason": "Display the native note and its evidence references.",
             "native": {"module": "sonaloop/mcp_server/_tools_native.py", "symbol": "read_note",
                        "line": 3, "calls": ["services.get_note"], "annotation": "R", "operation_id": False}},
            {"tool": "write_note", "family": "note", "treatment": "surface", "status": "planned",
             "reason": "Display the confirmed native note after the explicit write.",
             "native": {"module": "sonaloop/mcp_server/_tools_native.py", "symbol": "write_note",
                        "line": 7, "calls": ["services.update_note"], "annotation": "W", "operation_id": True}},
        ],
    }
    component = tmp_path / "sonaloop/ui_components"
    component.mkdir()
    (component / "coverage.json").write_text(json.dumps(ledger))
    return tmp_path, ledger


def test_repository_ledger_matches_every_registered_core_tool():
    # Inventory is discovered from source, so new tools fail without maintaining
    # a second expected-name list or permanently freezing today's status counts.
    assert coverage_errors() == []


def test_ledger_reads_are_independent_and_static(source_tree, monkeypatch):
    root, _ = source_tree
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.startswith(("sonaloop.mcp_server", "sonaloop.services")), name
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    data = coverage_data(source_root=root)
    data["tools"].clear()
    assert len(coverage_data(source_root=root)["tools"]) == 2
    assert coverage_errors(source_root=root) == []


def test_missing_and_duplicate_rows_fail(source_tree):
    root, ledger = source_tree
    missing = deepcopy(ledger)
    missing["tools"].pop()
    assert "Missing coverage tool: write_note" in coverage_errors(missing, source_root=root)
    duplicate = deepcopy(ledger)
    duplicate["tools"].append(deepcopy(duplicate["tools"][0]))
    assert "Duplicate coverage tool: read_note" in coverage_errors(duplicate, source_root=root)


def test_new_registered_module_requires_a_ledger_row(source_tree):
    root, ledger = source_tree
    server = root / "sonaloop/mcp_server"
    (server / "_tools_new.py").write_text(
        "def register_new(mcp):\n"
        "    @mcp.tool()\n"
        "    def remove_note(note_id: str):\n"
        "        return services.delete_note(note_id)\n")
    (server / "__init__.py").write_text(
        "from ._tools_native import register_native\n"
        "from ._tools_new import register_new\n"
        "def build_server():\n"
        "    register_native(mcp)\n"
        "    register_new(mcp)\n")
    (server / "_annotations.py").write_text(
        "TOOL_ANNOTATIONS = {'read_note': R('Read'), 'write_note': W('Write'), 'remove_note': D('Remove')}\n")
    assert "Missing coverage tool: remove_note" in coverage_errors(ledger, source_root=root)


def test_unregistered_module_is_outside_the_core_inventory(source_tree):
    root, ledger = source_tree
    (root / "sonaloop/mcp_server/_tools_orphan.py").write_text(
        "def register_orphan(mcp):\n"
        "    @mcp.tool()\n"
        "    def orphan_tool():\n"
        "        raise AssertionError('Not registered')\n")
    assert coverage_errors(ledger, source_root=root) == []


def test_removed_registration_makes_ledger_entries_stale(source_tree):
    root, ledger = source_tree
    (root / "sonaloop/mcp_server/__init__.py").write_text("def build_server():\n    pass\n")
    errors = coverage_errors(ledger, source_root=root)
    assert "Coverage tool is not registered: read_note" in errors
    assert "Coverage tool is not registered: write_note" in errors


@pytest.mark.parametrize(("field", "value", "message"), [
    ("status", "done", "Invalid status"),
    ("status", "not_applicable", "Invalid exemption/status pairing"),
    ("treatment", "context_only", "Invalid exemption/status pairing"),
    ("treatment", "generic_json", "Invalid treatment"),
    ("reason", " \n", "Missing nonblank coverage reason"),
    ("family", "", "Invalid family"),
])
def test_invalid_claims_and_exemptions_fail(source_tree, field, value, message):
    root, ledger = source_tree
    ledger["tools"][0][field] = value
    assert f"{message}: read_note" in coverage_errors(ledger, source_root=root)


def test_explicit_exemption_and_future_supported_status_are_valid(source_tree):
    root, ledger = source_tree
    ledger["tools"][0].update(status="not_applicable", treatment="context_only",
                              reason="Authoring context is consumed by the later authored result.")
    ledger["tools"][1]["status"] = "supported"
    assert coverage_errors(ledger, source_root=root) == []
    ledger["tools"][0]["reason"] = ""
    assert "Missing nonblank coverage reason: read_note" in coverage_errors(ledger, source_root=root)


@pytest.mark.parametrize(("field", "value"), [
    ("module", "../../private.py"), ("symbol", "renamed_note"), ("line", 8),
    ("calls", ["services.overwrite_note"]), ("annotation", "D"), ("operation_id", False),
    ("line", True), ("operation_id", 1),
])
def test_native_anchor_drift_cannot_pass(source_tree, field, value):
    root, ledger = source_tree
    ledger["tools"][1]["native"][field] = value
    assert f"Native {field} anchor drift: write_note" in coverage_errors(ledger, source_root=root)


def test_native_implementation_changes_invalidate_the_ledger(source_tree):
    root, ledger = source_tree
    path = root / "sonaloop/mcp_server/_tools_native.py"
    path.write_text(path.read_text().replace("services.get_note(note_id)", "services.get_persona(note_id)"))
    assert "Native calls anchor drift: read_note" in coverage_errors(ledger, source_root=root)
    annotations = root / "sonaloop/mcp_server/_annotations.py"
    annotations.write_text(annotations.read_text().replace("W('Write note')", "D('Write note')"))
    assert "Native annotation anchor drift: write_note" in coverage_errors(ledger, source_root=root)


def test_literal_public_tool_name_and_native_symbol_are_distinct(source_tree):
    root, ledger = source_tree
    path = root / "sonaloop/mcp_server/_tools_native.py"
    path.write_text(path.read_text().replace("@mcp.tool()\n    def read_note", "@mcp.tool(name='read_note')\n    def read_native"))
    ledger["tools"][0]["native"]["symbol"] = "read_native"
    assert coverage_errors(ledger, source_root=root) == []


def test_dynamic_registration_fails_instead_of_reporting_partial_coverage(source_tree):
    root, ledger = source_tree
    path = root / "sonaloop/mcp_server/_tools_native.py"
    path.write_text(path.read_text().replace("@mcp.tool()", "@mcp.tool(name=TOOL_NAME)", 1))
    assert any("Nonliteral native tool name" in error for error in coverage_errors(ledger, source_root=root))


@pytest.mark.parametrize("registration", ["mcp.add_tool(read_note)", "mcp.tool()(read_note)"])
def test_imperative_registration_requires_an_explicit_static_inventory_extension(source_tree, registration):
    root, ledger = source_tree
    path = root / "sonaloop/mcp_server/_tools_native.py"
    path.write_text(path.read_text().replace("\nraise AssertionError", f"\n    {registration}\nraise AssertionError"))
    assert any("Unsupported dynamic native registration" in error
               for error in coverage_errors(ledger, source_root=root))


def test_duplicate_native_registration_is_reported(source_tree):
    root, ledger = source_tree
    path = root / "sonaloop/mcp_server/__init__.py"
    path.write_text(path.read_text() + "    register_native(mcp)\n")
    assert any("Duplicate or recursive native registration" in error
               for error in coverage_errors(ledger, source_root=root))


@pytest.mark.parametrize("ledger", [[], {}, {"tools": None}, {"tools": [None]}])
def test_malformed_ledger_returns_diagnostics(source_tree, ledger):
    root, _ = source_tree
    assert coverage_errors(ledger, source_root=root)


def test_missing_source_returns_a_diagnostic(source_tree):
    root, ledger = source_tree
    (root / "sonaloop/mcp_server/_tools_native.py").unlink()
    assert any("Cannot inspect native tool sources" in error
               for error in coverage_errors(ledger, source_root=root))

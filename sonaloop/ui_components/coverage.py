"""Static MCP UI coverage checks; never import a tool module or invoke a service."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "sonaloop.mcp-ui-coverage.v1"
STATUSES = frozenset({"planned", "existing", "supported", "not_applicable"})
PRESENTATIONS = frozenset({"surface", "action_confirmation", "export"})
EXEMPTIONS = frozenset({"context_only", "reference_only", "admin_only",
                        "protocol_only", "execution_only"})
_ROOT = Path(__file__).resolve().parents[2]
_FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)


def coverage_data(*, source_root: str | Path | None = None) -> dict[str, Any]:
    """Read a fresh ledger from the package source tree, without runtime discovery."""
    root = Path(source_root) if source_root is not None else _ROOT
    return json.loads((root / "sonaloop/ui_components/coverage.json").read_text(encoding="utf-8"))


def _parse(root: Path, module: str) -> ast.Module:
    return ast.parse((root / module).read_text(encoding="utf-8"), filename=module)


def _annotations(root: Path) -> dict[str, str]:
    tree = _parse(root, "sonaloop/mcp_server/_annotations.py")
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if not any(isinstance(target, ast.Name) and target.id == "TOOL_ANNOTATIONS" for target in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            break
        result = {}
        for key, value in zip(node.value.keys, node.value.values):
            if (not isinstance(key, ast.Constant) or not isinstance(key.value, str)
                    or not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name)
                    or value.func.id not in {"R", "W", "D"} or key.value in result):
                raise ValueError("TOOL_ANNOTATIONS must contain unique literal tools with R/W/D annotations")
            result[key.value] = value.func.id
        return result
    raise ValueError("TOOL_ANNOTATIONS is missing or is not a static dictionary")


def _inventory(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Follow the core register_* calls made by build_server, using source AST only.

    Entry-point extensions are deliberately outside this source inventory. Native
    calls are syntactic services.* / _service().* anchors, not a transitive graph.
    Unresolvable registration shapes produce errors instead of a partial pass.
    """
    errors: list[str] = []
    annotations = _annotations(root)
    inventory: dict[str, dict[str, Any]] = {}
    visited: set[tuple[str, str]] = set()

    def visit(module: str, symbol: str) -> None:
        if (module, symbol) in visited:
            errors.append(f"Duplicate or recursive native registration: {module}:{symbol}")
            return
        visited.add((module, symbol))
        tree = _parse(root, module)
        functions = {node.name: node for node in tree.body if isinstance(node, _FUNCTION)}
        function = functions.get(symbol)
        if function is None:
            errors.append(f"Missing native registration function: {module}:{symbol}")
            return
        imports = {}
        for node in [*tree.body, *ast.walk(function)]:
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = (
                        str(Path(module).parent / (node.module.replace(".", "/") + ".py")), alias.name)
        tool_decorators = {id(decorator) for node in ast.walk(function) if isinstance(node, _FUNCTION)
                           for decorator in node.decorator_list if isinstance(decorator, ast.Call)
                           and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool"}
        for node in ast.walk(function):
            if isinstance(node, _FUNCTION):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                        errors.append(f"Unsupported native tool decorator: {module}:{node.lineno}")
                    if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                            and decorator.func.attr == "tool"):
                        continue
                    name_node = next((kw.value for kw in decorator.keywords if kw.arg == "name"), None)
                    if decorator.args or any(kw.arg is None for kw in decorator.keywords):
                        errors.append(f"Unsupported native tool decorator: {module}:{node.lineno}")
                        continue
                    if name_node is not None and (not isinstance(name_node, ast.Constant)
                                                  or not isinstance(name_node.value, str)):
                        errors.append(f"Nonliteral native tool name: {module}:{node.lineno}")
                        continue
                    tool = name_node.value if name_node is not None else node.name
                    if tool in inventory:
                        errors.append(f"Duplicate native tool: {tool}")
                        continue
                    calls = {ast.unparse(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)}
                    inventory[tool] = {
                        "module": module, "symbol": node.name, "line": node.lineno,
                        "calls": sorted(call for call in calls if call.startswith(("services.", "_service()."))),
                        "annotation": annotations.get(tool),
                        "operation_id": any(arg.arg == "operation_id" for arg in
                                            [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]),
                    }
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "add_tool":
                errors.append(f"Unsupported dynamic native registration: {module}:{node.lineno}")
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "tool"
                    and id(node) not in tool_decorators):
                errors.append(f"Unsupported dynamic native registration: {module}:{node.lineno}")
            if not isinstance(node.func, ast.Name):
                continue
            name = node.func.id
            target = imports.get(name)
            registration = (target[1] if target else name).startswith("register_")
            if not registration:
                continue
            if target:
                visit(*target)
            elif name in functions:
                visit(module, name)
            else:
                errors.append(f"Unresolved native registration: {module}:{name}")

    visit("sonaloop/mcp_server/__init__.py", "build_server")
    for tool in sorted(set(inventory) - set(annotations)):
        errors.append(f"Native tool lacks annotation: {tool}")
    for tool in sorted(set(annotations) - set(inventory)):
        errors.append(f"Annotation has no registered native tool: {tool}")
    if not inventory:
        errors.append("Native tool inventory is empty")
    return inventory, errors


def coverage_errors(ledger: dict[str, Any] | None = None, *,
                    source_root: str | Path | None = None) -> list[str]:
    """Return ledger/schema/source drift, without inferring runtime UI support.

    Native anchors bind the inspected functions, their line numbers, direct
    service-call spellings, annotation class and operation_id parameter presence.
    The source commit is a declared baseline; this check neither runs Git nor
    attests that the working tree is that immutable release.
    """
    root = Path(source_root) if source_root is not None else _ROOT
    try:
        data = coverage_data(source_root=root) if ledger is None else ledger
    except (OSError, ValueError) as error:
        return [f"Cannot read coverage ledger: {error}"]
    if not isinstance(data, dict):
        return ["Coverage ledger must be an object"]
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA:
        errors.append("Invalid coverage schema_version")
    source = data.get("native_source")
    if (not isinstance(source, dict) or not isinstance(source.get("repository"), str)
            or not source["repository"].strip() or not isinstance(source.get("commit"), str)
            or not re.fullmatch(r"[a-f0-9]{40}", source["commit"])):
        errors.append("Invalid native_source repository or commit")
    if not isinstance(data.get("scope"), str) or not data["scope"].strip():
        errors.append("Coverage scope must be a nonblank explanation")
    rows = data.get("tools")
    if not isinstance(rows, list):
        return errors + ["Coverage tools must be a list"]
    try:
        native, native_errors = _inventory(root)
        errors.extend(native_errors)
    except (OSError, ValueError, SyntaxError) as error:
        return errors + [f"Cannot inspect native tool sources: {error}"]
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("tool"), str) or not row["tool"].strip():
            errors.append(f"Invalid coverage tool row: {index}")
            continue
        tool = row["tool"]
        if tool in seen:
            errors.append(f"Duplicate coverage tool: {tool}")
        seen.add(tool)
        family = row.get("family")
        if not isinstance(family, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", family):
            errors.append(f"Invalid family: {tool}")
        status, treatment = row.get("status"), row.get("treatment")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"Invalid status: {tool}")
        if not isinstance(treatment, str) or treatment not in PRESENTATIONS | EXEMPTIONS:
            errors.append(f"Invalid treatment: {tool}")
        elif (status == "not_applicable") != (treatment in EXEMPTIONS):
            errors.append(f"Invalid exemption/status pairing: {tool}")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"Missing nonblank coverage reason: {tool}")
        anchor = row.get("native")
        if not isinstance(anchor, dict):
            errors.append(f"Invalid native anchor: {tool}")
            continue
        expected = native.get(tool)
        if expected is None:
            continue
        for field, value in expected.items():
            actual = anchor.get(field)
            # bool is an int subclass, so equality alone would accept line=True.
            if type(actual) is not type(value) or actual != value:
                errors.append(f"Native {field} anchor drift: {tool}")
    for tool in sorted(set(native) - seen):
        errors.append(f"Missing coverage tool: {tool}")
    for tool in sorted(seen - set(native)):
        errors.append(f"Coverage tool is not registered: {tool}")
    return errors

"""Public pure Component entry point over the existing family projections.

These authored view-model props are presentation input, not MCP call arguments.
Selecting a registered projection never executes its corresponding tool.
"""
from __future__ import annotations

import json

from .registry import SURFACES


def render_component_props(component_id: str, props: dict):
    """Render {name, value} through the customer's existing pure projection."""
    if not isinstance(props, dict) or set(props) != {"name", "value"}:
        raise ValueError("Expected public Component name and value props")
    surface = SURFACES.get(props["name"]) if isinstance(props["name"], str) else None
    if surface is None or surface.component_id != component_id:
        raise ValueError("Projection does not belong to this Component")
    pending, nodes = [(props, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 2048 or depth > 12:
            raise ValueError("Public Component props exceed traversal limits")
        if isinstance(value, dict):
            if any(key in {"_meta", "__proto__", "constructor", "prototype"} for key in value):
                raise ValueError("Private metadata is not a public Component prop")
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    if len(json.dumps(props, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()) > 8192:
        raise ValueError("Public Component props exceed the byte limit")
    return surface.render(props["value"])

"""The product's captured URL snapshot body, shared without navigation or recapture."""
from __future__ import annotations

from .library import _kit, collection


def snapshot_label(snapshot: dict):
    from ..web._i18n import t
    return (t("artifact_captured") if snapshot.get("ok") else t("research_reference_not_captured")
            if snapshot.get("mode") == "skipped" else t("artifact_capture_failed"))


def snapshot_content(snapshot: dict, *, passive=False):
    from ..web import ui
    from ..web._i18n import t
    h, _, _ = _kit()
    headings = snapshot.get("headings") or []
    text = snapshot.get("text", "") or snapshot.get("error", "")
    if not text:
        text = t("research_reference_empty_text") if snapshot.get("ok") else snapshot_label(snapshot)
    return h("div", {"class_": "sl-prose sl-research-reference-content"},
             h("p", {}, snapshot["description"]) if snapshot.get("description") else None,
             h("p", {"class_": "muted"}, " · ".join(headings if passive else headings[:8])) if headings else None,
             h("div", {"class_": "sl-research-reference-text"}, text) if passive
             else ui.clamp(text, threshold=ui.SECTION_CLAMP))


def _record(value):
    if (not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key]
                                         for key in ("id", "title", "url"))
            or value.get("kind") not in {"url", "prototype", "variant"}
            or not isinstance(value.get("snapshot"), dict)):
        raise ValueError("Expected native URL artifact and snapshot")
    snapshot = value["snapshot"]
    if (type(snapshot.get("ok")) is not bool or not isinstance(snapshot.get("headings"), list)
            or any(not isinstance(item, str) for item in snapshot["headings"])
            or any(key in snapshot and not isinstance(snapshot[key], str)
                   for key in ("text", "description", "error", "mode", "captured_at", "content_hash"))
            or any(key in value and not isinstance(value[key], str) for key in ("label", "captured_at", "content_hash"))):
        raise ValueError("Expected actual captured snapshot status and supplied text")
    return value


def reference(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    value = _record(value)
    snapshot = value["snapshot"]
    status = snapshot_label(snapshot)
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("reference_kind")),
               h("h2", {}, value["title"])),
             h("p", {}, t("artifact_kind_" + value["kind"]), " · ", value.get("label", "")),
             h("p", {"class_": "sl-research-reference-url"}, value["url"]),
             h("p", {"class_": "sl-research-status"}, status),
             h("p", {"class_": "muted small"}, value["captured_at"]) if value.get("captured_at") else None,
             h("h3", {}, t("reference_snapshot_h")), snapshot_content(snapshot, passive=True)), "ready"


def references(value):
    from ..web._i18n import t
    if not isinstance(value, list):
        raise ValueError("Expected native URL artifact list")
    cards = [reference(item)[0] for item in value]
    return collection(cards, empty=t("no_references")), "ready" if cards else "empty"


def removed(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if not isinstance(value, dict) or type(value.get("deleted")) is not int or value["deleted"] < 0:
        raise ValueError("Expected actual native URL reference deletion count")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("references_h")),
             h("p", {}, t("research_references_removed", n=value["deleted"]))), "ready"

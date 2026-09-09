"""Shared file identity, excerpt and provenance; media is explicitly prepared by the host."""
from __future__ import annotations

from .library import _kit, collection


def file_identity(asset: dict):
    from ..web._presence import asset_size
    h, _, _ = _kit()
    meta = " · ".join(x for x in (asset_size(asset), asset.get("media_type", "")) if x)
    return h("div", {"class_": "sl-file__info sl-research-file-info"},
             h("span", {"class_": "sl-file__name sl-research-file-name"}, asset.get("filename", "")),
             h("span", {"class_": "sl-file__meta sl-research-file-meta"}, meta))


def provenance_content(asset: dict, *, source, when, chain, passive=False):
    from ..web._components import _icon
    from ..web._i18n import t
    from ..web._presence import asset_direction
    h, fragment, raw = _kit()
    rows = [
        ("dot", t("asset_generated") if asset_direction(asset) == "out" else t("asset_received"), when),
        ("link", t("asset_source"), source), ("download", t("asset_supersedes"), chain),
        ("panel", t("notes_h"), asset.get("notes", "")),
    ]
    props = [h("div", {"class_": "sl-prop sl-research-asset-prop"},
               h("span", {"class_": "sl-prop__k sl-research-asset-key"}, None if passive else raw(_icon(icon)), label),
               h("span", {"class_": "sl-prop__v sl-research-asset-value"}, value))
             for icon, label, value in rows if value not in (None, "", "—")]
    return h("div", {"class_": "sec sl-research-asset-provenance" if passive else "sec", "id": "sec-provenance"},
             h("h2", {}, t("provenance_h")),
             h("div", {"class_": "sl-props sl-props--quiet sl-research-asset-props"}, fragment(*props)))


def asset_content(asset: dict, *, preview, file_card, provenance, passive=False):
    from ..web import ui
    from ..web._i18n import t
    h, fragment, _ = _kit()
    excerpt = (asset.get("text_excerpt") or "").strip()
    return fragment(preview, h("div", {"class_": "sec", "id": "sec-file"}, file_card),
                    h("div", {"class_": "sec", "id": "sec-excerpt"},
                      h("h2", {}, t("asset_excerpt_h")),
                      h("div", {"class_": "sl-research-asset-excerpt"}, excerpt) if passive
                      else ui.clamp(excerpt, threshold=ui.SECTION_CLAMP)) if excerpt else None,
                    provenance)


def _record(value):
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]
            or not isinstance(value.get("filename"), str) or not value["filename"]
            or not isinstance(value.get("media_type"), str)
            or type(value.get("bytes")) is not int or value["bytes"] < 0
            or value.get("kind") not in {"image", "screenshot", "document", "file"}):
        raise ValueError("Expected complete native asset identity and file metadata")
    for key in ("title", "source", "notes", "created_at", "text_excerpt"):
        if key in value and not isinstance(value[key], str):
            raise ValueError("Expected native asset text")
    if "supersedes" in value and (not isinstance(value["supersedes"], list) or any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str)
            or any(key in item and not isinstance(item[key], str) for key in ("filename", "created_at"))
            for item in value["supersedes"])):
        raise ValueError("Expected native asset supersession references")
    return value


def asset(value):
    from ..web._i18n import t
    from ..web._presence import asset_direction
    h, fragment, _ = _kit()
    value = _record(value)
    source = h("span", {}, value.get("source", "")) if value.get("source") else None
    chain = fragment(*(h("div", {}, item.get("filename") or item["id"],
                         " · " + item["created_at"] if item.get("created_at") else None)
                       for item in value.get("supersedes", []))) if value.get("supersedes") else None
    provenance = provenance_content(value, source=source, when=value.get("created_at"), chain=chain, passive=True)
    card = h("div", {"class_": "sl-file sl-research-asset-file"}, file_identity(value))
    # A metadata response does not contain pixels. Paths/URLs never become a hidden fetch.
    preview = h("p", {"class_": "muted small"}, t("research_asset_no_pixels")) if (
        value["kind"] in {"image", "screenshot"} or value.get("preview_url")) else None
    body = asset_content(value, preview=preview, file_card=card, provenance=provenance, passive=True)
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("asset_kind")),
               h("h2", {}, value.get("title") or value["filename"])),
             h("p", {}, t("asset_kind_" + value["kind"]), " · ",
               t("asset_dir_out") if asset_direction(value) == "out" else t("asset_dir_in")),
             body), "ready"


def assets(value):
    from ..web._i18n import t
    if not isinstance(value, list):
        raise ValueError("Expected native asset list")
    cards = [asset(item)[0] for item in value]
    return collection(cards, empty=t("research_assets_empty")), "ready" if cards else "empty"


def removed(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if not isinstance(value, dict) or type(value.get("deleted")) is not int or value["deleted"] < 0:
        raise ValueError("Expected native asset detach count")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("assets_h")),
             h("p", {}, t("research_assets_removed", n=value["deleted"])),
             h("p", {"class_": "muted small"}, t("research_asset_binary_retained"))), "ready"

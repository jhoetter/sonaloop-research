"""The same Note and Section content rendered in the product and MCP Apps."""
from __future__ import annotations

from pathlib import Path


def _kit():
    # Lazy imports avoid a cycle with web's route registration. No Store/service
    # is consulted by any renderer in this module.
    from ..web._html import h, fragment, raw, register_css
    register_css((Path(__file__).parents[1] / "web/assets/research-view/research.css").read_text())
    return h, fragment, raw


def note_content(note: dict):
    from ..web._components import _md
    h, _, raw = _kit()
    return h("div", {"class_": "sl-prose sl-research-note-content"}, raw(_md(note.get("text", ""))))


def note_card(note: dict):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card", "data-component": "research-note"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("notes_h")),
               h("h2", {}, note.get("title") or t("notes_h"))), note_content(note))


def section_content(section: dict, members: list[dict] | None = None):
    from ..web._i18n import t
    h, fragment, _ = _kit()
    rows = []
    for member in members or []:
        head = h("a", {"href": member["href"]}, member["title"]) if member.get("href") else member.get("title", "")
        rows.append(h("div", {"class_": "strow sl-research-member"}, h("b", {}, head), " ",
                      h("span", {"class_": "muted small"}, member.get("kind", "")),
                      h("div", {"class_": "muted small sl-note-summary"}, (member.get("summary") or "")[:240])))
    # A plain Section DTO contains references, not resolved member titles. Show
    # those references honestly; never fetch or invent their content here.
    if members is None:
        rows = [h("li", {}, node_id) for node_id in section.get("member_ids", [])]
        body = h("ul", {"class_": "sl-research-references"}, rows) if rows else h("p", {"class_": "muted"}, t("no_members"))
    else:
        body = fragment(rows) if rows else h("p", {"class_": "muted"}, t("no_members"))
    return h("div", {"class_": "sl-research-section-content"},
             h("p", {"class_": "sub"}, section["note"]) if section.get("note") else None, body)


def section_card(section: dict, members: list[dict] | None = None):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card", "data-component": "research-section"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("section")),
               h("h2", {}, section.get("title") or t("section"))), section_content(section, members))


def collection(cards: list, *, empty: str, total: int | None = None, has_more: bool = False):
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-collection"}, cards or h("p", {"class_": "sl-research-empty", "role": "status"}, empty),
             h("p", {"class_": "sl-research-page", "data-total": total},
               f"{len(cards)} / {total}" if total is not None else None,
               " · …" if has_more else None) if total is not None or has_more else None)

"""Project and search presentation shared with the product's real entry points."""
from __future__ import annotations

from .library import _kit, collection, note_content


def project_heading(project: dict, *, icon=None, level: str = "h1"):
    h, fragment, _ = _kit()
    return fragment(h(level, {"class_": "h1 sl-project-title" if level == "h1" else None}, icon, project.get("title", "")),
                    h("p", {"class_": "lead"}, project.get("goal", "")))


def project_card(project: dict):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"},
             h("span", {"class_": "sl-research-kind"}, t("project")), project_heading(project, level="h2"),
             h("p", {"class_": "muted"}, project.get("description", "")) if project.get("description") else None)


def search_hit_content(title: str, subtitle: str = "", date: str = ""):
    """The palette row's existing semantic content; links/icons belong to its shell."""
    h, fragment, _ = _kit()
    return fragment(h("span", {"class_": "sl-cmdk-title"}, title),
                    h("span", {"class_": "sl-cmdk-desc"}, subtitle) if subtitle else None,
                    h("span", {"class_": "sl-cmdk-meta"}, date) if date else None)


def search_card(hit: dict, *, full: bool = False):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-search"},
             h("header", {}, search_hit_content(hit.get("title", ""), "" if full else hit.get("text", ""))),
             note_content(hit) if full else None)


def projects(value):
    from ..web._i18n import t
    if not isinstance(value, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in value):
        raise ValueError("Expected native project summaries")
    return collection([project_card(item) for item in value], empty=t("no_projects")), "ready" if value else "empty"


def project(value):
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not isinstance(value.get("title"), str):
        raise ValueError("Expected native project")
    return project_card(value), "ready"


def search(value):
    from ..web._i18n import t
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise ValueError("Expected native search results")
    rows = value["results"]
    if any(not isinstance(row, dict) or not isinstance(row.get("title"), str) or not isinstance(row.get("text"), str) for row in rows):
        raise ValueError("Expected native search hit")
    return collection([search_card(row) for row in rows], empty=t("cmdk_empty")), "ready" if rows else "empty"


def fetched(value):
    if not isinstance(value, dict) or not isinstance(value.get("title"), str) or not isinstance(value.get("text"), str):
        raise ValueError("Expected native fetched document")
    return search_card(value, full=True), "ready"

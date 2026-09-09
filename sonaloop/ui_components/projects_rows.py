"""Project semantic bodies; product adapters supply resolved display fragments."""
from __future__ import annotations

from .library import _kit


def t(key, **kwargs):
    from ..web._i18n import t as translate
    return translate(key, **kwargs)


def record(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native project object")
    return value


def texts(value, required=(), optional=()):
    record(value)
    for key in required:
        if type(value.get(key)) is not str:
            raise ValueError(f"Expected native project text: {key}")
    for key in optional:
        if key in value and type(value[key]) is not str:
            raise ValueError(f"Expected native project text: {key}")


def identity(value, key="project_id"):
    texts(value, (key,))
    if not value[key].strip():
        raise ValueError("Expected nonempty native project identity")


def strings(value):
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise ValueError("Expected native project text list")
    return value


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Expected native nonnegative project count")
    return value


def fields(pairs):
    h, fragment, _ = _kit()
    return h("dl", {"class_": "sl-research-fields"}, [fragment(h("dt", {}, label),
        h("dd", {}, "—" if value is None else str(value).lower() if type(value) is bool else value))
        for label, value in pairs])


def project_heading(project, *, icon=None, level="h1"):
    h, fragment, _ = _kit()
    if level not in ("h1", "h2", "h3"):
        raise ValueError("Expected a project heading level")
    return fragment(h(level, {"class_": "h1 sl-project-title" if level == "h1" else None},
                      icon, project.get("title", "")), h("p", {"class_": "lead"}, project.get("goal", "")))


def archive_notice(project):
    h, _, _ = _kit()
    return (h("p", {"class_": "sl-project-meta", "data-project-archived": True},
              t("archive_non_destructive")) if str(project.get("status") or "") == "archived" else "")


def lineage_content(project, *, prepared_refs=None, heading_icon=None):
    """Existing product lineage, with tenant-resolved links supplied by its adapter."""
    h, fragment, _ = _kit()
    prepared_refs = prepared_refs or {}
    items = []
    for key, label in (("supersedes_project_id", t("lineage_supersedes")),
                       ("superseded_by_project_id", t("lineage_superseded_by"))):
        pid = str(project.get(key) or "")
        if pid:
            items.append(h("li", {}, label, ": ", prepared_refs.get(key, h("code", {}, pid))))
    if not items:
        return ""
    return h("details", {"class_": "sl-project-lineage", "id": "project-lineage",
                         "aria-label": t("lineage_h")},
             h("summary", {}, heading_icon, t("lineage_h")),
             h("ul", {"class_": "sl-pu-caps"}, fragment(items)))


def project_body(project, *, icon=None, level="h1", description=False, prepared=None, passive=False):
    """The product header's exact order, with passive native details when requested.

    Prepared fragments are a product-only seam; tool projections never accept
    fragments from native data. No resolution, media probes or normalization here.
    """
    h, fragment, _ = _kit()
    prepared = prepared or {}
    details = None
    if passive:
        pairs = [("id", project["id"])]
        for key, label in (("slug", "slug"), ("status", t("status_h")),
                           ("methodology", t("methodology_h")), ("created_at", t("created")),
                           ("updated_at", t("rpj_updated")), ("workflow_trace_id", "workflow_trace_id"),
                           ("operation_id", t("rpj_operation")), ("operation_state", t("rpj_operation_state")),
                           ("governance_contract", t("rpj_governance")), ("url", t("url_h"))):
            if key in project:
                pairs.append((label, project[key]))
        details = fragment(fields(pairs), h("p", {}, t("participants"), ": ",
            ", ".join(project.get("persona_ids", []))) if "persona_ids" in project else None)
    return fragment(project_heading(project, icon=icon, level=level),
        h("p", {"class_": "muted"}, project["description"]) if description and project.get("description") else None,
        prepared.get("experience_header"), prepared.get("creator"), prepared.get("cohort"),
        archive_notice(project), prepared.get("lineage") if "lineage" in prepared else lineage_content(project), details)


def icon_content(spec):
    """The supplied icon specification, never interpreted as markup or a path."""
    h, _, _ = _kit()
    texts(spec, ("kind",), ("name", "svg", "svg_path", "url", "prompt", "generated_at", "updated_at"))
    if spec["kind"] not in ("regular", "custom"):
        raise ValueError("Unknown native project icon kind")
    if spec["kind"] == "regular":
        identity(spec, "name")
    elif not any(spec.get(key) for key in ("svg", "svg_path", "url")):
        raise ValueError("Expected a supplied custom icon specification")
    pairs = [("kind", spec["kind"])]
    for key, label in (("name", "name"), ("svg_path", "svg_path"), ("url", t("url_h")),
                       ("prompt", t("rpj_prompt")), ("generated_at", t("rpj_generated")),
                       ("updated_at", t("rpj_updated"))):
        if key in spec:
            pairs.append((label, spec[key]))
    if "svg" in spec:
        pairs.append((t("rpj_svg_supplied"), True))
    return h("div", {"class_": "sl-research-project-icon"}, fields(pairs),
        h("p", {"class_": "sl-research-meta"}, t("rpj_icon_notice")),
        h("details", {}, h("summary", {}, "SVG"),
          h("code", {"class_": "sl-research-prose"}, spec["svg"])) if "svg" in spec else None)

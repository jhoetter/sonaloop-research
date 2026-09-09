"""Catalog identity and origin bodies shared with the existing Product inspector."""
from __future__ import annotations

import math

from .library import _kit
from .projects_rows import record, texts, identity, strings, count, fields, disclosure, t


def records(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected catalog rows")
    return value


def nullable_texts(value, keys):
    record(value)
    for key in keys:
        if key in value and value[key] is not None and type(value[key]) is not str:
            raise ValueError(f"Expected catalog text or null: {key}")


def prose(value):
    if type(value) is not str:
        raise ValueError("Expected catalog prose")
    return _kit()[0]("p", {"class_": "sl-research-prose"}, value)


def section(label, body):
    return _kit()[0]("section", {}, _kit()[0]("h3", {}, label), body or prose(t("rcat_no_entries")))


def text_list(value):
    strings(value)
    h, _, _ = _kit()
    return h("ul", {}, [h("li", {}, item) for item in value]) if value else prose(t("rcat_no_entries"))


def facet_values(value):
    record(value)
    h, fragment, _ = _kit()
    return h("dl", {"class_": "sl-research-fields"},
        [fragment(h("dt", {}, key), h("dd", {}, text_list(items)))
         for key, items in value.items()]) if value else prose(t("rcat_no_entries"))


def counts(value):
    record(value)
    for number in value.values():
        count(number)
    return fields(value.items()) if value else prose(t("rcat_no_entries"))


def catalog_identity_content(entry, *, passive=False):
    """The existing Product title/role line, including its original class names."""
    identity(entry, "slug")
    nullable_texts(entry, ("display_name", "role"))
    h, _, _ = _kit()
    return h("span", {"class_": "title" + (" sl-research-catalog-identity" if passive else "")},
        h("span", {"class_": "sl-catalog-row-title"},
          h("span", {"class_": "sl-research-catalog-name"} if passive else {},
            entry.get("display_name") or entry["slug"]),
          h("span", {"class_": "sl-catalog-slug" + (" sl-research-catalog-slug" if passive else "")}, entry["slug"])),
        h("span", {"class_": "muted small"}, f' · {entry.get("role") or "—"}'))


def catalog_row(entry, *, prepared=None, passive=False):
    """Product supplies avatar/meta/action fragments; native data never does."""
    h, fragment, _ = _kit()
    body = catalog_identity_content(entry, passive=passive)
    if not passive:
        prepared = prepared or {}
        return h("div", {"class_": "row"}, prepared.get("avatar"), body,
            h("span", {"class_": "right"}, fragment([*(prepared.get("meta") or []), prepared.get("action")])))
    if prepared is not None:
        raise ValueError("Passive catalog rows cannot accept Product controls")
    if type(entry.get("has_avatar")) is not bool:
        raise ValueError("Expected declared catalog avatar availability")
    texts(entry, optional=("tier",))
    facets = facet_values(entry.get("facets"))
    return h("article", {"class_": "sl-research-card sl-research-catalog-entry"},
        h("h3", {}, body), disclosure(t("rpx_record_details"),
            fields([(key, entry[key]) for key in ("slug", "tier", "has_avatar") if key in entry]), facets))


def provenance_tooltip(stamp):
    """Exactly the Product's supplied ref/pull-time tooltip; no inference/read."""
    nullable_texts(stamp, ("ref", "pulled_at"))
    return " · ".join(value for value in (stamp.get("ref"), stamp.get("pulled_at")) if value)


def provenance_badge(stamp, *, passive=False):
    if not stamp:
        return ""
    tip = provenance_tooltip(stamp)
    if passive:
        return _kit()[0]("span", {"class_": "sl-research-kind", "title": tip or None}, t("persona_from_catalog"))
    from ..web._components import _label
    return _label(t("persona_from_catalog"), "var(--accent)", "soft", True, tip or None)


def provenance_content(stamp):
    if stamp is None:
        return prose(t("rcat_no_provenance"))
    record(stamp)
    keys = ("source", "repo", "ref", "slug", "pack", "base_url", "manifest_generated_at", "pulled_at")
    nullable_texts(stamp, keys)
    if "schema_version" in stamp and stamp["schema_version"] is not None:
        count(stamp["schema_version"])
    _, fragment, _ = _kit()
    return fragment(provenance_badge(stamp, passive=True), disclosure(t("rcat_provenance"),
        fields([(key, stamp[key]) for key in (*keys, "schema_version") if key in stamp])
        if stamp else prose(t("rcat_no_provenance"))))


def recommendation_row(value):
    identity(value, "slug")
    texts(value, ("display_name",))
    for key in ("score", "base_score", "diversity_bonus"):
        if type(value.get(key)) not in (int, float) or not math.isfinite(value[key]):
            raise ValueError("Expected supplied catalog recommendation score")
    if type(value.get("seeded")) is not bool:
        raise ValueError("Expected supplied catalog seed flag")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h3", {}, value["display_name"] or value["slug"]),
        fields(((t("rcat_score"), value["score"]), (t("rcat_base_score"), value["base_score"]),
                (t("rcat_diversity_bonus"), value["diversity_bonus"]))),
        section(t("rcat_rationale"), text_list(value.get("rationale"))),
        disclosure(t("rpx_record_details"),
            fields((("slug", value["slug"]), ("seeded", value["seeded"]))),
            facet_values(value.get("facets"))))


def status_row(value):
    identity(value, "slug")
    identity(value, "id")
    texts(value, ("status",), ("tier",))
    nullable_texts(value, ("pulled_at", "ref", "pack", "local_updated_at", "catalog_updated_at"))
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h3", {}, value["slug"]),
        fields(((t("status_h"), value["status"]),)), disclosure(t("rpx_record_details"),
        fields([(key, value[key]) for key in ("id", "slug", "tier", "pulled_at", "ref", "pack",
                                            "local_updated_at", "catalog_updated_at") if key in value])))


def landed_row(value):
    identity(value, "slug")
    identity(value, "id")
    texts(value, ("display_name",))
    if "provenance" not in value:
        raise ValueError("Expected native landed provenance field")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h3", {}, value["display_name"] or value["slug"]),
        fields((("slug", value["slug"]), ("id", value["id"]))), provenance_content(value["provenance"]))


def skipped_rows(values):
    h, _, _ = _kit()
    body = []
    for value in records(values):
        identity(value, "slug")
        texts(value, ("reason",), ("tier",))
        body.append(h("li", {}, h("strong", {}, value["slug"]), prose(value["reason"]),
            fields((("tier", value["tier"]),)) if "tier" in value else None))
    return h("ul", {}, body) if body else prose(t("rcat_no_entries"))

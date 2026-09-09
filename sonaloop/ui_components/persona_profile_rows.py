"""Existing Product profile sections and supplied native metadata, without I/O."""
from __future__ import annotations

import math

from .library import _kit
from .projects_rows import record, identity, texts, strings, fields, disclosure, t


def profile_record(value):
    identity(value, "id")
    texts(value, ("slug", "display_name", "source_description", "created_at", "updated_at"))
    texts(value.get("role"), ("title",))
    texts(value.get("company_context"), ("industry",))
    for key in ("goals", "constraints", "tools", "tool_ids", "pain_points", "success_criteria"):
        strings(value.get(key))
    for key in ("identity_traits", "segment", "demographics", "personality"):
        record(value.get(key))
    records(value.get("relationships"))


def records(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected supplied native profile records")
    return value


def subtitle(value):
    """The Product fallback hero's existing role and industry text."""
    return f'{value["role"]["title"]} · {value["company_context"]["industry"]}'


def profile_row(value, *, prepared=None, passive=False):
    """Product supplies its avatar/actions; native list cards never resolve them."""
    h, _, _ = _kit()
    identity(value, "id")
    texts(value, ("display_name",))
    role = value.get("role")
    if isinstance(role, dict):
        texts(role, ("title",))
        role = role["title"]
    if type(role) is not str:
        raise ValueError("Expected supplied native Persona role")
    if not passive:
        from ..web._routes_lists import _row
        prepared = prepared or {}
        return _row(f'/personas/{value["id"]}', prepared.get("avatar"), value["display_name"],
            prepared.get("right"), sub=role, actions=prepared.get("actions"))
    texts(value, ("slug", "segment", "age_range", "url"))
    return h("article", {"class_": "sl-research-card sl-research-profile"}, h("h2", {}, value["display_name"]),
        h("p", {"class_": "sl-research-prose"}, role), h("p", {}, value["segment"]),
        fields(((t("rpf_age_range"), value["age_range"]),)),
        disclosure(t("rpx_record_details"), fields((key, value[key]) for key in ("id", "slug", "url"))))


def heading(value, *, top=None, passive=False):
    h, fragment, _ = _kit()
    if passive:
        return fragment(h("h2", {}, value["display_name"]), h("p", {"class_": "sl-research-prose"}, subtitle(value)))
    from ..web._components import _hero
    return _hero(value["display_name"], sub=subtitle(value), top=top)


def list_section(title, value, *, section_id=None, fallback=False, passive=False):
    """Shared goals/tools/pain text; Product keeps its existing pills and anchors."""
    h, _, raw = _kit()
    strings(value)
    if passive:
        return h("section", {"class_": "sl-research-profile-section"}, h("h3", {}, title),
            h("ul", {}, [h("li", {}, item) for item in value]) if value else h("p", {}, t("none")))
    from ..web._components import _pills
    return h("div", {"class_": "sec", "id": section_id,
        **({"data-persona-surface-fallback": True} if fallback else {})}, h("h2", {}, title), raw(_pills(value)))


def relationships_content(value):
    h, fragment, _ = _kit()
    rows = []
    for item in records(value):
        texts(item, ("name", "type", "friction"))
        rows.append(h("p", {}, h("strong", {}, item["name"]), " ",
            h("span", {"class_": "muted"}, f'— {item["type"]}: {item["friction"]}')))
    return fragment(rows)


def metadata(value):
    """Named supplied detail values only; execution tokens never become prose."""
    h, fragment, _ = _kit()
    if isinstance(value, dict):
        return h("dl", {"class_": "sl-research-fields"}, [fragment(h("dt", {}, key), h("dd", {}, metadata(item)))
            for key, item in value.items() if key not in {"dispatch_token", "execution_grant", "confirmation_token",
                "approval_token", "access_token", "refresh_token", "preview_token"}])
    if isinstance(value, list):
        return h("ul", {}, [h("li", {}, metadata(item)) for item in value]) if value else h("span", {}, t("none"))
    if value is None:
        return h("span", {}, "null")
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("Expected finite supplied profile value")
    elif type(value) not in (str, bool):
        raise ValueError("Expected supplied native profile metadata")
    return h("span", {}, str(value).lower() if type(value) is bool else value)


def history(title, value):
    h, _, _ = _kit()
    entries = []
    for item in records(value):
        title_text = next((item[key] for key in ("summary", "task", "date", "timestamp", "id")
            if isinstance(item.get(key), str) and item[key]), t("rpf_record"))
        entries.append(h("article", {"class_": "sl-research-profile-history"}, h("h3", {}, title_text), metadata(item)))
    return disclosure(title, entries if entries else h("p", {}, t("rpf_no_history")))


def profile_content(value):
    """Native profile, deliberately distinct from the interactive surface DTO."""
    h, fragment, _ = _kit()
    profile_record(value)
    details = [("identity_traits", t("rpf_identity")), ("segment", t("rpf_segment")),
        ("demographics", t("rpf_demographics")), ("role", t("role")), ("company_context", t("rpf_company")),
        ("personality", t("rpf_personality")), ("provenance", t("rpf_provenance")), ("capabilities", t("capabilities_h"))]
    return fragment(heading(value, passive=True),
        h("p", {"class_": "sl-research-prose"}, t("rpf_native_notice")),
        list_section(t("goals"), value["goals"], passive=True),
        list_section(t("pain_points"), value["pain_points"], passive=True),
        disclosure(t("tools"), list_section(t("tools"), value["tools"], passive=True),
            fields((("tool_ids", ", ".join(value["tool_ids"])),))),
        disclosure(t("relationships"), relationships_content(value["relationships"]) or h("p", {}, t("none"))),
        disclosure(t("rpf_profile_details"),
            h("p", {"class_": "sl-research-prose"}, value["source_description"]),
            list_section(t("rpf_constraints"), value["constraints"], passive=True),
            list_section(t("rpf_success"), value["success_criteria"], passive=True),
            [h("section", {"class_": "sl-research-profile-section"}, h("h3", {}, label), metadata(value[key]))
                for key, label in details if key in value]),
        disclosure(t("rpx_record_details"), fields((key, value[key]) for key in ("id", "slug", "created_at", "updated_at")),
            h("h3", {}, t("rpf_media_reference")), h("p", {}, t("rpf_media_not_loaded")),
            metadata({key: value[key] for key in ("avatar", "soul", "url") if key in value})))

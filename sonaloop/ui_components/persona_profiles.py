"""Real native Persona profile/list/history results, shared with Product pages."""
from __future__ import annotations

from .library import _kit, collection, note_content
from . import persona_profile_rows as r


def profile(value):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-profile"}, r.profile_content(value)), "ready"


def detail(value):
    h, _, _ = _kit()
    r.record(value)
    return h("article", {"class_": "sl-research-card sl-research-profile"}, r.profile_content(value.get("persona")),
        [r.history(label, value.get(key)) for key, label in (
            ("calendar_events", r.t("rpf_calendar_history")), ("experience_events", r.t("rpf_experience_history")),
            ("daily_summaries", r.t("rpf_daily_history")), ("pain_points", r.t("rpf_pain_history")),
            ("reflections", r.t("rpf_reflection_history")))]), "ready"


def summary(value):
    return r.profile_row(value, passive=True)


def profiles(value):
    r.record(value)
    items = r.records(value.get("items"))
    from .projects_rows import count
    count(value.get("total"))
    if type(value.get("has_more")) is not bool:
        raise ValueError("Expected native Persona page continuation flag")
    if value.get("next_cursor") is not None and type(value["next_cursor"]) is not str:
        raise ValueError("Expected native Persona cursor or null")
    cards = [profile(item)[0] if isinstance(item.get("role"), dict) else summary(item) for item in items]
    return collection(cards, empty=r.t("no_personas"), total=value["total"], has_more=value["has_more"]), "ready" if cards else "empty"


def queried(value):
    r.record(value)
    if type(value.get("substrate_version")) is not int or value["substrate_version"] != 1:
        raise ValueError("Expected native Persona substrate version")
    from .projects_rows import count
    for key in ("total", "limit", "offset"):
        count(value.get(key))
    if value.get("next_offset") is not None:
        count(value["next_offset"])
    cards = [summary(item) for item in r.records(value.get("items"))]
    h, fragment, _ = _kit()
    return fragment(collection(cards, empty=r.t("no_personas"), total=value["total"], has_more=value.get("next_offset") is not None),
        r.disclosure(r.t("rpx_record_details"), r.fields((key, value.get(key)) for key in ("substrate_version", "limit", "offset", "next_offset")))), "ready" if cards else "empty"


def soul(value):
    r.identity(value, "persona_id")
    r.texts(value, ("path", "content"))
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-profile"}, h("h2", {}, r.t("rpf_soul")),
        h("p", {}, r.t("rpf_supplied_document")), note_content({"text": value["content"]}),
        r.disclosure(r.t("rpx_record_details"), r.fields((key, value[key]) for key in ("persona_id", "path")))), "ready" if value["content"] else "empty"

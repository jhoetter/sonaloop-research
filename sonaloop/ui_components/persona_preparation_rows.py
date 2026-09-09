"""Shared Persona readiness bodies; Product decoration is explicitly prepared."""
from __future__ import annotations

import math

from .library import _kit
from .projects_rows import record, texts, strings, count, identity, fields as native_fields, t


def fields(pairs):
    labels = {"next_action": t("rpp_next_action"), "memory_hits": t("rpp_memory_hits"), "cursor": t("rpp_cursor")}
    return native_fields((labels.get(key, key), value) for key, value in pairs)


def rows(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected native preparation rows")
    return value


def nullable(value, keys):
    record(value)
    for key in keys:
        if key not in value or value[key] is not None and type(value[key]) is not str:
            raise ValueError("Expected explicit native text or null: " + key)


def flags(value, keys):
    record(value)
    if any(type(value.get(key)) is not bool for key in keys):
        raise ValueError("Expected native preparation flags")


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Expected finite native measurement")


def counts(value, keys):
    record(value)
    for key in keys:
        count(value.get(key))


def section(title, *body):
    h, _, _ = _kit()
    return h("section", {"class_": "sl-research-preparation-section"}, h("h3", {}, title), *body)


def text_list(title, value):
    h, _, _ = _kit()
    strings(value)
    return section(title, h("ul", {}, [h("li", {}, item) for item in value])
        if value else h("p", {}, t("rpp_no_entries")))


def readiness_record(value):
    identity(value, "persona_id")
    texts(value, ("level", "memory_level", "next_action"))
    if value["level"] not in ("ready", "developing", "thin") or value["memory_level"] not in ("deep", "developing", "thin"):
        raise ValueError("Expected native Persona readiness levels")
    count(value.get("score"))
    if value["score"] > 100:
        raise ValueError("Expected native readiness score out of 100")
    counts(value.get("counts"), ("events", "facts", "evidence", "grounded_claims", "grounding_corpora",
        "daily_summaries", "reflections", "digests", "blocking_anomalies"))
    counts(value.get("dimensions"), ("profile", "grounding", "memory", "continuity", "capabilities"))
    strings(value.get("gaps"))
    if "critic" not in value:
        raise ValueError("Expected explicit native critic or null")
    if value["critic"] is not None:
        flags(value["critic"], ("green",))
        nullable(value["critic"], ("created_at",))
        strings(value["critic"].get("low_dimensions"))


def readiness_labels(value):
    """Original Product chip text and colors, shared with passive text chips."""
    label = t("persona_ready") if value["level"] == "ready" else (
        t("persona_developing") if value["level"] == "developing" else t("persona_thin"))
    counters = value["counts"]
    labels = [(f'{label} · {value["score"]}/100', "var(--green)" if value["level"] == "ready" else "var(--amber)")]
    labels.extend((f'{counters[key]} {label}', None) for key, label in (
        ("events", t("memory_events_short")), ("facts", t("memory_facts_short")),
        ("daily_summaries", t("memory_days_short")), ("grounded_claims", t("memory_grounded_short")),
        ("digests", t("memory_digests_short"))))
    green = (value.get("critic") or {}).get("green")
    labels.append((t("memory_critic_ok") if green else t("memory_critic_missing"),
                   "var(--green)" if green else "var(--muted)"))
    return labels


def readiness_content(value, *, prepared=None, passive=False):
    h, _, _ = _kit()
    if passive:
        readiness_record(value)
    prepared = prepared or {}
    badges = prepared.get("badges")
    if badges is None:
        badges = [h("span", {"class_": "sl-research-preparation-badge"}, label)
                  for label, _ in readiness_labels(value)]
    return h("section", {"class_": "sec sl-persona-readiness" + (" sl-research-readiness" if passive else ""),
        "id": None if passive else "readiness"},
        h("div", {"class_": "sl-persona-readiness__head"}, h("h2", {}, t("persona_readiness")), badges[0]),
        h("p", {"class_": "muted"}, t("persona_memory_warning")) if value["level"] != "ready" else None,
        h("div", {"class_": "sl-persona-readiness__counts" + (" sl-research-preparation-badges" if passive else "")}, badges[1:]))


def capability_labels():
    return (("see", t("cap_rung_see")), ("walk", t("cap_rung_walk")),
            ("drive", t("cap_rung_drive")), ("login", t("cap_rung_login")))


def capability_provenance(value):
    return {"derived": t("cap_derived"), "authored": t("cap_authored"),
            "evidence": t("cap_evidence")}.get(value, value)


def capabilities_content(value, *, prepared=None, passive=False):
    h, fragment, _ = _kit()
    if passive:
        record(value)
        flags(value.get("rungs"), ("see", "walk", "drive", "login"))
        count(value.get("tech_comfort"))
        if not 1 <= value["tech_comfort"] <= 5:
            raise ValueError("Expected native capability comfort 1..5")
        texts(value, ("accessibility", "provenance"))
        strings(value.get("devices"))
    prepared = prepared or {}
    rungs = value.get("rungs") or {}
    badges = prepared.get("badges")
    if badges is None:
        badges = [h("span", {"class_": "sl-research-preparation-badge"}, label, ": ", str(bool(rungs.get(key))).lower())
                  for key, label in capability_labels()]
    chip = prepared.get("comfort", h("span", {"class_": "sl-research-preparation-badge"},
        t("cap_tech_comfort"), ": ", value.get("tech_comfort", "—"), "/5"))
    prov = h("span", {"class_": "muted small"}, capability_provenance(value.get("provenance") or ""))
    return h("div", {"class_": "sec" + (" sl-research-capabilities" if passive else ""), "id": None if passive else "caps"},
        h("h2", {}, t("capabilities_h")),
        h("div", {"class_": "cap-row" + (" sl-research-preparation-badges" if passive else "")}, fragment(*badges), chip, prov),
        h("p", {"class_": "muted small"}, f'{t("cap_devices")}: {", ".join(value.get("devices") or []) or "—"}'),
        h("p", {}, h("strong", {}, t("cap_accessibility")), ": ", value["accessibility"]) if value.get("accessibility") else None,
        h("p", {"class_": "sl-research-meta"}, t("rpp_caps_notice")) if passive else None)

"""Escaped bodies for supplied Persona revisions, voice verdicts and sources."""
from __future__ import annotations

import re

from .library import _kit
from .projects_rows import record, identity, texts, strings, fields, disclosure, t


def records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Expected native Persona record list")
    return value


def nullable(value, *keys):
    for key in keys:
        if key not in value or value[key] is not None and type(value[key]) is not str:
            raise ValueError("Expected native Persona text or null")


def base(value):
    identity(value, "id")
    identity(value, "persona_id")
    texts(value, ("created_at",))


def prose(value):
    h, _, _ = _kit()
    return h("p", {"class_": "sl-research-prose"}, value)


def section(label, *body):
    h, _, _ = _kit()
    return h("section", {}, h("h3", {}, label), *body) if any(body) else None


def text_list(label, values):
    h, _, _ = _kit()
    strings(values)
    return section(label, h("ul", {}, [h("li", {}, item) for item in values])) if values else None


def details(value, extra=()):
    # Native execution grants and unrelated output fields never enter this
    # explicit identity projection. The original MCP value remains untouched.
    return disclosure(t("rpx_record_details"), fields([
        ("id", value["id"]), ("persona_id", value["persona_id"]),
        ("created_at", value["created_at"]), *extra]))


def revision_content(value):
    base(value)
    texts(value, ("effective_on", "rationale"))
    changes = record(value.get("changes"))
    allowed = {f"{key}_{suffix}" for key in ("goals", "constraints", "pains", "tools")
               for suffix in ("add", "remove")} | {"personality", "notes"}
    if changes.keys() - allowed:
        raise ValueError("Unknown native identity revision change")
    refs = records(value.get("refs"))
    from ..web._render import render_ref
    h, fragment, raw = _kit()
    rows = []
    for key, label in (("goals", t("goals")), ("constraints", t("rprec_constraints")),
                       ("pains", t("pain_points")), ("tools", t("tools"))):
        for suffix, operation in (("add", t("rprec_added")), ("remove", t("rprec_removed"))):
            field = f"{key}_{suffix}"
            if field in changes:
                rows.append(text_list(f"{label} · {operation}", changes[field]))
    if "personality" in changes:
        personality = record(changes["personality"])
        if personality.keys() - {"working_style", "communication_style", "risk_tolerance", "character_notes"}:
            raise ValueError("Unknown native identity revision personality field")
        pairs = []
        for key, label in (("working_style", t("f_working_style")),
                           ("communication_style", t("f_communication_style")),
                           ("risk_tolerance", t("f_risk_tolerance")),
                           ("character_notes", t("rprec_character_notes"))):
            if key in personality:
                texts(personality, (key,))
                pairs.append((label, personality[key]))
        if pairs:
            rows.append(section(t("rprec_personality"), fields(pairs)))
    if "notes" in changes:
        texts(changes, ("notes",))
        if changes["notes"]:
            rows.append(section(t("rprec_notes"), prose(changes["notes"])))
    ref_rows = []
    for ref in refs:
        identity(ref, "id")
        texts(ref, ("kind",))
        if ref["kind"] not in {"fact", "event", "digest", "evidence"}:
            raise ValueError("Unknown native Persona revision reference kind")
        ref_rows.append(h("li", {}, raw(render_ref(ref, passive=True))))
    return h("div", {"class_": "sl-research-record-content"},
        fields(((t("rprec_effective_on"), value["effective_on"]),)),
        section(t("rprec_rationale"), prose(value["rationale"])),
        fragment(rows) if any(rows) else prose(t("rprec_no_changes")),
        section(t("rprec_refs"), h("ul", {}, ref_rows)) if ref_rows else None,
        details(value))


def voice_content(value):
    base(value)
    texts(value, ("kind", "text_sha256"))
    if value["kind"] != "persona_voice_check" or type(value.get("green")) is not bool:
        raise ValueError("Expected recorded native Persona voice verdict")
    if not re.fullmatch(r"[a-f0-9]{64}", value["text_sha256"]):
        raise ValueError("Expected native candidate text digest")
    nullable(value, "rewrite", "context_snapshot_id")
    scores = record(value.get("scores"))
    dimensions = (("authenticity", t("rprec_authenticity")), ("register_match", t("rprec_register_match")),
                  ("knowledge_grounding", t("rprec_knowledge_grounding")),
                  ("attribution_separation", t("rprec_attribution_separation")))
    for key, _ in dimensions:
        if type(scores.get(key)) is not int or not 0 <= scores[key] <= 5:
            raise ValueError("Expected native voice dimension score 0..5")
    h, _, _ = _kit()
    issues = []
    for issue in records(value.get("issues")):
        texts(issue, ("kind", "detail"))
        issues.append(h("li", {}, h("strong", {}, issue["kind"]), prose(issue["detail"])))
    signals = []
    for signal in records(value.get("deterministic_signals")):
        texts(signal, ("kind", "phrase"))
        signals.append(h("li", {}, h("strong", {}, signal["kind"]), ": ", signal["phrase"]))
    return h("div", {"class_": "sl-research-record-content"},
        fields(((t("rprec_recorded_green"), value["green"]),)),
        fields([(label, f"{scores[key]} / 5") for key, label in dimensions]),
        section(t("rprec_issues"), h("ul", {}, issues)) if issues else prose(t("rprec_no_issues")),
        section(t("rprec_rewrite"), prose(value["rewrite"])) if value["rewrite"] else None,
        section(t("rprec_signals"), h("ul", {}, signals), prose(t("rprec_signals_notice"))) if signals else None,
        prose(t("rprec_voice_notice")),
        details(value, (("text_sha256", value["text_sha256"]),
                        ("context_snapshot_id", value["context_snapshot_id"]))))


def evidence_content(value):
    base(value)
    texts(value, ("source_type", "content_or_path"))
    nullable(value, "notes")
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-record-content"},
        fields(((t("rprec_source_type"), value["source_type"]),)), prose(value["content_or_path"]),
        section(t("rprec_notes"), prose(value["notes"])) if value["notes"] else None,
        prose(t("rprec_source_notice")), details(value))

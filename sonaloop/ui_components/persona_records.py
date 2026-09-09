"""Pure native result projections shared by the Product Persona records page."""
from __future__ import annotations

from .library import _kit, collection
from .persona_record_rows import records, revision_content, voice_content, evidence_content, t


def _card(label, body):
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card sl-research-persona-record"}, h("h2", {}, label), body)


def revision(value):
    return _card(t("rprec_revision"), revision_content(value)), "ready"


def revisions(value):
    values = records(value)
    return collection([revision(item)[0] for item in values], empty=t("rprec_no_revisions")), "ready" if values else "empty"


def voice_check(value):
    return _card(t("rprec_voice_check"), voice_content(value)), "ready"


def evidence(value):
    return _card(t("rprec_evidence"), evidence_content(value)), "ready"

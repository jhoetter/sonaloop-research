"""Read-only inspection of stored Persona revisions, voice verdicts and sources."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403
from ...ui_components import persona_records as records
from ...ui_components.library import collection


def _body(render, value):
    try:
        return render(value)[0]
    except (ValueError, TypeError, KeyError):
        return h("p", {"class_": "muted"}, t("rprec_unavailable"))


def register_persona_records(app):
    @app.get("/personas/{persona_id}/records", response_class=HTMLResponse)
    def persona_records(persona_id: str):
        store = Store()
        persona = store.get_persona_for_active_workspace(persona_id)
        if not persona:
            return HTMLResponse(_layout(t("not_found"), h("p", {}, t("profile_not_found")),
                                        store, active="personas"), status_code=404)
        pid = persona["id"]
        revisions = store.list_persona_revisions(pid)
        voices = [item for item in store.list_eval_reports(pid) if item.get("kind") == "persona_voice_check"]
        sources = store.list_evidence(pid)
        body = h("div", {"class_": "sl-syn-main"}, h("h1", {}, t("rprec_records")),
            h("h2", {}, t("rprec_revisions")),
            collection([_body(records.revision, item) for item in revisions], empty=t("rprec_no_revisions")),
            h("h2", {}, t("rprec_voice_checks")),
            collection([_body(records.voice_check, item) for item in voices], empty=t("rprec_no_voice")),
            h("h2", {}, t("rprec_sources")),
            collection([_body(records.evidence, item) for item in sources], empty=t("rprec_no_sources")))
        return _layout(t("rprec_records"), body, store, active="personas",
            crumbs=[(t("personas"), "/personas"), (persona["display_name"], f"/personas/{pid}"),
                    (t("rprec_records"), None)])

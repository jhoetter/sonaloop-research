"""Explicit Product inspection of existing native profile/history/document reads."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403
from ...ui_components import persona_profiles


def register_persona_profiles(app):
    def render(persona_id, *, document=False):
        store = Store()
        try:
            # Existing native getters may repair their SOUL/runtime fields.
            # No new authoring, media resolution or surface operation is admitted.
            value = (services.get_persona_soul(persona_id, store=store) if document
                     else services.get_persona(persona_id, store=store))
        except KeyError:
            return HTMLResponse(_layout(t("not_found"), h("p", {}, t("not_found")), store, active="personas"), status_code=404)
        pid = value["persona_id"] if document else value["persona"]["id"]
        label = t("rpf_soul") if document else t("rpf_profile_history")
        try:
            body = (persona_profiles.soul if document else persona_profiles.detail)(value)[0]
        except (ValueError, TypeError, KeyError):
            body = h("p", {}, t("rpf_unavailable"))
        return _layout(label, h("div", {"class_": "sl-syn-main"}, h("h1", {}, label), body),
            store, active="personas", crumbs=[(t("personas"), "/personas"), (pid, f"/personas/{pid}"), (label, None)])

    @app.get("/personas/{persona_id}/profile", response_class=HTMLResponse)
    def native_profile(persona_id: str):
        return render(persona_id)

    @app.get("/personas/{persona_id}/soul", response_class=HTMLResponse)
    def native_soul(persona_id: str):
        return render(persona_id, document=True)

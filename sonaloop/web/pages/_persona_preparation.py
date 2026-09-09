"""Read-only Product consumers and prepared decoration for Persona preparation."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403
from ... import artifacts
from ...ui_components import persona_preparation as preparation
from ...ui_components import persona_preparation_rows as preparation_rows


def readiness_html(value):
    badges = [raw(_label(label, color)) if color else _label(label)
              for label, color in preparation_rows.readiness_labels(value)]
    return preparation.readiness_content(value, prepared={"badges": badges})


def capabilities_html(value):
    rungs = value.get("rungs") or {}
    badges = [raw(_label(label, "var(--green)" if rungs.get(key) else "var(--muted)",
                        "soft" if rungs.get(key) else "outline", title=f"rungs.{key}"))
              for key, label in preparation_rows.capability_labels()]
    meta = artifacts.tech_comfort_meta(value.get("tech_comfort"))
    chip = raw(_label(f'{t("cap_tech_comfort")}: {t(meta["label_key"])} · {value.get("tech_comfort", "—")}/5',
                      meta["color"], title=meta["hint"]))
    return preparation.capabilities_content(value, prepared={"badges": badges, "comfort": chip})


def _body(render, value):
    try:
        return render(value)[0]
    except (ValueError, TypeError, KeyError):
        return h("p", {"class_": "muted"}, t("rpp_unavailable"))


def _missing(store):
    return _layout(t("not_found"), _empty_state(t("profile_not_found"), t("persona_runtime_cleared"),
                   icon="personas"), store, active="personas")


def _page(store, persona, label, body):
    return _layout(label, h("div", {"class_": "sl-syn-main"}, body), store, active="personas",
        crumbs=[(t("personas"), "/personas"), (persona["display_name"], f'/personas/{persona["id"]}'),
                (t("rpp_preparation"), f'/personas/{persona["id"]}/preparation'), (label, None)])


def register_persona_preparation(app):
    """No route prepares a context, starts a build, or executes a returned step."""
    @app.get("/personas/{persona_id}/preparation", response_class=HTMLResponse)
    def preparation_history(persona_id: str):
        store = Store()
        persona = store.get_persona(persona_id)
        if not persona:
            return _missing(store)
        pid = persona["id"]
        status = services.persona_readiness(pid, store=store)
        builds = services.list_persona_builds(pid, store=store)
        snapshots = services.list_persona_context_snapshots(pid, store=store)
        build_links = [h("li", {}, h("a", {"href": f'/personas/{pid}/preparation/builds/{row["build_id"]}'},
                                      row["build_id"])) for row in builds]
        context_links = [h("li", {}, h("a", {"href": f'/personas/{pid}/preparation/contexts/{row["id"]}'},
                                        row["id"])) for row in snapshots]
        return _page(store, persona, t("rpp_preparation"), fragment(_body(preparation.readiness, status),
            h("details", {}, h("summary", {}, t("rpp_builds")), _body(preparation.builds, builds), h("ul", {}, build_links)),
            h("details", {}, h("summary", {}, t("rpp_snapshots")), _body(preparation.snapshots, snapshots), h("ul", {}, context_links))))

    @app.get("/personas/{persona_id}/preparation/contexts/{snapshot_id}", response_class=HTMLResponse)
    def preparation_context(persona_id: str, snapshot_id: str):
        store = Store()
        persona = store.get_persona(persona_id)
        if not persona:
            return _missing(store)
        try:
            value = services.get_persona_context_snapshot(snapshot_id, store=store)
        except KeyError:
            return _missing(store)
        if value.get("persona_id") != persona["id"]:
            return _missing(store)
        return _page(store, persona, t("rpp_snapshot"), _body(preparation.snapshot, value))

    @app.get("/personas/{persona_id}/preparation/builds/{build_id}", response_class=HTMLResponse)
    def preparation_build(persona_id: str, build_id: str):
        store = Store()
        persona = store.get_persona(persona_id)
        if not persona:
            return _missing(store)
        try:
            value = services.get_persona_build(build_id, store=store)
        except KeyError:
            return _missing(store)
        if value.get("persona_id") != persona["id"]:
            return _missing(store)
        return _page(store, persona, t("rpp_build"), _body(preparation.build, value))

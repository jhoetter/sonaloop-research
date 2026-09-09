"""Shared prototype detail body and prepared properties; no app/file/process access."""
from __future__ import annotations

from .library import _kit, collection, note_card


def prototype_properties(value, *, project=None, form_rows=(), fidelity=None,
                         session_count=None, grounded=None, created=None):
    """Product adapters prepare names, links and counts; absent counts stay absent."""
    from ..web._i18n import t
    rows = [("projects", t("project"), project)] if project is not None else []
    rows.extend(form_rows)
    if fidelity is not None:
        rows.append(("square", t("fidelity"), fidelity))
    if session_count is not None:
        rows.append(("personas", t("sessions"), str(session_count)))
    if grounded is not None:
        rows.append(("check", t("grounding_h"), grounded))
    rows.append(("dot", t("created"), created if created is not None else value.get("created_at", "")))
    return rows


def prototype_content(value, *, preview, replays=None, sessions=None, session_count=None):
    from ..web._i18n import t
    h, fragment, _ = _kit()
    return fragment(
        preview,
        h("section", {"class_": "sec sl-research-prototype-notes", "id": "sec-notes"},
          h("h2", {}, t("notes_h")), h("div", {"class_": "sl-research-prose"}, value["notes"]))
        if value.get("notes") else None,
        replays,
        h("div", {"class_": "sec", "id": "sec-sessions", "style": "margin-top:22px"},
          h("h2", {}, f'{t("proto_sessions_h")} ({session_count})'),
          h("div", {"style": "margin-top:8px"}, sessions)) if sessions is not None else None,
    )


def _record(value):
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str)
            for key in ("id", "slug", "name", "version", "kind", "path", "entry", "run", "notes", "created_at")):
        raise ValueError("Expected native prototype identity and artifact metadata")
    if not value["id"] or not value["name"]:
        raise ValueError("Expected actual prototype identity")
    for key in ("type", "fidelity", "url"):
        if key in value and not isinstance(value[key], str):
            raise ValueError("Expected native prototype text")
    if value.get("project_id") is not None and not isinstance(value["project_id"], str):
        raise ValueError("Expected native project identity")
    if "running" in value and type(value["running"]) is not bool:
        raise ValueError("Expected actual native local-process state")
    if "tags" in value and (not isinstance(value["tags"], list)
                            or any(not isinstance(tag, str) for tag in value["tags"])):
        raise ValueError("Expected native artifact tags")
    return value


def _fields(rows):
    h, fragment, _ = _kit()
    return h("dl", {"class_": "sl-research-fields"}, fragment(*(
        fragment(h("dt", {}, label), h("dd", {}, value)) for _, label, value in rows
        if value not in (None, ""))))


def _location(value):
    from ..web._i18n import t
    h, fragment, _ = _kit()
    rows = [("", t("rp_delivery"), t("rp_remote") if value["run"] == "remote" else value["run"])]
    if value.get("url"):
        rows.append(("", t("rp_address"), value["url"]))
    else:
        rows.extend(("", label, value[key]) for label, key in ((t("rp_path"), "path"), (t("rp_entry"), "entry")))
    if "running" in value:
        rows.append(("", t("rp_local_process"), t("rp_running") if value["running"] else t("rp_not_running")))
    return fragment(_fields(rows), h("p", {"class_": "muted small"}, t("rp_no_preview")))


def prototype(value):
    from ..web._i18n import t
    from ..web._primitive_taxonomy import prototype_fidelity_value
    h, _, _ = _kit()
    value = _record(value)
    # Native free type/tags remain literal. Taxonomy labels would require runtime data.
    form_rows = [("", t("form_h"), value.get("type") or value["kind"])]
    if value.get("tags"):
        form_rows.append(("", t("rp_tags"), " · ".join(value["tags"])))
    properties = prototype_properties(value, project=value.get("project_id"), form_rows=form_rows,
                                      fidelity=prototype_fidelity_value(value))
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("prototype_kind")),
               h("h2", {}, value["name"]), h("p", {"class_": "muted"}, value["version"])),
             _fields(properties), prototype_content(value, preview=_location(value))), "ready"


def registered_remote(value):
    h, fragment, _ = _kit()
    if not isinstance(value, dict):
        raise ValueError("Expected native remote registration envelope")
    card, state = prototype(value.get("prototype"))
    paired = value.get("note")
    if paired is not None and (not isinstance(paired, dict) or not isinstance(paired.get("id"), str)
                               or not isinstance(paired.get("text"), str)):
        raise ValueError("Expected actual paired native note")
    return h("div", {"class_": "sl-research-collection"}, fragment(card, note_card(paired) if paired else None)), state


def prototypes(value):
    from ..web._i18n import t
    if not isinstance(value, list):
        raise ValueError("Expected native prototype list")
    cards = [prototype(item)[0] for item in value]
    return collection(cards, empty=t("rp_empty")), "ready" if cards else "empty"


def running(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("prototype_id"), str)
            or not value["prototype_id"] or not isinstance(value.get("url"), str) or not value["url"]):
        raise ValueError("Expected actual native prototype run result")
    remote = value.get("remote") is True
    if remote:
        if value.get("pid") is not None or value.get("running") is not False:
            raise ValueError("Remote address lookup did not start a local process")
    elif type(value.get("pid")) is not int or value["pid"] <= 0:
        raise ValueError("Expected actual native local process ID")
    if "already_running" in value and type(value["already_running"]) is not bool:
        raise ValueError("Expected native reuse flag")
    title = t("rp_remote_address") if remote else t("rp_reused") if value.get("already_running") else t("rp_started")
    rows = [("", t("prototype_kind"), value["prototype_id"]), ("", t("rp_address"), value["url"])]
    if not remote:
        rows.append(("", t("rp_process_id"), str(value["pid"])))
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, title), _fields(rows),
             h("p", {"class_": "muted small"}, t("rp_no_preview"))), "ready"


def stopped(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if not isinstance(value, dict) or type(value.get("stopped")) is not bool or (
            value["stopped"] and (not isinstance(value.get("prototype_id"), str) or not value["prototype_id"])):
        raise ValueError("Expected native prototype stop result")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("prototypes_h")),
             h("p", {}, t("rp_stopped") if value["stopped"] else t("rp_nothing_stopped")),
             h("p", {"class_": "muted small"}, value["prototype_id"]) if value["stopped"] else None), "ready"


def removed(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if not isinstance(value, dict) or type(value.get("deleted")) is not int or value["deleted"] < 0:
        raise ValueError("Expected native prototype deletion count")
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, t("prototypes_h")),
             h("p", {}, t("rp_deleted", n=value["deleted"])),
             h("p", {"class_": "muted small"}, t("rp_files_retained"))), "ready"

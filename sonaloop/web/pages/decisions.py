"""Decision records: the real /decisions/{id} detail page (UX U7, spec/ux-contract.md §8.2),
the cross-project list page + the shared row renderers.

A decision ALSO lives on its project page — an outline row in the phase whose gate it decided
(UX P2, §3.4) — and the detail page keeps that anchor as the secondary "view in project" link.
This module owns the decision CARD shared by the global /decisions index and the decision
detail page: evidence chips via render_ref, rejected alternatives with why-not notes,
supersede links in both directions. READ-ONLY like every page. The card's `.hyp` CSS is
co-located with its primary owner in hypotheses.py; the status pills live in web/_presence
(shared with the outline chips). /decisions and /decisions/{id} have distinct path shapes, so
the list route never shadows the detail route."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .. import ui
from .._presence import decision_status_pill
from .._render import render_ref
from ...ui_components.bets import decision_reads


def _decision_reads(d: dict, store, by_id: dict, *, clamp_at: int = ui.CLAMP_THRESHOLD,
                    dec_href=lambda oid: f"#dec-{oid}"):
    """Resolve product references before entering the shared pure renderer."""
    return decision_reads(d, based=[raw(render_ref(ref, store, show_role=False)) for ref in d.get("based_on") or []],
                          rejected=[raw(render_ref(ref, store, show_role=False)) for ref in d.get("rejected") or []],
                          by_id=by_id, clamp_at=clamp_at, dec_href=dec_href)


def _decision_row(d: dict, store, by_id: dict, *, title_href: str | None = None,
                  project_title: str | None = None) -> str:
    """One decision: status pill + title, the decision text, evidence chips, rejected
    alternatives, supersede links. On the project page the card is the anchor target (plain bold
    title); on the cross-project list `title_href` links the title into that anchor and
    `project_title` names where the decision lives."""
    status = d.get("status", "proposed")
    title = h("b", {}, d.get("title", ""))
    if title_href:
        title = h("a", {"href": title_href}, title)
    proj = (h("span", {"class_": "muted small", "style": "margin-left:8px"}, project_title)
            if project_title else None)
    body, based, rejected, links = _decision_reads(d, store, by_id)
    return h("div", {"class_": "hyp", "id": f'dec-{d["id"]}'},
             h("div", {}, raw(decision_status_pill(status)), " ", title, proj),
             body,
             based, rejected, links)


def register_decisions(app) -> None:
    @app.get("/decisions", response_class=HTMLResponse)
    def decisions_list(project: str = Query(default=""), status: str = Query(default=""),
                       subtype: str = Query(default=""), trace: str = Query(default=""),
                       q: str = Query(default="")) -> str:
        """Every decision record across all projects — the Library's Decisions tab
        (ux-contract §3.5): one status-pilled row per record, the audit trail of what
        the research changed; the full ADR card lives on the detail page (full page or
        slide-over). Filterable by project + status (U10, the shared FilterBar grammar)."""
        from .library import library_filters, library_page
        return library_page("decisions", flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/decisions", q=q)

    @app.get("/decisions/{decision_id}", response_class=HTMLResponse)
    def decision_detail(decision_id: str) -> str:
        """A decision's REAL detail page (UX U7 — every kind, one scaffold; supersedes the old
        redirect into the project anchor, which stays reachable as the secondary 'view in
        project' link): the full-width ADR record on the shared anatomy — kind eyebrow + status
        pill header, the decision body at the section dose, resolved based_on/rejected chips and
        supersede links to sibling DETAIL pages — with the properties rail (project, evidence
        count, dates)."""
        store = Store()
        try:
            d = services.get_decision(decision_id, store=store)
        except KeyError:
            return _layout(t("not_found"),
                           _empty_state(t("decisions_h"), t("runtime_maybe_cleared"), icon="flag"),
                           store, active="library")
        proj = (store.get_research_project(d.get("project_id")) if d.get("project_id") else None)
        by_id = {x["id"]: x for x in store.list_decisions(d.get("project_id"))}
        body_clamp, _based, rejected, links = _decision_reads(
            d, store, by_id, clamp_at=ui.SECTION_CLAMP, dec_href=lambda oid: f"/decisions/{oid}")
        anchor = (f'/jobs/{d["project_id"]}#dec-{d["id"]}' if d.get("project_id") else "")
        body = fragment(
            h("div", {"class_": "sec", "id": "sec-decision"}, body_clamp, rejected, links))
        # Project-rooted crumb (§8.2 — the council pattern); kind root only for orphans.
        crumbs = ([(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}')]
                  if proj else [(t("decisions_h"), "/decisions")])
        crumbs.append((d.get("title", ""), None))
        # The rail's project link lands ON the deciding row (the #dec- anchor) — this replaces
        # the old "View in project" meta-line link, which no other kind carried (round 2, §8.2).
        proj_link = (h("a", {"href": anchor or f'/jobs/{proj["id"]}'}, proj["title"]) if proj else "")
        prop_rows = [
            ("projects", t("project"), proj_link),
            *detail_form_rows("decision", d),
            ("link", t("rel_based_on"), raw(_label(t("chip_evidence_n", n=len(d.get("based_on") or []))))),
            ("dot", t("created"), ui.local_date(d.get("created_at") or "")),
        ]
        return detail_page(
            store, title=d.get("title", ""), crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            icon="flag", kind=t("decision_kind"),
            pills=[decision_status_pill(d.get("status", "proposed"))],
            hid="sec-head", body=body, prop_rows=prop_rows,
            rel_study_id=f"decision:{d['id']}", rel_proj_id=(proj["id"] if proj else None),
            rail_sections=[("sec-decision", t("decision_kind"))],
            star=("decision", d["id"], d.get("title", "")[:60], f'/decisions/{d["id"]}'))

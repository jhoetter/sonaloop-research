"""Read-only Product consumers of cohort reports, selection history and coverage."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403
from ...ui_components import cohort, cohort_preflight, cohort_rows
from ...ui_components.library import collection


def _body(render, value):
    try:
        return render(value)[0]
    except (ValueError, TypeError, KeyError):
        return h("p", {"class_": "muted"}, t("rcg_unavailable"))


def register_cohort_results(app):
    @app.get("/cohorts", response_class=HTMLResponse)
    def cohort_reports():
        store = Store()
        reports = [row for row in store.list_eval_reports()
                   if row.get("kind") in ("cohort_diversity", "cohort_critic")]
        cards = [_body(cohort.diversity if row["kind"] == "cohort_diversity" else cohort.critic, row)
                 for row in reports]
        # The diversity tool is a writer. Its na result is not persisted; this
        # history never evaluates a new report to manufacture an empty entry.
        return _layout(t("rcg_cohorts"), h("div", {"class_": "sl-syn-main"},
            h("h1", {}, t("rcg_cohorts")),
            _body(cohort.depth, services.cohort_memory_depth(store=store)),
            h("h2", {}, t("rcg_reports")), collection(cards, empty=t("rcg_no_reports"))),
            store, active="personas", crumbs=[(t("personas"), "/personas"), (t("rcg_cohorts"), None)])

    @app.get("/jobs/{project_id}/cohort", response_class=HTMLResponse)
    def project_cohort(project_id: str, version_id: str | None = None):
        store = Store()
        project = store.get_research_project(project_id)
        if not project:
            return _layout(t("not_found"), h("p", {}, t("not_found")), store, active="projects")
        pid = project["id"]
        members = project.get("persona_ids") or []
        revisions = project.get("cohort_revisions") or []
        try:
            preflight = services.get_cohort_preflight(pid, version_id, store=store)
        except KeyError:
            preflight = None
        # Do not call cohort_memory_depth([]): native [] means the whole
        # workspace. An empty project panel has no project-specific depth DTO.
        memory_depth = _body(cohort.depth, services.cohort_memory_depth(members, store=store)) if members else None
        coverage = services.assess_coverage(pid, job=project.get("job"), store=store)
        links = [h("li", {}, h("a", {"href": f'/jobs/{pid}/cohort?version_id={row["id"]}'},
                                   f'{row["version"]} · {row["status"]}'))
                 for row in (preflight or {}).get("history", [])]
        return _layout(t("rcg_cohorts"), h("div", {"class_": "sl-syn-main"},
            h("h1", {}, t("rcg_cohorts")),
            cohort.selection_content(members, ""),
            cohort_rows.disclosure(t("rcg_selection"), cohort_rows.revisions(revisions)),
            memory_depth, _body(cohort.coverage, coverage),
            _body(cohort_preflight.preflight, preflight) if preflight is not None else h("p", {}, t("rcg_no_preflight")),
            h("ul", {}, links)), store, active="projects",
            crumbs=[(t("projects"), "/jobs"), (project.get("title") or pid, f"/jobs/{pid}"), (t("rcg_cohorts"), None)])

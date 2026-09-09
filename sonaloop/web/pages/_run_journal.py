"""Read-only project-owned Run journal inspection, using the public pure body."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403
from ...ui_components import run_journal


def register_run_journal(app):
    @app.get("/jobs/{project_id}/runs/{run_id}", response_class=HTMLResponse)
    def project_run_journal(project_id: str, run_id: str):
        store = Store()

        def missing():
            return HTMLResponse(_layout(t("not_found"), h("p", {}, t("not_found")), store,
                                        active="projects"), status_code=404)

        project = store.get_research_project_for_active_workspace(project_id)
        if not project:
            return missing()
        # Verify both scopes before calling the native getter or disclosing a row.
        run = store.get_run(run_id)
        if not run or run.get("project_id") != project["id"]:
            return missing()
        value = services.run_journal(run_id, store=store)
        if value.get("project_id") != project["id"] or value.get("run_id") != run_id:
            return missing()
        try:
            body = run_journal.journal(value)[0]
        except (ValueError, TypeError, KeyError):
            body = h("p", {"class_": "muted"}, t("rrun_unavailable"))
        return _layout(t("rrun_journal"), h("div", {"class_": "sl-syn-main"},
            h("h1", {}, project.get("title", "")), body), store, active="projects",
            crumbs=[(t("projects"), "/jobs"), (project.get("title", project_id), f"/jobs/{project_id}"),
                    (t("rrun_journal"), None)])

"""Explicit read-only catalog status and recommendation inspection."""
from __future__ import annotations

from fastapi import Query

from ._ctx import *  # noqa: F401,F403
from ...services._catalog import CatalogFetchError
from ...ui_components import persona_catalog


def _page(store, label, read, render):
    try:
        value = read()
    except (CatalogFetchError, ValueError, KeyError):
        return HTMLResponse(_layout(label, h("p", {}, t("rcat_unavailable")), store,
                                    active="personas"), status_code=503)
    try:
        body = render(value)[0]
    except (ValueError, TypeError, KeyError):
        body = h("p", {}, t("rcat_unavailable"))
    return _layout(label, h("div", {"class_": "sl-syn-main"}, body), store, active="personas",
        crumbs=[(t("personas"), "/personas"), (t("catalog_h"), "/personas/catalog"), (label, None)])


def register_catalog_results(app):
    @app.get("/personas/catalog/status", response_class=HTMLResponse)
    def catalog_status(persona_slugs: list[str] | None = Query(default=None), ref: str = "main"):
        store = Store()
        return _page(store, t("rcat_status"),
            lambda: services.catalog_status(persona_slugs, ref, store=store), persona_catalog.status)

    @app.get("/personas/catalog/recommendations", response_class=HTMLResponse)
    def catalog_recommendations(keyword: list[str] | None = Query(default=None),
        n: int = Query(default=5, ge=1, le=100), min_coverage: int | None = Query(default=None, ge=1, le=100)):
        spec = {"keywords": keyword or [], "n": n}
        if min_coverage is not None:
            spec["min_coverage"] = min_coverage
        return _page(Store(), t("rcat_recommendations"), lambda: services.catalog_recommend(spec),
                     persona_catalog.recommendations)

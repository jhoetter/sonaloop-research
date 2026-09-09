"""Assets as a first-class surface (UX U8, spec/ux-contract.md §8.3): which input files the
project RECEIVED (evidence in — possibly across many MCP messages over time) and which documents
the software GENERATED (deliverables out — possibly several versions, the supersede chain).

Three routes on the shared anatomy, zero new presentation:
  - /assets             — the Library's Assets tab (cross-project rows, §3.5).
  - /assets/{id}        — the asset detail page (U7 scaffold: preview / file card, provenance
                          block, properties rail). GLOBAL id resolution across projects, like
                          every other kind's detail route (get_asset is project-scoped, so the
                          lookup scans the project records — assets ride the project JSON blob).
  - /jobs/{id}     — the project outline includes the project's assets in context.

The shared pill/size/source-chip/preview renderers live in web/_presence (the house pattern);
rows are ui.primitive_row, so the slide-over (§8.1) works from every surface."""
from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import Response

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .. import ui
from .._presence import (
    asset_direction, asset_direction_pill, asset_file_card, asset_kind_pill,
    asset_preview_html, asset_source_chip,
)


def find_asset(store, asset_id: str) -> tuple[dict | None, dict | None]:
    """(project, asset) for an asset id (or filename) resolved ACROSS projects — the global
    /assets/{id} route's lookup. Returns (None, None) when nothing matches."""
    for proj in store.list_research_projects():
        for a in proj.get("assets") or []:
            if a.get("id") == asset_id or a.get("filename") == asset_id:
                return proj, a
    return None, None


def _provenance_section(a: dict, store) -> str:
    """The PROVENANCE block (§8.3): received/generated timestamp · source resolved as a chip ·
    the supersede chain when recorded · notes — the sl-props row contract, so provenance reads
    like structure, not prose. The Generated/Received verb already states the direction; the
    header pill is the page's ONE direction encoding (round-4 J2: no repeats)."""
    when = ui.local_ts(a.get("created_at") or "")
    chain = a.get("supersedes") or []
    chain_html = fragment(*(
        h("div", {"class_": "muted small"},
          s.get("filename", "") or s.get("id", ""), " · ",
          ui.local_ts(s.get("created_at") or ""))
        for s in chain)) if chain else None
    from ...ui_components.assets import provenance_content
    return provenance_content(a, source=raw(asset_source_chip(a, store)),
                              when=when, chain=chain_html)



def register_assets(app) -> None:
    @app.get("/assets", response_class=HTMLResponse)
    def assets_list(project: str = Query(default=""), status: str = Query(default=""),
                    direction: str = Query(default=""), subtype: str = Query(default=""),
                    trace: str = Query(default=""), q: str = Query(default="")) -> str:
        # The Library's Assets tab under the canonical URL (ux-contract §3.5), with the
        # shared FilterBar (U10): project + status + direction, same URL grammar.
        from .library import library_filters, library_page
        return library_page("assets", flt=library_filters(project, status, direction, subtype, trace),
                            base="/assets", q=q)

    @app.get("/assets/{asset_id}", response_class=HTMLResponse)
    def asset_detail(asset_id: str) -> str:
        """An asset's REAL detail page (UX U8 — the U7 anatomy): ASSET eyebrow + kind/direction
        pills, image preview / file card with download, the text excerpt for documents, the
        PROVENANCE block (when received/generated, source chip, supersede chain, notes), and
        the properties rail (project · created).

        Round-4 J2 (ux-audit): the page reads ONCE top to bottom — filename, size and
        mimetype live only on the file card (no H1 sub line), the rail carries no
        Type/Direction/Size rows (the header pills + the card state them), and the card
        drops its extension-badge stage when the real first-page preview leads the page."""
        store = Store()
        proj, a = find_asset(store, asset_id)
        if a is None:
            return _layout(t("not_found"),
                           _empty_state(t("assets_h"), t("runtime_maybe_cleared"), icon="clipboard"),
                           store, active="library")
        title = a.get("title") or a.get("filename", "")
        excerpt = (a.get("text_excerpt") or "").strip()
        preview = asset_preview_html(a)
        from ...ui_components.assets import asset_content
        body = asset_content(a, preview=raw(preview),
                             file_card=raw(asset_file_card(a, stage=not preview)),
                             provenance=raw(_provenance_section(a, store)))
        proj_link = h("a", {"href": f'/jobs/{proj["id"]}'}, proj["title"])
        prop_rows = [
            ("projects", t("project"), proj_link),
            *detail_form_rows("asset", a),
            ("dot", t("created"), ui.local_date(a.get("created_at") or "")),
        ]
        return detail_page(
            store, title=title, active="projects",   # G5: an asset always lives on a project
            # Project-rooted crumb (§8.2 — the council pattern; an asset always has a project).
            crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'),
                    (title, None)],
            icon="file", kind=t("asset_kind"),
            pills=[asset_kind_pill(a), asset_direction_pill(a)],
            body=body, prop_rows=prop_rows,
            rel_study_id=f"asset:{a['id']}", rel_proj_id=proj["id"],
            rail_sections=([("sec-excerpt", t("asset_excerpt_h"))] if excerpt else [])
                          + [("sec-provenance", t("provenance_h"))],
            star=("asset", a["id"], title[:60], f'/assets/{a["id"]}'))

    def _asset_binary(asset_id: str, *, preview: bool, thumbnail: bool = False) -> Response:
        """Serve one opaque asset id from the ACTIVE workspace.

        Cloud principals may belong to several workspaces, but each request is
        bound to exactly one active RLS scope. Files do not carry RLS themselves:
        narrow the database lookup and filesystem partition again before resolving
        either. The outer Cloud principal middleware supplies authentication and
        validates that the active id is one of the memberships.
        """
        from ... import config

        tenant_token = None
        if config.postgres_row_tenancy_enabled():
            scope = config.request_tenant_scope()
            if scope is None or not scope[1] or scope[1] not in scope[0]:
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
            active_id = scope[1]
            tenant_token = config.set_request_tenant_scope([active_id], active_id)

        store = Store()
        try:
            project, asset = find_asset(store, asset_id)
            # Opaque browser routes are id-addressed.  `find_asset` also accepts a
            # filename for the human detail page, but thumbnails never widen that
            # compatibility seam into a binary capability.
            if (project is None or asset is None
                    or (thumbnail and str(asset.get("id") or "") != asset_id)):
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
            try:
                if thumbnail and asset.get("kind") in ("image", "screenshot"):
                    data, record = services.get_asset_content(
                        project["id"], asset["id"], store=store)
                    filename = str(record.get("filename") or record["id"])
                elif thumbnail and asset.get("preview_url"):
                    data, record = services.get_asset_preview_content(
                        project["id"], asset["id"], store=store)
                    filename = f'{asset.get("filename") or asset["id"]}.preview.png'
                elif thumbnail:
                    return Response(status_code=404, headers={"Cache-Control": "no-store"})
                elif preview:
                    data, record = services.get_asset_preview_content(
                        project["id"], asset["id"], store=store)
                    media_type = "image/png"
                    filename = f'{asset.get("filename") or asset["id"]}.preview.png'
                else:
                    data, record = services.get_asset_content(
                        project["id"], asset["id"], store=store)
                    media_type = str(record.get("media_type") or "application/octet-stream")
                    filename = str(record.get("filename") or record["id"])
                if thumbnail:
                    from .._thumbnails import ASSET_THUMBNAIL_PX, thumbnail_webp
                    data = thumbnail_webp(
                        data, variant="asset", max_side=ASSET_THUMBNAIL_PX)
                    media_type = "image/webp"
            except (FileNotFoundError, KeyError, ValueError):
                # Do not reveal whether a record, preview or backing file was the
                # missing piece across a tenant boundary.
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
        finally:
            store.close()
            if tenant_token is not None:
                config.reset_request_tenant_scope(tenant_token)

        # Only inert raster formats render inline.  User-controlled SVG/HTML and
        # arbitrary files download instead of becoming same-origin active content.
        if thumbnail:
            from .._thumbnails import thumbnail_headers
            return Response(content=data, media_type="image/webp",
                            headers=thumbnail_headers(filename))

        inline_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
        disposition = "inline" if preview or media_type.lower() in inline_types else "attachment"
        headers = {
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        }
        return Response(content=data, media_type=media_type, headers=headers)

    @app.get("/assets/{asset_id}/content", response_class=Response, include_in_schema=False)
    def asset_content(asset_id: str) -> Response:
        return _asset_binary(asset_id, preview=False)

    @app.get("/assets/{asset_id}/preview", response_class=Response, include_in_schema=False)
    def asset_preview(asset_id: str) -> Response:
        return _asset_binary(asset_id, preview=True)

    @app.get("/assets/{asset_id}/thumbnail", response_class=Response, include_in_schema=False)
    def asset_thumbnail(asset_id: str) -> Response:
        return _asset_binary(asset_id, preview=False, thumbnail=True)

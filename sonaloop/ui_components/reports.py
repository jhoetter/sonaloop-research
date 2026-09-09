"""Prepared report shell shared by product inspection and passive MCP Apps."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReportParts:
    crew: Any = ""
    ref_titles: dict[str, str] = field(default_factory=dict)
    figures: list[list[dict | None]] = field(default_factory=list)
    convergence: tuple[Any, list] = field(default_factory=lambda: ("", []))
    stakeholder_context: Any = ""
    stakeholder_end: Any = ""


def report_body(report: dict, prepared: ReportParts, *, with_toc: bool = False,
                audience: str = "detailed", passive: bool = False):
    """The canonical report shell and narrative sections from prepared context.

    Product and passive consumers share this body. All title, media, crew and
    cited-council resolution has finished before this function is entered.
    """
    from ..web._report import _cover_title, _body, _stakeholder_markdown
    from ..web._html import h, raw, fragment
    from ..web._components import _md
    from ..web._i18n import t
    from ..web._presence import synthesis_status_pill
    from ..web import ui
    from ..config import content_language
    if audience not in {"detailed", "stakeholder"}:
        raise ValueError("report audience must be 'detailed' or 'stakeholder'")
    stakeholder = audience == "stakeholder"
    de = content_language() == "de"
    _t = report.get("title", "")           # the default title ends in " — Report"; custom titles show as-is
    project_title = _t[:-len(" — Report")] if _t.endswith(" — Report") else _t

    # Detail-header attribution (ux-contract §10 W11): when the report's DATA carries voices
    # (statements), their personas lead the cover meta line as the one avatar-group anatomy.
    crew = prepared.crew
    # G2: the lifecycle pill beside the cover eyebrow — the same words as the report rows
    # (the convergence meta line dropped its status TEXT: one encoding, the pill).
    status_pill = (h("span", {"class_": "sl-research-status"}, t("syn_status_" + report["status"])) if passive
                   else raw(synthesis_status_pill(report.get("status", "done"))))

    if report.get("scope") != "project":
        # a convergence synthesis, rendered in the unified report shell.
        meta_parts = [x for x in [
            (f'{len(report.get("council_ids", []))} {t("councils")}'
             if report.get("council_ids") else ""),
            ui.local_date(report.get("created_at") or "")] if x]
        meta_line = fragment(*(fragment(" · " if i else "", value)
                               for i, value in enumerate(meta_parts)))
        cover = h("header", {"class_": "rp-cover sl-research-report-cover" if passive else "rp-cover"},
                  h("div", {"class_": "rp-eyebrow sl-research-report-meta" if passive else "rp-eyebrow"}, t("synthesis_kind"), status_pill),
                  h("h2", {}, project_title) if passive else raw(_cover_title(project_title)),
                  h("div", {"class_": "rp-metaline sl-research-report-meta" if passive else "rp-metaline"}, crew if crew else None, h("span", {}, meta_line)))
        body, toc = prepared.convergence
        article = h("article", {"class_": "report report-syn sl-research-card" if passive else "report report-syn"}, cover, raw(body))
        return (article, toc) if with_toc else article

    def rtitle(ref):
        return prepared.ref_titles.get(ref, ref)
    sections = report.get("sections", [])
    n_studies = len({x for sec in sections for x in sec.get("source_study_ids", [])})
    # The cover meta line is part of the printable DOCUMENT (PDF export reuses this markup),
    # so the whole line follows the content language — `t()` would mix the UI language into
    # an authored German report ("6 sections · 5 Studien", ux-audit P5 finding).
    n_sec = len(sections)
    sections_word = (("Abschnitt" if n_sec == 1 else "Abschnitte") if de
                     else ("section" if n_sec == 1 else "sections"))
    studies_word = (("Studie" if n_studies == 1 else "Studien") if de
                    else ("study" if n_studies == 1 else "studies"))
    meta_parts = [f"{n_sec} {sections_word}", f"{n_studies} {studies_word}",
                  ui.local_date(report.get("created_at") or "")]
    meta_line = fragment(*(fragment(" · " if i else "", value)
                           for i, value in enumerate(meta_parts)))

    cover = h("header", {"class_": "rp-cover sl-research-report-cover" if passive else "rp-cover"},
              h("div", {"class_": "rp-eyebrow sl-research-report-meta" if passive else "rp-eyebrow"}, t("synthesis_kind"), status_pill),
              h("h2", {}, project_title) if passive else raw(_cover_title(project_title)),
              h("div", {"class_": "rp-metaline sl-research-report-meta" if passive else "rp-metaline"}, crew if crew else None, h("span", {}, meta_line)),
              (h("p", {"class_": "rp-lead"}, raw(_md(report["lead"])))
               if report.get("lead") else ""))

    limitations = ""
    if report.get("limitations"):
        limitations = h(
            "section", {"class_": "rp-limitations sl-research-report-limitations" if passive else "rp-limitations", "role": "note"},
            h("h2", {}, "Limitationen" if de else "Limitations"),
            h("ul", {}, *[
                h("li", {}, h("code", {}, row.get("original_status") or
                              ("" if passive else t("cohort_status_overridden"))),
                  " — ", row.get("rationale") or "")
                for row in report.get("limitations") or []
            ]),
        )

    toc = h("div" if passive else "nav", {"class_": "rp-toc sl-research-toc" if passive else "rp-toc"}, h("div", {"class_": "rp-toc-h"}, t("toc")),
            h("ol", {}, *[h("li", {}, h("span" if passive else "a", {} if passive else {"href": f"#rp-s{i}"}, sec["heading"]))
                          for i, sec in enumerate(sections, 1)]))

    secs = []
    stakeholder_context_html = prepared.stakeholder_context
    for i, sec in enumerate(sections, 1):
        figs = prepared.figures[i - 1]
        if stakeholder:
            # A/B stimuli are one comparison and must travel together.  More than
            # two figures still belongs in the detailed evidence report.
            figs = figs[:2]
        section_md = (_stakeholder_markdown(sec.get("markdown", ""))
                      if stakeholder else sec.get("markdown", ""))
        body_html = (_body(section_md, figs, passive=passive) if section_md
                     # plain <em>, not markdown syntax — this string is never md-rendered
                     else h("p", {"class_": "muted"},
                            h("em", {}, f"({'noch nicht verfasst' if de else 'not yet authored'})")))
        if passive and not section_md and figs:
            body_html = fragment(body_html, _body("", figs, passive=True))
        cites = ""
        if sec.get("citations") and not stakeholder:
            rows = []
            for n, c in enumerate(sec["citations"], 1):
                council = h("span", {"class_": "rp-cite-src"}, f" · {rtitle(c['council_id'])}") if c.get("council_id") else ""
                quote = h("span", {"class_": "rp-cite-q"}, f"„{c['quote']}“") if c.get("quote") else ""
                rows.append(h("li", {}, h("span", {"class_": "rp-cite-n"}, str(n)),
                              h("span", {}, h("b", {}, rtitle(c["study_id"])), council, " ", quote)))
            cites = h("div", {"class_": "rp-cites sl-research-report-citations" if passive else "rp-cites"}, h("div", {"class_": "rp-cites-h"}, t("citations")),
                      h("ol", {}, *rows))
        src = ""
        if sec.get("source_study_ids"):
            src_text = ((f'{len(sec["source_study_ids"])} Quellen · Details in Sonaloop')
                        if de else
                        (f'{len(sec["source_study_ids"])} sources · Details in Sonaloop'))
            if not stakeholder:
                src_text = (("Quellen: " if de else "Sources: ")
                            + ", ".join(rtitle(x) for x in sec["source_study_ids"]))
            src = h("div", {"class_": "rp-src sl-research-report-sources" if passive else "rp-src"}, src_text)
        secs.append(h("section", {"class_": "rp-sec sl-research-report-section" if passive else "rp-sec", "id": f"rp-s{i}"},
                      h("h2", {}, h("span", {"class_": "rp-num"}, f"{i:02d}"), sec["heading"]),
                      body_html, cites, src))
    stakeholder_end = prepared.stakeholder_end
    article = h("article", {"class_": "report" + (" report--stakeholder" if stakeholder else "") + (" sl-research-card sl-research-project-report" if passive else "")},
                cover, limitations, "" if stakeholder else toc, stakeholder_context_html,
                *secs, raw(prepared.convergence[0]) if passive else "", stakeholder_end)
    if with_toc:
        return article, [(f"rp-s{i}", sec["heading"]) for i, sec in enumerate(sections, 1)]
    return article

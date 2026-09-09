"""Full native Synthesis projections and the shared prepared convergence body."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SynthesisParts:
    """Trusted presentation fragments already resolved by the product adapter."""
    findings: dict[str, tuple[str, Any]] = field(default_factory=dict)
    charts: Any = ""
    councils: Any = None
    recommendations: Any = ""
    voices: Any = ""
    prompts: Any = ""
    sentiment: Any = ""
    references: Any = ""
    head: Any = ""


def _record(value):
    """Recognize full native records; legacy summaries remain native-text fallbacks."""
    if (not isinstance(value, dict) or not isinstance(value.get("scope"), str)
            or not isinstance(value.get("status"), str) or value["scope"] not in {"convergence", "project"}
            or value["status"] not in {"in_progress", "done"}):
        raise ValueError("Expected a full native Synthesis with explicit scope and status")
    for key in ("id", "title", "start_input", "arc_narrative", "gesamtbild", "positionierung", "created_at"):
        if not isinstance(value.get(key), str):
            raise ValueError(f"Expected native Synthesis {key}")
    for key in ("goal", "next_council_question", "stop_reason", "lead"):
        if key in value and not isinstance(value[key], str):
            raise ValueError(f"Expected native Synthesis {key}")
    if not isinstance(value.get("council_ids"), list) or any(not isinstance(x, str) for x in value["council_ids"]):
        raise ValueError("Expected native council references")
    for key in ("statements", "findings", "sections"):
        if not isinstance(value.get(key), list) or any(not isinstance(x, dict) for x in value[key]):
            raise ValueError(f"Expected native Synthesis {key}")
    for key in ("references", "citations", "prompts", "limitations"):
        if not isinstance(value.get(key, []), list) or any(not isinstance(x, dict) for x in value.get(key, [])):
            raise ValueError(f"Expected native Synthesis {key}")
    for statement in value["statements"]:
        if not isinstance(statement.get("persona_id"), str) or not isinstance(statement.get("text"), str):
            raise ValueError("Expected a native Synthesis statement")
    for finding in value["findings"]:
        if not isinstance(finding.get("text"), str) or not isinstance(finding.get("kind", ""), str):
            raise ValueError("Expected a native Synthesis finding")
    for ref in value.get("references", []):
        if not isinstance(ref.get("council_id"), str):
            raise ValueError("Expected a native Synthesis council reference")
    for citation in value.get("citations", []):
        if not isinstance(citation.get("ref"), str) or not isinstance(citation.get("kind"), str):
            raise ValueError("Expected a native Synthesis citation")
    for prompt in value.get("prompts", []):
        if not isinstance(prompt.get("text"), str):
            raise ValueError("Expected a native Synthesis prompt")
    posture = value.get("claim_posture")
    if posture:
        if (not isinstance(posture, dict) or type(posture.get("verified")) is not bool
                or not isinstance(posture.get("counts", {}), dict)
                or any(type(count) is not int or count < 0 for count in posture.get("counts", {}).values())):
            raise ValueError("Expected a recorded native claim posture")
    for section in value["sections"]:
        if not isinstance(section.get("heading"), str) or not isinstance(section.get("markdown", ""), str):
            raise ValueError("Expected a native report section")
        for key in ("citations", "figures"):
            if not isinstance(section.get(key, []), list) or any(not isinstance(x, dict) for x in section.get(key, [])):
                raise ValueError(f"Expected native section {key}")
        if (not isinstance(section.get("source_study_ids", []), list)
                or any(not isinstance(x, str) for x in section.get("source_study_ids", []))):
            raise ValueError("Expected native section sources")
        for citation in section.get("citations", []):
            if not isinstance(citation.get("study_id"), str):
                raise ValueError("Expected a native section citation")
        for figure in section.get("figures", []):
            if not isinstance(figure.get("kind"), str):
                raise ValueError("Expected a native figure reference")
    return value


def synthesis(value):
    from ..web._html import fragment, raw
    from ..web._render import render_claim_posture_notice
    from ..web._report import render_report
    record = _record(value)
    return fragment(raw(render_claim_posture_notice(record, passive=True)),
                    raw(render_report(record, passive=True))), "ready"


def syntheses(values):
    from .library import collection
    from ..web._i18n import t
    if not isinstance(values, list):
        raise ValueError("Expected the native Synthesis list")
    return collection([synthesis(value)[0] for value in values], empty=t("no_synthesis")), "ready" if values else "empty"


def synthesis_body(syn: dict, prepared: SynthesisParts, *, embed: bool = False, passive: bool = False):
    from ..web._synthesis import _verdict_card, _verdict_split
    from ..web._components import _md, _study_lead, _srcchips
    from ..web._vm import study_head
    from ..web._i18n import t
    from ..web._html import h, raw
    from ..web import ui
    # embed=True omits the bespoke syn-head so the content can sit inside the unified report shell
    # (rp-cover + report typography) — spec/unified-synthesis-report.md §3 (one renderer).
    sec = []  # (id, short_label, html)

    def _block(bid, label, inner):                            # the shared section wrapper
        return h("div", {"class_": "block sl-research-report-block" if passive else "block", "id": bid}, h("h2", {"class_": "bh"}, label), inner)

    def prose(text):
        html = raw(_md(text))
        return html if passive else ui.clamp(html, threshold=ui.SECTION_CLAMP)
    # 1) Structure before prose (ux-contract §3.6): the derived verdict/POV card opens the report,
    # the sentiment + stance charts row follows — only THEN the authored prose (clamped).
    if (verdict := _verdict_card(syn)):
        sec.append(("verdict", t("verdict_h"), verdict))
    if (charts := prepared.charts):
        sec.append(("charts", t("sentiment_block"), _block("charts", t("sentiment_block"), charts)))
    # 2) Executive Summary — the unified Question → Answer lead (shared with the council 'finding'),
    # fed by the shared study view-model so council/synthesis never branch on field names. Long
    # authored bodies clamp at the section threshold (C6) — depth stays, dosed. When the verdict
    # card above already consumed the opening sentences, the section starts from the first
    # NON-consumed sentence (round-3 H1: one screen never repeats prose verbatim); when the card
    # consumed EVERYTHING, the honest fallback is no echo block at all — the verdict IS the summary.
    if syn.get("gesamtbild"):
        vm = study_head(syn, is_synthesis=True)
        answer_md = vm["answer_md"]
        if verdict:
            lead, rest = _verdict_split(syn)           # the SAME splitter the card rendered from
            if lead:
                answer_md = rest
        if answer_md.strip():
            sec.append(("exec", t("summary"), _study_lead(
                prose(answer_md),
                vm["answer_label"], question=vm["question"], qlabel=t("question"))))
    # 2) Cited evidence — councils are DECOUPLED: this synthesis is a standalone answer that may
    # CITE councils (or none). The reference rows are the ONE place the cited councils are named
    # (Round 5 finish: the per-council breakdown rows named the same councils a second time —
    # merged). With >1 cited councils each row carries that council's thin stance strip: N
    # DIFFERENT distributions side by side are a comparison, not the §11 T5 re-encoding (a
    # single cited council's strip WOULD re-encode the chain bars above, so it stays bare).
    belege = prepared.councils
    # Finding LIST sections (key_problems/pain_solvers/open_questions/shortlist) now render through the
    # ONE finding renderer — id + label from finding_kinds.json, prose via _prose (spec/unified-…).
    def _fsec(kind, label, toc=None):
        value = prepared.findings.get(kind)
        if value is None:
            return None
        sid, html = value
        return (sid, toc or label, _block(sid, label, raw(html)))

    if prepared.recommendations:
        sec.append(("empfehlungen", t("recommendations"),
                    _block("empfehlungen", t("recommendations"), raw(prepared.recommendations))))
    if syn.get("positionierung"):
        sec.append(("positionierung", t("positioning"),
                    _block("positionierung", t("positioning"),
                           h("div", {"class_": "sl-prose sm"},
                             prose(syn["positionierung"])))))
    # Structured convergence blocks (GAP-3): a methodology's key problems / affinity clusters /
    # down-select ranking + shortlist render as first-class answer content when present (data-driven —
    # labels via i18n, content free-text; no methodology value hardcoded).
    if (s := _fsec("key_problem", t("key_problems"))):
        sec.append(s)
    if (s := _fsec("cluster", t("affinity_clusters"))):
        sec.append(s)
    if (s := _fsec("ranking", t("ranking"))):
        sec.append(s)
    if (s := _fsec("shortlist", t("shortlist"))):
        sec.append(s)
    # Voices (Stimmen) — the synthesis' OWN per-persona statements (verdict + shift + quoted
    # evidence; spec/unified-artifact-schema). These are cross-council ANALYSIS, not a re-hosted
    # transcript (spec/artifact-cross-references.md): each row is the persona's distilled key
    # argument, with the verbatim council quotes expandable underneath (§3.6e).
    if prepared.voices:
        sec.append(("stimmen", t("voices"), _block("stimmen", t("voices"), raw(prepared.voices))))
    if prepared.prompts:
        sec.append(("prompts", t("question"), raw(prepared.prompts)))
    if prepared.sentiment:
        # The prepared analytics section owns its heading; keep the original
        # product wrapper so embedding it does not repeat that title.
        sec.append(("sentiment-detail", t("sentiment_over_chain"),
                    h("div", {"class_": "block", "id": "sentiment-detail"}, raw(prepared.sentiment))))
    # supporting analysis (omit when empty — an empty section reads as a broken box)
    if (s := _fsec("segment", t("segments"))):
        sec.append(s)
    if (s := _fsec("pain_solver", t("validated_pain_solvers"))):
        sec.append(s)
    if (s := _fsec("open_question", t("open_questions_next_study"), toc=t("open_questions"))):
        sec.append(s)
    if belege:                       # cited evidence (councils) — demoted, near the end
        sec.append(belege)
    # arc (collapsed) — only when there is a narrative; an empty <details> reads as a broken box
    if (syn.get("arc_narrative") or "").strip():
        sec.append(("bogen", t("course"),
                    h("div" if passive else "details", {"class_": "block sl-research-report-block" if passive else "block", "id": "bogen"},
                      h("h2" if passive else "summary", {"class_": "bh"} if passive else {"class_": "bh", "style": "cursor:pointer"}, t("arc_course")),
                      h("div", {"class_": "sl-prose sm"}, raw(_md(syn["arc_narrative"] if passive else _srcchips(syn["arc_narrative"])))))))

    # ---- slim meta strip (replaces the old Eigenschaften rail) — omitted when embedded in the report shell
    if passive:
        shown = {"recommendation", "key_problem", "cluster", "ranking", "shortlist", "segment", "pain_solver", "open_question"}
        for kind, (sid, html) in prepared.findings.items():
            if kind not in shown:
                sec.append((sid, kind, _block(sid, kind, raw(html))))
        if prepared.references:
            sec.append(("sources", t("citations"), _block("sources", t("citations"), raw(prepared.references))))
        for field, label in (("goal", t("report_goal")), ("start_input", t("question")),
                             ("next_council_question", t("report_next_question")), ("stop_reason", t("report_stop_reason"))):
            if syn.get(field):
                sec.append((field, label, _block(field, label, prose(syn[field]))))
    head = "" if embed else prepared.head
    main = head + raw("".join(str(html) for _, _, html in sec))   # section htmls are all trusted (h() Safe or built strings)
    # Unified detail shell: the caller wraps this content in _doc (content column + Properties/Relations
    # aside) and renders the section minimap via _page_rail(toc) — same as every other detail page.
    toc = [(sid, lbl) for sid, lbl, _ in sec]
    return h("div", {"class_": "sl-syn-main sl-research-synthesis-body" if passive else "sl-syn-main"}, raw(main)), toc

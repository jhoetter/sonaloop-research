"""Shared Council reading blocks and passive native full/list projections."""
from __future__ import annotations

from .library import _kit, collection


def h2h_result_html(result: dict, *, passive: bool = False) -> str:
    """The deterministic head-to-head verdict: the overall preference + margin headline, the per-option
    vote tally, and the segment-splits (who-prefers-what) table. The server computes these; the prose
    verdict lives in the exec_summary above. UI language is German by default (match the surrounding UI)."""
    from ..web._html import h, fragment
    from ..web._i18n import t
    options = result.get("options", [])
    title_by = {o["label"]: o.get("title", o["label"]) for o in options}
    pref = result.get("preference")
    decisive = t("h2h_decisive_" + (result.get("decisive") or "tie"))
    if pref:
        headline = h("div", {"class_": "h2h-pref"},
                     h("strong", {}, f"{t('h2h_preference')}: {pref} — {result.get('preference_title') or ''}"),
                     h("span", {"class_": "muted small"}, f" · {decisive} · {t('h2h_margin')} {result.get('margin')}"))
    else:
        headline = h("div", {"class_": "h2h-pref"}, h("strong", {}, t("h2h_no_pref")))

    # Per-option vote tally.
    opt_rows = [h("tr", {}, h("th", {}, t("h2h_options")), h("th", {}, t("h2h_votes")))]
    for o in options:
        is_win = o["label"] == pref
        opt_rows.append(h("tr", {"style": ("font-weight:600" if is_win else "")},
                          h("td", {}, f"{o['label']} — {o.get('title', '')}"),
                          h("td", {}, str(o.get("votes", 0)))))
    table_class = "h2h-table sl-research-format-table" if passive else "h2h-table"
    opt_table = h("table", {"class_": table_class}, *opt_rows)

    # Segment-splits: who prefers what, broken down by persona segment/archetype.
    splits = result.get("segment_splits", [])
    seg_html = ""
    if splits:
        labels = [o["label"] for o in options]
        head = [h("th", {}, t("h2h_segment")), h("th", {}, t("h2h_voters"))]
        head += [h("th", {}, lab) for lab in labels]
        head.append(h("th", {}, t("h2h_prefers")))
        seg_rows = [h("tr", {}, *head)]
        for s in splits:
            cells = [h("td", {}, s.get("segment", "")), h("td", {}, str(s.get("voters", 0)))]
            cells += [h("td", {}, str((s.get("tally") or {}).get(lab, 0))) for lab in labels]
            prefers = s.get("prefers")
            cells.append(h("td", {}, (f"{prefers} — {title_by.get(prefers, '')}" if prefers else t("h2h_tie"))))
            seg_rows.append(h("tr", {}, *cells))
        seg_html = fragment(h("h3", {"style": "margin:14px 0 6px"}, t("h2h_segments")),
                            h("table", {"class_": table_class}, *seg_rows))
    return str(fragment(headline, opt_table, seg_html))


def red_team_result_html(rt: dict, *, passive: bool = False) -> str:
    """The deterministic red-team verdict: the case-against headline (blocker themes + worst severity), the
    per-theme blocker table (how many personas raise each blocker + severity), and — when the run captured
    both directions — a compact case-for table beside it. The server computes these; the prose verdict lives
    in the exec_summary above. UI language is German by default (match the surrounding UI)."""
    from ..web._html import h, fragment
    from ..web._i18n import t
    against = rt.get("case_against") or {}
    themes = against.get("themes", [])
    top = against.get("top_blocker")
    worst = against.get("worst_severity")
    if themes:
        headline = h("div", {"class_": "h2h-pref"},
                     h("strong", {}, f"{t('rt_case_against')}: {against.get('theme_count', 0)} {t('rt_blockers')}"),
                     h("span", {"class_": "muted small"},
                       f" · {against.get('voices', 0)} {t('rt_voices')}"
                       + (f" · {t('rt_top_blocker')}: {top}" if top else "")
                       + (f" · {t('rt_severity')} {t('rt_sev_' + worst)}" if worst else "")))
    else:
        headline = h("div", {"class_": "h2h-pref"}, h("strong", {}, t("rt_no_objections")))

    rows = [h("tr", {}, h("th", {}, t("rt_blocker")), h("th", {}, t("rt_personas")), h("th", {}, t("rt_severity")))]
    for th in themes:
        sev = th.get("severity")
        rows.append(h("tr", {},
                      h("td", {}, th.get("theme", "")),
                      h("td", {}, str(th.get("count", 0))),
                      h("td", {}, t("rt_sev_" + sev) if sev else "")))
    table_class = "h2h-table sl-research-format-table" if passive else "h2h-table"
    against_table = h("table", {"class_": table_class}, *rows)

    # The optional case FOR, beside the case against (both-directions run).
    for_html = ""
    case_for = rt.get("case_for")
    if case_for and case_for.get("themes"):
        fr = [h("tr", {}, h("th", {}, t("rt_pull")), h("th", {}, t("rt_personas")))]
        for th in case_for["themes"]:
            fr.append(h("tr", {}, h("td", {}, th.get("theme", "")), h("td", {}, str(th.get("count", 0)))))
        for_html = fragment(h("h3", {"style": "margin:14px 0 6px"}, t("rt_case_for")),
                            h("table", {"class_": table_class}, *fr))
    return str(fragment(headline, against_table, for_html))


def summary_reads(record: dict, *, clamp_at: int = 900, passive: bool = False):
    """The product's two authored summary blocks, with complete passive prose."""
    from ..web import ui
    from ..web._components import _md, _study_lead
    from ..web._i18n import t
    h, fragment, raw = _kit()
    def prose(text):
        content = raw(_md(text))
        return content if passive else ui.clamp(content, threshold=clamp_at)
    summary = record.get("summary") or ""
    answer = record.get("exec_summary") or summary
    lead = raw(_study_lead(prose(summary), t("answer_exec_summary"), qid="sec-summary")) if summary.strip() else ""
    answer = raw(_study_lead(prose(answer), t("council_finding"))) if answer or not passive else ""
    content = fragment(lead, answer)
    return h("div", {"class_": "sl-research-council-summary"}, content) if passive and content else content


def council_voices(record: dict, store=None, *, backlinks=None, clamp_at: int | None = None, passive=False):
    """Reuse the product's native prompt matching and statement grouping."""
    from .. import artifacts
    from ..web._render import render_statements
    statements = artifacts.council_statements(record)
    prompts = artifacts.council_prompts(record)
    referenced = {(st.get("about") or {}).get("id") for st in statements if st.get("about")}
    group_prompts = [prompt for prompt in prompts if prompt.get("id") in referenced]
    return render_statements(statements, store, group_by="prompt" if group_prompts else "persona",
                             prompts=group_prompts, backlinks=backlinks, clamp_at=clamp_at,
                             collapsible=bool(group_prompts), passive=passive)


def _full_record(value):
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str)
            or not isinstance(value.get("prompt"), str) or not isinstance(value.get("persona_ids"), list)
            or not isinstance(value.get("statements"), list)):
        raise ValueError("Expected a full native Council record")
    if any(not isinstance(pid, str) for pid in value["persona_ids"]):
        raise ValueError("Expected native Council participant identifiers")
    for statement in value["statements"]:
        if (not isinstance(statement, dict) or not isinstance(statement.get("persona_id"), str)
                or not isinstance(statement.get("text"), str)):
            raise ValueError("Expected a native Council statement")
    for field in ("summary", "exec_summary", "proposal", "selection_reason"):
        if field in value and not isinstance(value[field], str):
            raise ValueError(f"Expected native Council {field}")
    for field in ("prompts", "findings", "votes", "questions"):
        if field in value and not isinstance(value[field], list):
            raise ValueError(f"Expected native Council {field}")
    return value


def council(value, *, format_content=None):
    """Actual record_council/get_council data, without reads or inferred voices."""
    from ..web._i18n import t
    from ..web._render import render_claim_posture_notice, render_findings, render_stance
    h, fragment, raw = _kit()
    record = _full_record(value)
    special = [format_content] if format_content is not None else []
    if format_content is None and record.get("head_to_head"):
        special.append(raw(h2h_result_html(record["head_to_head"]["result"])))
    if format_content is None and record.get("red_team"):
        special.append(raw(red_team_result_html(record["red_team"])))
    if format_content is None and record.get("price_ladder"):
        from .council_formats import price_ladder_content
        special.append(price_ladder_content(record["price_ladder"]))
    votes = []
    for vote in record.get("votes") or []:
        if not isinstance(vote, dict):
            raise ValueError("Expected a native Council vote")
        choice = (raw(render_stance(vote["stance"], passive=True)) if isinstance(vote.get("stance"), dict)
                  else str(vote.get("vote") or ""))
        votes.append(h("li", {}, vote.get("persona_id", ""), ": ", choice,
                       f' — {vote["reason"]}' if vote.get("reason") else None))
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("council_kind")), h("h2", {}, record["prompt"])),
             raw(render_claim_posture_notice(record, passive=True)),
             h("p", {"class_": "muted small"}, t("participants"), ": ", ", ".join(record["persona_ids"])),
             h("p", {"class_": "muted small"}, record["selection_reason"]) if record.get("selection_reason") else None,
             summary_reads(record, passive=True), fragment(special),
             h("div", {"class_": "sl-research-council-voices"}, h("h3", {}, t("voices")), council_voices(record, passive=True)),
             raw(render_findings(record.get("findings") or [], passive=True)),
             h("div", {}, h("h3", {}, t("vote")), h("ul", {}, votes)) if votes else None), "ready"


def councils(value):
    """Paginated native list summaries carry counts, never full participant data."""
    from ..web._i18n import t
    h, _, _ = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("items"), list)
            or type(value.get("total")) is not int or value["total"] < 0
            or not isinstance(value.get("has_more"), bool)):
        raise ValueError("Expected the native Council summary page")
    cards = []
    for item in value["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or not isinstance(item.get("prompt"), str) or not isinstance(item.get("votes"), dict)
                or any(type(item.get(key)) is not int or item[key] < 0 for key in ("personas", "turns"))):
            raise ValueError("Expected a native Council summary")
        if any(not isinstance(label, str) or type(count) is not int or count < 0 for label, count in item["votes"].items()):
            raise ValueError("Expected recorded Council vote counts")
        votes = [h("li", {}, str(label), ": ", str(count)) for label, count in item["votes"].items()]
        cards.append(h("article", {"class_": "sl-research-card"},
                       h("header", {}, h("span", {"class_": "sl-research-kind"}, t("council_kind")), h("h2", {}, item["prompt"])),
                       h("p", {"class_": "muted small"}, t("participants"), ": ", str(item["personas"]),
                         " · ", t("voices"), ": ", str(item["turns"])),
                       h("p", {"class_": "muted small"}, t("created"), ": ", item["created_at"]) if item.get("created_at") else None,
                       h("div", {}, h("p", {"class_": "muted small"}, t("vote")), h("ul", {}, votes)) if votes else None))
    return collection(cards, empty=t("no_councils"), total=value["total"], has_more=value["has_more"]), "ready" if cards else "empty"

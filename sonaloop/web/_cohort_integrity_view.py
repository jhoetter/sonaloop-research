"""Read-only inspector for the server-owned Reaction Test cohort gate."""
from __future__ import annotations

from ..cohort_integrity import current_cohort_preflight, preflight_satisfies_project
from ._components import _icon, _label
from ._html import fragment, h, raw, register_css
from ._i18n import t
from . import ui


register_css(r"""
/* Research integrity is supporting evidence, not another report-sized card.  The
   first layer answers "was this checked?"; exact policy inputs remain one native
   disclosure away for keyboard, screen-reader and no-JS users. */
.sl-integrity{width:100%;max-width:760px;margin:14px 0;border:0;border-top:1px solid var(--line-2);border-bottom:1px solid var(--line-2);background:transparent}
.sl-integrity+.sl-integrity{margin-top:-15px;border-top:0}.sl-integrity>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:minmax(0,1fr) auto 14px;align-items:center;gap:12px;padding:12px 0}.sl-integrity>summary::-webkit-details-marker,.sl-integrity-nested>summary::-webkit-details-marker{display:none}
.sl-integrity>summary::after{content:'›';color:var(--faint);font-size:20px;line-height:1;transform:rotate(0);transition:transform 120ms}.sl-integrity[open]>summary::after{transform:rotate(90deg)}
.sl-integrity-heading{display:flex;align-items:flex-start;gap:9px;min-width:0}.sl-integrity-heading>svg{flex:none;width:17px;height:17px;margin-top:2px;color:var(--muted)}.sl-integrity-heading-copy{min-width:0}.sl-integrity-title{display:block;font-weight:650;color:var(--ink)}.sl-integrity-summary{display:block;margin-top:2px;color:var(--muted);font-size:var(--t-sm);line-height:1.4}.sl-integrity-badges{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.sl-integrity-body{padding:2px 0 13px 26px;color:var(--ink);font-size:var(--t-sm)}.sl-integrity-context{max-width:68ch;margin:0 0 7px;color:var(--muted);line-height:1.5}.sl-integrity-nested{border:0;border-top:1px solid var(--line-2);margin-top:7px}.sl-integrity-nested>summary{list-style:none;cursor:pointer;padding:8px 0;color:var(--muted);font-size:var(--t-sm);font-weight:550}.sl-integrity-nested>summary::before{content:'›';display:inline-block;width:14px;color:var(--faint);transform:rotate(0);transition:transform 120ms}.sl-integrity-nested[open]>summary::before{transform:rotate(90deg)}
.sl-integrity-list{margin:0 0 7px;padding-left:18px;color:var(--muted);font-size:var(--t-sm)}.sl-integrity-list li+li{margin-top:5px}.sl-integrity-metrics{display:grid;gap:5px;margin:0 0 8px}.sl-integrity-metrics>div{display:grid;grid-template-columns:minmax(150px,.65fr) minmax(0,1fr);gap:12px}.sl-integrity-metrics dt{color:var(--muted)}.sl-integrity-metrics dd{margin:0;color:var(--ink);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.sl-integrity-technical{font-family:var(--mono);font-size:var(--t-xs)}
.sl-integrity-attention{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:11px 0}.sl-integrity-attention .sl-integrity-heading{align-items:center}.sl-integrity-attention .sl-integrity-summary{margin-top:3px}.sl-cohort-required{margin-top:9px}.sl-cohort-required strong{display:block;margin-bottom:4px}.sl-cohort-limitation{margin-top:9px;color:var(--muted);font-size:var(--t-sm)}
@media(max-width:640px){.sl-integrity>summary{grid-template-columns:minmax(0,1fr) 14px}.sl-integrity-badges{grid-column:1/-1;justify-content:flex-start;padding-left:26px}.sl-integrity-body{padding-left:0}.sl-integrity-metrics>div{grid-template-columns:1fr;gap:1px}.sl-integrity-attention{grid-template-columns:1fr}.sl-integrity-attention>.lbl{margin-left:26px;width:max-content}}
""")


def _maximum_score(rows: list[dict]) -> float:
    return max((float(row.get("score") or 0) for row in rows), default=0.0)


def _cohort_age_text(value) -> str:
    """Human duration before project start; exact fractional hours remain in the record/API."""
    if value is None:
        return t("cohort_age_unknown")
    try:
        hours = max(0.0, float(value))
    except (TypeError, ValueError):
        return t("cohort_age_unknown")
    if hours < 24:
        return t("cohort_age_hours", n=max(1, round(hours)))
    if hours < 14 * 24:
        return t("cohort_age_days", n=max(1, round(hours / 24)))
    if hours < 60 * 24:
        return t("cohort_age_weeks", n=max(1, round(hours / (7 * 24))))
    return t("cohort_age_months", n=max(1, round(hours / (30 * 24))))


def _cohort_origin_text(value: str) -> str:
    from ..ui_components.cohort_preflight import _cohort_origin_text as origin_text
    return origin_text(value)


def render_cohort_integrity(project: dict, store=None, *, show_missing: bool = True,
                            embedded: bool = False) -> str:
    """Render persisted depth, provenance, leakage and remediation state."""
    policy = project.get("integrity") or {}
    current = current_cohort_preflight(project)
    required = bool(policy.get("cohort_preflight_required"))
    if not current:
        if not required:
            return ""
        if not show_missing:
            return ""
        return h(
            "section",
            {"class_": "sl-integrity sl-integrity-attention", "id": "cohort-integrity",
             "role": "status", "aria-label": t("cohort_integrity_missing_help")},
            h("div", {"class_": "sl-integrity-heading"},
              raw(_icon("personas")),
              h("span", {"class_": "sl-integrity-heading-copy"},
                h("strong", {"class_": "sl-integrity-title"}, t("cohort_integrity_h")),
                h("span", {"class_": "sl-integrity-summary"},
                  t("cohort_integrity_missing_help")))),
            raw(_label(t("cohort_integrity_missing"), "var(--amber)")),
        )

    stale = not preflight_satisfies_project(project, store)
    status = "stale" if stale else str(current.get("status") or "needs_reselection")
    labels = {
        "pass": t("cohort_status_pass"),
        "overridden": t("cohort_status_overridden"),
        "needs_deepening": t("cohort_status_needs_deepening"),
        "needs_reselection": t("cohort_status_needs_reselection"),
        "stale": t("cohort_status_stale"),
    }
    colors = {
        "pass": "var(--green)", "overridden": "var(--amber)",
        "needs_deepening": "var(--amber)", "needs_reselection": "var(--red)",
        "stale": "var(--red)",
    }
    representation = current.get("representation") or {}
    leakage = current.get("leakage") or {}
    semantic = leakage.get("semantic") or {}
    time_marker = "__SONALOOP_LOCAL_TIME__"
    meta_text = t("cohort_policy_meta", version=current.get("policy_version") or "—", evaluated=time_marker)
    before, _, after = meta_text.partition(time_marker)
    prepared = {
        "status": status, "stale": stale,
        "icon": raw(_icon("personas")),
        "status_badge": raw(_label(labels.get(status, status), colors.get(status, "var(--muted)"))),
        "unverified_badge": (raw(_label(t("cohort_unverified_countervoices_n",
            n=len(representation.get("unverified_countervoice_persona_ids") or [])), "var(--red)"))
            if representation.get("unverified_countervoice_persona_ids") else None),
        "persona_ages": [_cohort_age_text(row.get("profile_age_hours_at_project_start"))
            for row in (current.get("depth") or {}).get("personas") or []],
        "lexical_max": _maximum_score(leakage.get("lexical") or []),
        "semantic_max": _maximum_score(semantic.get("scores") or []) if semantic.get("provided") else None,
        "meta": fragment(before, ui.local_ts(current.get("evaluated_at") or ""), after),
    }
    from ..ui_components.cohort_preflight import integrity_content
    return integrity_content(current, prepared=prepared, embedded=embedded)

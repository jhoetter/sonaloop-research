"""Pure hypothesis/decision bodies shared by product detail and passive MCP views.

Callers supply any resolved reference markup. The renderer never receives a Store,
resolves a native record, derives a verdict or performs an action.
"""
from __future__ import annotations

from .library import _kit, collection


def predicted_text(pred: dict) -> str:
    from ..web._i18n import t
    if "expected_value" in pred:
        expected = str(pred.get("expected_value"))
        if pred.get("tolerance"):
            expected += f' ±{pred["tolerance"]:g}'
    else:
        expected = (t("hyp_dir_increase") if pred.get("expected_direction") == "increase"
                    else t("hyp_dir_decrease"))
    out = f'{pred.get("metric", "")} → {expected}'
    if pred.get("confidence") is not None:
        out += f' · {t("hyp_confidence")} {pred["confidence"]:.0%}'
    return out


def hypothesis_reads(hypothesis: dict, *, source=None, derived=None):
    from ..web._i18n import t
    h, fragment, _ = _kit()
    result = hypothesis.get("result") or {}
    values = [h("span", {}, h("span", {"class_": "muted"}, t("hyp_predicted"), ": "),
                predicted_text(hypothesis.get("prediction") or {}))]
    if result:
        values.append(h("span", {}, h("span", {"class_": "muted"}, t("hyp_observed"), ": "),
                        str(result.get("observed_value", ""))))
    note_text = result.get("note") or (hypothesis.get("drop_note") if hypothesis.get("status") == "dropped" else "")
    note = h("p", {"class_": "muted small"}, note_text) if note_text else None
    return h("div", {"class_": "sl-research-values"}, fragment(values)), note, source, derived


def decision_reads(decision: dict, *, based: list, rejected: list, by_id: dict | None = None,
                   clamp_at: int = 420, dec_href=lambda oid: f"#dec-{oid}"):
    from ..web import ui
    from ..web._i18n import t
    h, fragment, _ = _kit()
    alternatives = decision.get("rejected") or []
    if len(rejected) != len(alternatives):
        raise ValueError("Each rejected alternative needs its supplied reference presentation")
    body = ui.clamp(decision.get("decision", ""), threshold=clamp_at)
    evidence = h("p", {"class_": "muted small turn-refs"}, t("rel_based_on"), ": ", fragment(based))
    why_not = fragment([
        h("p", {"class_": "muted small turn-refs"}, t("dec_rejected"), ": ", reference,
          f' — {alternative["note"]}' if alternative.get("note") else "")
        for alternative, reference in zip(alternatives, rejected, strict=True)])
    links = []
    for field, label in (("superseded_by", "dec_superseded_by"), ("supersedes", "dec_supersedes")):
        if decision.get(field):
            identifier = decision[field]
            title = ((by_id or {}).get(identifier) or {}).get("title", identifier)
            links.append(h("p", {"class_": "muted small"}, t(label), ": ",
                           h("a", {"href": dec_href(identifier)}, title)))
    return body, evidence, why_not, fragment(links)


def _card(kind: str, title: str, status: str, parts):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t(kind)),
               h("h2", {}, title), h("p", {"class_": "sl-research-status"}, status)),
             h("div", {"class_": "sl-research-artifact-body"}, parts))


def hypothesis(value):
    from ..web._i18n import t
    from ..web._presence import hypothesis_status_label
    from ..web._render import _refs_line
    _, _, raw = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str)
            or not isinstance(value.get("text"), str) or not isinstance(value.get("prediction"), dict)
            or not isinstance(value.get("status"), str)):
        raise ValueError("Expected a native hypothesis")
    prediction = value["prediction"]
    if (not isinstance(prediction.get("metric"), str) or not prediction["metric"].strip()
            or ("expected_value" not in prediction and prediction.get("expected_direction") not in {"increase", "decrease"})):
        raise ValueError("Expected a recorded checkable prediction")
    result = value.get("result") or {}
    source = raw(_refs_line([result["source"]], t("hyp_observed"), passive=True)) if result.get("source") else None
    derived = raw(_refs_line(value["derived_from"], t("rel_based_on"), passive=True)) if value.get("derived_from") else None
    return _card("hypothesis_kind", value["text"], hypothesis_status_label(value["status"]),
                 hypothesis_reads(value, source=source, derived=derived)), "ready"


def decision(value):
    from ..web._presence import decision_status_label
    from ..web._render import render_ref
    _, _, raw = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str)
            or not isinstance(value.get("title"), str) or not isinstance(value.get("decision"), str)
            or not isinstance(value.get("status"), str) or not isinstance(value.get("based_on"), list)):
        raise ValueError("Expected a native decision")
    # A passive result has no expand action; keep the entire authored body visible.
    parts = decision_reads(value, based=[raw(render_ref(ref, show_role=False, passive=True)) for ref in value["based_on"]],
                           rejected=[raw(render_ref(ref, show_role=False, passive=True)) for ref in value.get("rejected") or []],
                           clamp_at=len(value["decision"]))
    return _card("decision_kind", value["title"], decision_status_label(value["status"]), parts), "ready"


def hypotheses(value):
    return _list(value, "hypotheses", hypothesis, "no_hypotheses")


def decisions(value):
    return _list(value, "decisions", decision, "no_decisions")


def _list(value, key, render, empty):
    from ..web._i18n import t
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise ValueError(f"Expected native {key}")
    cards = [render(item)[0] for item in value[key]]
    return collection(cards, empty=t(empty)), "ready" if cards else "empty"


def hypothesis_write(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native hypothesis write result")
    return hypothesis(value.get("hypothesis"))


def decision_write(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native decision write result")
    cards = [decision(value.get("decision"))[0]]
    if "successor" in value:
        cards.append(decision(value["successor"])[0])
    return collection(cards, empty=""), "ready"

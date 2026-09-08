"""Shared survey instrument/result bodies; supplied native aggregates only."""
from __future__ import annotations

from .library import _kit, collection


def count_row(label: str, count: int, total: int):
    """A native count and its proportion, using a passive accessible HTML meter."""
    from ..web._i18n import t
    h, _, _ = _kit()
    if type(count) is not int or type(total) is not int or count < 0 or total < 0:
        raise ValueError("Expected a bounded native response count")
    if count > total:
        # Native multi-select imports permit repeated choices. Preserve the
        # actual tally while refusing to depict it as a unit proportion.
        return h("div", {"class_": "sl-research-count-overflow"},
                 h("p", {}, label, ": ", count),
                 h("p", {"class_": "muted small"}, t("survey_count_exceeds_answers", count=count, total=total)))
    ratio = f'{count / total if total else 0:.12f}'.rstrip("0").rstrip(".")
    return h("div", {"class_": "sl-research-count-row"}, h("span", {}, label),
             h("meter", {"class_": "sl-research-meter", "min": 0, "max": 1, "value": ratio,
                          "aria-label": label}, f"{count} / {total}"), h("span", {}, count))


def predicted_actual(comparison: dict):
    from .. import artifacts
    from ..web._i18n import t
    from ..web._render import render_ref
    h, fragment, raw = _kit()
    terms = artifacts.stance_terms()
    names = {term["term"] for term in terms}
    predicted = comparison.get("predicted")
    actual = comparison.get("actual")
    for distribution in (predicted, actual):
        if (not isinstance(distribution, dict) or type(distribution.get("n")) is not int or distribution["n"] < 0
                or not isinstance(distribution.get("counts"), dict)):
            raise ValueError("Expected native comparison counts")
        if set(distribution["counts"]) != names:
            raise ValueError("Expected the complete native comparison vocabulary")
        if any(type(count) is not int or count < 0 or count > distribution["n"] for count in distribution["counts"].values()):
            raise ValueError("Expected bounded native comparison counts")
    head = h("tr", {}, h("th", {}, t("survey_stance_mapped")),
             h("th", {}, f'{t("survey_predicted")} ({predicted.get("n", 0)})'),
             h("th", {}, f'{t("survey_actual")} ({actual.get("n", 0)})'))
    rows = [h("tr", {}, h("td", {}, t(artifacts.stance_meta(term["value"])["label_key"])),
              h("td", {}, (predicted.get("counts") or {}).get(term["term"], 0)),
              h("td", {}, (actual.get("counts") or {}).get(term["term"], 0)))
            for term in terms]
    references = fragment([raw(render_ref(ref, passive=True)) for ref in predicted.get("refs") or []])
    return h("div", {"class_": "sl-research-comparison"},
             h("table", {}, h("thead", {}, head), h("tbody", {}, rows)), references)


def question_content(question: dict, result: dict | None = None):
    from ..web._i18n import t
    h, _, _ = _kit()
    body = [h("div", {"class_": "sl-research-question-heading"},
              h("span", {"class_": "muted small"}, question.get("id") or question.get("question_id", "")),
              h("b", {}, question.get("text", "")))]
    if result is None:
        if question.get("options"):
            body.append(h("ul", {"class_": "sl-research-options"}, [h("li", {}, option) for option in question["options"]]))
        return h("div", {"class_": "sl-research-question-content"}, body)
    answered = result.get("answered")
    if type(answered) is not int or answered < 0:
        raise ValueError("Expected native answered count")
    if question.get("kind") == "text":
        answers = result.get("answers") or []
        # survey_results itself bounds retained answers to 50. Show every supplied
        # answer, rather than losing qualifiers behind the product's old 8-row cap.
        body.extend(h("blockquote", {}, answer) for answer in answers)
        if len(answers) < answered:
            body.append(h("p", {"class_": "muted small"}, f'{len(answers)} / {answered}'))
    else:
        counts = result.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("Expected native option counts")
        body.extend(count_row(option, count, answered) for option, count in counts.items())
    if question.get("stance_mapped") and result.get("comparison"):
        body.append(predicted_actual(result["comparison"]))
    if not answered:
        body.append(h("p", {"class_": "muted small"}, t("no_survey_responses")))
    return h("div", {"class_": "sl-research-question-content"}, body)


def question_kind_label(question):
    from ..web._primitive_taxonomy import survey_question_form_labels
    return " · ".join(survey_question_form_labels({"questions": [question]}))


def _question_card(question: dict, result: dict | None = None):
    from ..web._i18n import t
    h, _, _ = _kit()
    return h("div", {"class_": "sl-research-question"},
             h("p", {"class_": "muted small"}, question_kind_label(question),
               f' · {t("n_responses", n=result["answered"])}' if result is not None else ""),
             question_content(question, result))


def _survey_card(value: dict, *, aggregated: bool = False):
    from ..web._i18n import t
    from ..web._render import render_ref
    h, _, raw = _kit()
    key = "survey_id" if aggregated else "id"
    if (not isinstance(value, dict) or not isinstance(value.get(key), str)
            or not isinstance(value.get("title"), str) or not isinstance(value.get("questions"), list)
            or value.get("status") not in {"draft", "open", "closed"}):
        raise ValueError("Expected native survey instrument or aggregate")
    questions = value["questions"]
    if any(not isinstance(question, dict) or not isinstance(question.get("text"), str)
           or question.get("kind") not in {"single", "multi", "scale", "text"} for question in questions):
        raise ValueError("Expected native survey questions")
    count = value.get("responses" if aggregated else "response_count")
    # record_survey returns an instrument without live response_count. Missing is
    # unknown, never an invented zero or an implied collection of respondents.
    if (aggregated and count is None) or (count is not None and (type(count) is not int or count < 0)):
        raise ValueError("Expected native survey response count")
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("survey_kind")),
               h("h2", {}, value["title"]), h("p", {"class_": "sl-research-status"}, t("survey_status_" + value["status"])),
               h("p", {"class_": "muted small"}, t("n_responses", n=count)) if count is not None else None),
             h("p", {}, value["intro"]) if value.get("intro") else None,
             [_question_card(question, question if aggregated else None) for question in questions],
             [raw(render_ref(ref, passive=True)) for ref in value.get("derived_from") or []])


def survey(value):
    return _survey_card(value), "ready"


def survey_write(value):
    if not isinstance(value, dict):
        raise ValueError("Expected native survey write result")
    return survey(value.get("survey"))


def surveys(value):
    from ..web._i18n import t
    if not isinstance(value, dict) or not isinstance(value.get("surveys"), list):
        raise ValueError("Expected native survey collection")
    cards = [_survey_card(item) for item in value["surveys"]]
    return collection(cards, empty=t("no_surveys")), "ready" if cards else "empty"


def survey_results(value):
    card = _survey_card(value, aggregated=True)
    return card, "ready" if value.get("responses") else "empty"


def response_summary(total: int, *, level: str = "h2"):
    from ..web._i18n import t
    h, _, _ = _kit()
    if type(total) is not int or total < 0:
        raise ValueError("Expected native response total")
    return h(level, {"class_": "sl-research-response-total"}, t("n_responses", n=total))


def imported(value):
    from ..web._i18n import t
    h, _, _ = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("survey_id"), str)
            or type(value.get("imported")) is not int or value["imported"] < 0):
        raise ValueError("Expected native survey import receipt")
    return h("article", {"class_": "sl-research-card"},
             h("header", {}, h("span", {"class_": "sl-research-kind"}, t("survey_kind")),
               h("h2", {}, t("survey_import_complete"))),
             h("p", {}, t("survey_import_processed", n=value["imported"])),
             response_summary(value.get("total_responses"), level="p"),
             h("code", {}, value["survey_id"])), "ready"

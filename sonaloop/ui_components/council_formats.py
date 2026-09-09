"""Pure Council format bodies shared by the inspector and native result views.

Aggregates are recorded values, never recalculated here. Flattened getters do
not contain a Council transcript. All references remain supplied literal IDs.
"""
from __future__ import annotations

import math

from .library import _kit, collection


def _object(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a native Council format object")
    return value


def _rows(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Expected native Council format rows")
    return value


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Expected native literal identifiers")
    return value


def _text(value, *keys):
    if any(not isinstance(value.get(key), str) for key in keys):
        raise ValueError("Expected native Council format text: " + ", ".join(keys))


def _counts(value, *keys):
    if any(type(value.get(key)) is not int or value[key] < 0 for key in keys):
        raise ValueError("Expected recorded nonnegative counts")


def _number(value, *, share=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (share and not 0 <= value <= 1):
        raise ValueError("Expected a finite recorded value")


def _optional_text(value, *keys):
    for key in keys:
        if key in value and value[key] is not None and not isinstance(value[key], str):
            raise ValueError("Expected native Council format text: " + key)


def _head_result(value):
    _object(value)
    options = _rows(value.get("options"))
    for option in options:
        _text(option, "label", "title")
        _counts(option, "votes")
    labels = [option["label"] for option in options]
    if len(labels) < 2 or len(set(labels)) != len(labels):
        raise ValueError("Expected distinct recorded options")
    _counts(value, "voters", "abstentions")
    _text(value, "decisive")
    _number(value.get("margin"), share=True)
    _optional_text(value, "preference", "preference_title")
    if ("preference" not in value or "preference_title" not in value
            or value["preference"] not in [None, *labels]
            or value.get("decisive") not in {"tie", "narrow", "clear", "decisive"}):
        raise ValueError("Expected the recorded preference verdict")
    for bucket in [value, *_rows(value.get("segment_splits"))]:
        tally = _object(bucket.get("tally"))
        if set(tally) != set(labels):
            raise ValueError("Expected every recorded option tally")
        _counts(tally, *labels)
        _counts(bucket, "voters", "abstentions")
        _number(bucket.get("margin"), share=True)
        if bucket is not value:
            _text(bucket, "segment")
            if "prefers" not in bucket or bucket["prefers"] not in [None, *labels]:
                raise ValueError("Expected the recorded segment preference")
    return value


def _head(value):
    _object(value)
    _head_result(value.get("result"))
    for option in _rows(value.get("options")):
        _text(option, "label", "kind", "title")
        if option["kind"] == "text":
            _text(option, "text")
        elif option["kind"] == "artifact":
            _text(option, "artifact_id")
        else:
            raise ValueError("Expected a native text or artifact option")
    for preference in _rows(value.get("preferences")):
        _text(preference, "persona_id")
        _optional_text(preference, "choice", "label", "preference", "reason")
        if "intensity" in preference and type(preference["intensity"]) not in (str, int, float, type(None)):
            raise ValueError("Expected a scalar recorded intensity")
    _text(value, "recorded_at")
    meta = _object(value.get("variant_meta", {}))
    _optional_text(meta, "hypothesis_id")
    for label, variant in _object(meta.get("variants", {})).items():
        if not isinstance(label, str):
            raise ValueError("Expected variant labels")
        _object(variant)
    for pid, order in _object(meta.get("order_shown", {})).items():
        if not isinstance(pid, str):
            raise ValueError("Expected literal participant IDs")
        _strings(order)
    return value


def head_to_head_content(value):
    """Complete supplied options/preferences around the existing verdict body."""
    from .councils import h2h_result_html
    from ..web._i18n import t
    value = _head(value)
    h, fragment, raw = _kit()
    options = [h("li", {}, h("strong", {}, option["label"], " — ", option["title"]),
                 h("p", {}, option["text"] if option["kind"] == "text" else "artifact:" + option["artifact_id"]))
               for option in value["options"]]
    preferences = []
    for pref in value["preferences"]:
        choice = pref.get("choice") or pref.get("label") or pref.get("preference") or ""
        preferences.append(h("li", {}, h("strong", {}, pref["persona_id"]), ": ", choice,
            h("p", {}, pref["reason"]) if pref.get("reason") else None,
            h("p", {}, t("cf_intensity"), ": ", str(pref["intensity"])) if pref.get("intensity") is not None else None))
    meta = value.get("variant_meta") or {}
    metadata = []
    for label, variant in meta.get("variants", {}).items():
        # Extensible native variant details remain in the canonical output;
        # named scalar values are readable without a generic JSON dump.
        details = [h("li", {}, key, ": ", str(item)) for key, item in variant.items()
                   if isinstance(key, str) and type(item) in (str, int, float, bool)]
        metadata.append(h("li", {}, label, h("ul", {}, details)))
    for pid, order in meta.get("order_shown", {}).items():
        metadata.append(h("li", {}, t("cf_order"), " · ", pid, ": ", " → ".join(order)))
    if meta.get("hypothesis_id"):
        metadata.append(h("li", {}, "hypothesis:", meta["hypothesis_id"]))
    result = value["result"]
    segments = [h("li", {}, row["segment"], ": ", t("cf_abstentions"), " ", str(row["abstentions"]),
                  " · ", t("h2h_margin"), " ", str(row["margin"])) for row in result["segment_splits"]]
    return h("div", {"class_": "sl-research-head-to-head"}, raw(h2h_result_html(result, passive=True)),
             h("p", {}, t("h2h_voters"), ": ", str(result["voters"]), " · ",
               t("cf_abstentions"), ": ", str(result["abstentions"])), h("ul", {}, segments),
             h("h3", {}, t("h2h_options")), h("ul", {}, options),
             h("h3", {}, t("cf_preferences")), h("ul", {}, preferences),
             fragment(h("h3", {}, t("cf_variant_meta")), h("ul", {}, metadata)) if metadata else None,
             h("p", {"class_": "muted small"}, t("cf_recorded"), ": ", value["recorded_at"]))


def _price_result(value):
    _object(value)
    bands = _strings(value.get("bands"))
    if not bands or len(set(bands)) != len(bands):
        raise ValueError("Expected recorded price bands")
    overall = _object(value.get("overall"))
    segments = _rows(value.get("segments"))
    for bucket in [overall, *segments]:
        _counts(bucket, "respondents")
        if bucket is not overall:
            _text(bucket, "segment")
        for point in _rows(bucket.get("points")):
            _text(point, "label")
            _number(point.get("amount"))
            _counts(point, "respondents")
            counts = _object(point.get("counts"))
            if set(counts) != set(bands):
                raise ValueError("Expected all recorded price band counts")
            _counts(counts, *bands)
            if "acceptance" not in point:
                raise ValueError("Expected a recorded acceptance value or null")
            if point["acceptance"] is not None:
                _number(point["acceptance"], share=True)
        for field in ("acceptable_range", "cliff"):
            if field not in bucket:
                raise ValueError("Expected a recorded range/cliff or null")
            if bucket[field] is not None:
                bound = _object(bucket[field])
                names = ("low", "high") if field == "acceptable_range" else ("from", "to")
                _text(bound, *names)
                for name in names:
                    _number(bound.get(name + "_amount"))
                if field == "cliff":
                    _number(bound.get("drop"), share=True)
    return value


def price_result_content(value):
    """The product's price table, including recorded nulls and duplicate counts."""
    from ..web._i18n import t
    value = _price_result(value)
    h, _, _ = _kit()
    sections = []
    for bucket in [value["overall"], *value["segments"]]:
        rows = []
        for point in bucket["points"]:
            counts = h("ul", {}, [h("li", {}, band, ": ", str(point["counts"][band])) for band in value["bands"]])
            acceptance = t("cf_unanswered") if point["acceptance"] is None else str(point["acceptance"])
            rows.append(h("tr", {}, h("th", {"scope": "row"}, point["label"],
                h("p", {"class_": "muted small"}, t("cf_amount"), ": ", str(point["amount"]))),
                h("td", {}, h("p", {}, t("cf_responses"), ": ", str(point["respondents"]),
                  " · ", t("cf_acceptance"), ": ", acceptance), counts)))
        rng, cliff = bucket["acceptable_range"], bucket["cliff"]
        range_text = (f'{rng["low"]} ({rng["low_amount"]}) → {rng["high"]} ({rng["high_amount"]})'
                      if rng else t("cf_none"))
        cliff_text = (f'{cliff["from"]} ({cliff["from_amount"]}) → {cliff["to"]} ({cliff["to_amount"]}): {cliff["drop"]}'
                      if cliff else t("cf_none"))
        sections.append(h("section", {"class_": "sl-research-price-bucket"},
            h("h3", {}, bucket.get("segment", t("cf_overall"))),
            h("p", {}, t("participants"), ": ", str(bucket["respondents"])),
            h("p", {}, t("cf_range"), ": ", range_text), h("p", {}, t("cf_cliff"), ": ", cliff_text),
            h("table", {"class_": "h2h-table sl-research-price-table"},
              h("thead", {}, h("tr", {}, h("th", {"scope": "col"}, t("cf_price")),
                h("th", {"scope": "col"}, t("cf_responses")))), h("tbody", {}, rows))))
    return h("div", {"class_": "sl-research-price-result"}, sections)


def price_ladder_content(value):
    from ..web._i18n import t
    _object(value)
    _text(value, "recorded_at")
    for point in _rows(value.get("price_points")):
        _text(point, "label")
        _number(point.get("amount"))
    for response in _rows(value.get("responses")):
        _text(response, "persona_id", "price", "band", "quote")
        _number(response.get("amount"))
    result = price_result_content(value.get("result"))
    h, _, _ = _kit()
    responses = [h("li", {}, h("strong", {}, row["persona_id"]), " · ", row["price"],
                   " (", str(row["amount"]), ") · ", row["band"], h("blockquote", {}, row["quote"]))
                 for row in value["responses"]]
    return h("div", {"class_": "sl-research-price-ladder"}, result,
             h("h3", {}, t("cf_responses")), h("ul", {}, responses),
             h("p", {"class_": "muted small"}, t("cf_recorded"), ": ", value["recorded_at"]))


def _red(value):
    _object(value)
    _text(value, "stance", "recorded_at")
    if value["stance"] not in {"against", "for", "both"}:
        raise ValueError("Expected recorded red-team direction")
    roles = _object(value.get("roles"))
    for pid, role in roles.items():
        if not isinstance(pid, str):
            raise ValueError("Expected literal participant IDs")
        _object(role)
        _text(role, "id", "name", "lens")
    _rows(value.get("objections"))
    _rows(value.get("endorsements"))
    if "case_for" not in value:
        raise ValueError("Expected recorded case_for or null")
    for name in ("case_against", "case_for"):
        case = value.get(name)
        if name == "case_for" and case is None:
            continue
        _object(case)
        _counts(case, "theme_count", "voices", "total")
        if name == "case_against":
            if "top_blocker" not in case or "worst_severity" not in case:
                raise ValueError("Expected the recorded blocker verdict or null")
            _optional_text(case, "top_blocker", "worst_severity")
            if case["worst_severity"] not in {None, "low", "medium", "high", "critical"}:
                raise ValueError("Expected the recorded worst severity")
        for theme in _rows(case.get("themes")):
            _text(theme, "theme")
            _counts(theme, "count")
            _strings(theme.get("personas"))
            for item in _rows(theme.get("items")):
                _text(item, "text")
                _optional_text(item, "persona_id", "severity", "severity_raw")
                if name == "case_against" and item.get("severity") not in {"low", "medium", "high", "critical"}:
                    raise ValueError("Expected recorded objection severity")
            if name == "case_against" and theme.get("severity") not in {"low", "medium", "high", "critical"}:
                raise ValueError("Expected recorded theme severity")
    return value


def red_team_content(value):
    from .councils import red_team_result_html
    from ..web._i18n import t
    value = _red(value)
    h, _, raw = _kit()
    cases = []
    for name, label in (("case_against", "rt_case_against"), ("case_for", "rt_case_for")):
        case = value[name]
        if case is None:
            continue
        themes = []
        for theme in case["themes"]:
            items = [h("li", {}, h("strong", {}, item.get("persona_id") or ""),
                " · " + item["severity"] if item.get("severity") else None,
                " (" + item["severity_raw"] + ")" if item.get("severity_raw") else None,
                h("p", {}, item["text"])) for item in theme["items"]]
            themes.append(h("section", {}, h("h4", {}, theme["theme"]),
                h("p", {}, t("participants"), ": ", ", ".join(theme["personas"])), h("ul", {}, items)))
        cases.append(h("section", {}, h("h3", {}, t(label)),
                       h("p", {}, t("cf_responses"), ": ", str(case["total"])), themes))
    return h("div", {"class_": "sl-research-red-team"}, raw(red_team_result_html(value, passive=True)),
             h("p", {}, value["stance"]),
             h("ul", {}, [h("li", {}, h("strong", {}, pid), ": ", role["name"], " (", role["id"], ")",
                            h("p", {}, role["lens"])) for pid, role in value["roles"].items()]), cases,
             h("p", {"class_": "muted small"}, t("cf_recorded"), ": ", value["recorded_at"]))


def _detail(value, label, content):
    from ..web._i18n import t
    _object(value)
    _text(value, "id", "prompt", "project_id", "created_at")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"},
        h("header", {}, h("span", {"class_": "sl-research-kind"}, t(label)), h("h2", {}, value["prompt"])),
        h("p", {"class_": "muted small"}, "council:", value["id"], " · project:", value["project_id"]),
        h("p", {"class_": "muted small"}, t("created"), ": ", value["created_at"]), content), "ready"


def head_to_head(value):
    return _detail(value, "h2h_title", head_to_head_content(value))


def price_ladder(value):
    return _detail(value, "cf_price_ladder", price_ladder_content(value))


def red_team(value):
    return _detail(value, "rt_title", red_team_content(value))


def price_analysis(value):
    from ..web._i18n import t
    _object(value)
    _text(value, "session_id", "project_id", "prompt")
    if value.get("schema") != "price_ladder_analysis":
        raise ValueError("Expected the native price_ladder_analysis result")
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, value["prompt"]),
        h("p", {}, t("cf_price_ladder"), " · council:", value["session_id"]), price_result_content(value)), "ready"


def _write(value, key, render):
    from .councils import _full_record, council
    value = _full_record(value)
    return council(value, format_content=render(value.get(key)))


def head_to_head_write(value):
    return _write(value, "head_to_head", head_to_head_content)


def price_ladder_write(value):
    return _write(value, "price_ladder", price_ladder_content)


def red_team_write(value):
    return _write(value, "red_team", red_team_content)


def query_council_card(row):
    """The supplied lean substrate row, shared with the study result composition."""
    from ..web._i18n import t
    _text(row, "id", "project_id", "prompt", "created_at")
    _counts(row, "statements", "votes", "questions")
    _strings(row.get("persona_ids"))
    h, _, _ = _kit()
    return h("article", {"class_": "sl-research-card"}, h("h2", {}, row["prompt"]),
        h("p", {"class_": "muted small"}, "council:", row["id"], " · project:", row["project_id"]),
        h("p", {}, t("participants"), ": ", ", ".join(row["persona_ids"])),
        h("p", {}, t("cf_query_counts", statements=row["statements"], votes=row["votes"], questions=row["questions"])),
        h("p", {"class_": "muted small"}, t("created"), ": ", row["created_at"]))


def query_councils(value):
    """Native offset page: integer row counts are not list_councils vote tallies."""
    from ..web._i18n import t
    _object(value)
    if type(value.get("substrate_version")) is not int or value["substrate_version"] != 1:
        raise ValueError("Expected native Council substrate version 1")
    _counts(value, "total", "limit", "offset")
    if "next_offset" not in value or (value["next_offset"] is not None
            and (type(value["next_offset"]) is not int or value["next_offset"] < 0)):
        raise ValueError("Expected native next_offset or null")
    h, _, _ = _kit()
    cards = [query_council_card(row) for row in _rows(value.get("items"))]
    return h("div", {"class_": "sl-research-council-query"},
        h("p", {"class_": "muted small"}, t("cf_query_page", offset=value["offset"], shown=len(cards), total=value["total"])),
        collection(cards, empty=t("no_councils"), has_more=value["next_offset"] is not None)), "ready" if cards else "empty"

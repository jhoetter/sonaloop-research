"""Shared native funnel rows; chart fragments are explicit presentation inputs."""
from __future__ import annotations

from .library import _kit


def funnel_content(value: dict, *, bars: list, legend, passive=False):
    from ..web._components import _icon
    from ..web._i18n import t
    h, fragment, raw = _kit()
    if len(bars) != len(value["rows"]):
        raise ValueError("Every native funnel row needs its own chart fragment")
    rows = []
    for row, bar in zip(value["rows"], bars, strict=True):
        rows.append(h("div", {"class_": "sess-frow sl-research-funnel-row" if passive else "sess-frow"},
                      h("span", {"class_": "sfl"}, t("step_n", n=row["step"])), bar,
                      h("span", {"class_": "sfn"},
                        f'{row["entered"]} {t("funnel_entered")} · {row["dropped"]} {t("funnel_dropped")}')))
        if passive and row.get("caption"):
            rows.append(h("p", {}, row["caption"]))
        if passive and row.get("personas"):
            rows.append(h("p", {"class_": "muted small"}, t("personas"), ": ", ", ".join(row["personas"])))
        for reason in row.get("drop_reasons", []):
            rows.append(h("div", {"class_": "sess-frow sl-research-funnel-reason" if passive else "sess-frow"},
                          h("span", {}), h("span", {"class_": "sess-freason"},
                            None if passive else raw(_icon("warning")), " ", reason)))
    return h("div", {"class_": "sess-funnel sl-research-funnel" if passive else "sess-funnel", "id": "funnel"},
             h("h2", {}, t("funnel_h"), " · ", (value.get("subject") or {}).get("key", "")),
             h("p", {"class_": "ihint"}, t("funnel_hint", n=value["sessions"])), fragment(*rows), legend)


def funnel(value):
    from ..web._i18n import t
    from .surveys import count_row
    h, fragment, _ = _kit()
    if (not isinstance(value, dict) or not isinstance(value.get("subject"), dict)
            or not isinstance(value.get("rows"), list)
            or any(type(value.get(name)) is not int or value[name] < 0 for name in ("sessions", "completed"))
            or value["completed"] > value["sessions"]):
        raise ValueError("Expected the native Session funnel")
    bars = []
    for row in value["rows"]:
        if (not isinstance(row, dict) or any(type(row.get(name)) is not int or row[name] < 0
                                            for name in ("step", "entered", "continued", "dropped"))
                or row["continued"] + row["dropped"] != row["entered"]
                or row["entered"] > value["sessions"]
                or not isinstance(row.get("drop_reasons"), list)):
            raise ValueError("Expected complete native per-step funnel counts")
        bars.append(h("div", {}, count_row(t("funnel_continued"), row["continued"], row["entered"]),
                      count_row(t("funnel_dropped"), row["dropped"], row["entered"])))
    legend = h("p", {}, t("completed"), ": ", str(value["completed"]), " / ", str(value["sessions"]))
    flow = value.get("flow")
    headline = h("h2", {}, flow["title"]) if isinstance(flow, dict) and isinstance(flow.get("title"), str) else None
    biggest = value.get("biggest_dropoff")
    detail = (h("p", {}, t("outcome_dropped", n=biggest["step"]), ": ", str(biggest["dropped"]),
                f' · {biggest["caption"]}' if biggest.get("caption") else None)
              if isinstance(biggest, dict) else None)
    body = funnel_content(value, bars=bars, legend=legend, passive=True)
    return h("article", {"class_": "sl-research-card"}, headline, detail, body), "ready" if value["sessions"] else "empty"

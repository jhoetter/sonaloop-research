"""Phase 1 — the ONE renderer per primitive (spec/unified-artifact-schema-rollout.md).

Every artifact draws its content through these functions, so a Statement / Finding / Prompt / Ref / Stance
looks identical everywhere (consistency by construction). Reads the primitives produced by the adapters in
`sonaloop.artifacts`; emits HTML via the existing h()/_prose toolkit.
"""
from __future__ import annotations

import re as _re

from .. import artifacts as _A
from ._i18n import t
from ._html import h, raw, fragment, register_css
from ._components import _prose, _avatar, _label, _icon

# Co-located CSS for the §3.6 dosing affordances this renderer emits: collapsible prompt
# rounds (the banner doubles as the <summary>) and expandable verbatim quotes on a statement.
register_css(r"""
details.qround>summary{position:relative;list-style:none;cursor:pointer;display:flex;flex-direction:column;gap:12px}
details.qround>summary::-webkit-details-marker{display:none}
details.qround>summary .qround-q{padding-right:48px}
.qround-cnt{position:absolute;right:12px;top:12px;color:var(--accent);background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 8px;font-size:var(--t-xs);font-weight:600}
details.qround>summary:hover .qround-q{border-color:var(--accent)}
/* Council threading (ux-contract §10 W5): the answers indent one step under their question and
   a file-tree connector links them — a hairline spine descends from the question banner's
   underside and ELBOWS (rounded corner) into each answer card at its header line. Each card
   draws its own elbow (::before: border-left + border-bottom + a radius corner, reaching up
   through the 12px gap above); every non-last card continues the spine down its own height
   (::after), so the line runs question → card → card and ENDS curving into the last one.
   Geometry is connector drawing (not rhythm); the indent itself is the 28px token. Hairline
   var(--line) keeps it quiet in light AND dark; a one-answer round degrades to one elbow. */
.qround-a{position:relative;margin-left:28px}
.qround-a>.turn{position:relative}
.qround-a>.turn::before{content:"";position:absolute;left:-16px;top:-12px;width:15px;height:37px;
  border-left:1px solid var(--line);border-bottom:1px solid var(--line);
  border-bottom-left-radius:10px;pointer-events:none}
.qround-a>.turn:not(:last-child)::after{content:"";position:absolute;left:-16px;top:25px;bottom:-12px;
  width:1px;background:var(--line);pointer-events:none}
/* The turn TEXT is running prose (§11 T2/T4): the dense reading voice (t-md at the 1.6
   rhythm — the same body layer as the report base), wrapped at the --measure-prose reading
   width, left-aligned; the card itself keeps the structural measure. */
.turn-text{font-size:var(--t-md);line-height:1.6;max-width:var(--measure-prose)}
.turn-text p{margin:0}
.turn-quotes{margin:8px 0 0}
.turn-quotes>summary{cursor:pointer;list-style:none}
.turn-quotes>summary::-webkit-details-marker{display:none}
.turn-quotes>summary::before{content:"▸ "}
.turn-quotes[open]>summary::before{content:"▾ "}
/* Verbatim quote typography (§11 T3/T4 — the design system's prose-blockquote idiom is the
   loud Markdown callout; evidence quotes stay RESTRAINED): quiet hairline, italic body at
   t-body/1.6, and the opening „ HANGS into the gutter (negative first-line indent) so the
   quoted words stay optically aligned. */
.turn-quote{margin:8px 0 0;padding:2px 0 2px 16px;border-left:2px solid var(--line-2);font-size:var(--t-body);line-height:1.6;color:var(--muted);max-width:var(--measure-prose)}
.turn-quote p{margin:0 0 3px;font-style:italic;text-indent:-.62ch}
/* Grounding-chip lines (§10 W4): one explicit rhythm under a turn/finding — quiet faint lead
   label, consistent 4px/8px wrap spacing for the chips (the base .srcchip margin-left is the
   inline-citation idiom; inside a refs LINE the chips space themselves). */
.turn-refs{margin:12px 0 0;line-height:1.6}
.turn-refs .srcchip{margin:2px 8px 2px 0;vertical-align:middle}
.turn-refs__lbl{color:var(--faint)}
.srcchip-ts{font-family:var(--mono);font-size:var(--t-xs);color:var(--faint);margin-right:4px;white-space:nowrap}
.srcchip-mark{color:var(--faint);font-style:italic;margin-right:4px}
.claim-notice{display:flex;align-items:flex-start;gap:9px;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent;padding:4px 0 16px;margin:0 0 16px;font-size:var(--t-sm)}
/* The icon, explicit heading, role=status and aria-label carry status accessibly.  A repeated
   coloured left rail added alert-card weight without adding information on detail pages. */
.claim-notice--verified svg{color:var(--green)}.claim-notice--unverified svg{color:var(--red)}.claim-notice svg{width:16px;height:16px;flex:none;margin-top:1px}
.claim-health-body{min-width:0;display:flex;flex-direction:column;gap:6px}.claim-counts,.sl-claim-sources{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.claim-issues{margin:0;padding-left:18px}.claim-exact-refs{margin:0}.claim-exact-refs summary{cursor:pointer;color:var(--muted)}
""")


_CLAIM_COLORS = {
    "observed": "var(--green)", "memory_grounded": "var(--accent)",
    "inferred": "var(--amber)", "simulated": "var(--accent)",
    "unsupported": "var(--red)",
}


def render_claim_posture_chip(posture: str) -> str:
    """The same provenance chip on every Statement/Finding surface."""
    value = str(posture or "unsupported").strip().lower()
    labels = {
        "observed": t("claim_posture_observed"),
        "memory_grounded": t("claim_posture_memory_grounded"),
        "inferred": t("claim_posture_inferred"),
        "simulated": t("claim_posture_simulated"),
        "unsupported": t("claim_posture_unsupported"),
    }
    return _label(labels.get(value, labels["unsupported"]),
                  _CLAIM_COLORS.get(value, "var(--muted)"))


def render_claim_posture_notice(record: dict, store=None, *, passive: bool = False) -> str:
    """Canonical posture/source counts plus exact repair/evidence links.

    The envelope is server-stamped.  This renderer never upgrades trust from
    prose length or a run label; legacy records without an envelope render no
    badge rather than a guessed one.
    """
    envelope = record.get("claim_posture") or {}
    if not envelope:
        return ""
    counts = {key: int(value or 0) for key, value in (envelope.get("counts") or {}).items()}
    n = sum(counts.values())
    complete = bool(envelope.get("verified"))
    heading = t("claim_contract_verified") if complete else t("claim_contract_unverified")
    detail = t("claim_contract_detail", n=n)
    if envelope.get("prose_uncovered"):
        detail += " " + t("claim_contract_uncovered")
    count_chips = fragment(*(h("span", {"class_": "claim-count"},
                                      raw(render_claim_posture_chip(posture)), f" · {count}")
                             for posture, count in counts.items() if count))
    refs: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for claim in envelope.get("claims") or []:
        for ref in claim.get("refs") or []:
            marker = (str(ref.get("kind") or ""), str(ref.get("id") or ""),
                      str(ref.get("anchor") or ""))
            if marker not in seen:
                seen.add(marker); refs.append(ref)
    source_counts: dict[str, int] = {}
    for ref in refs:
        kind = str(ref.get("kind") or "unknown")
        source_counts[kind] = source_counts.get(kind, 0) + 1
    sources = fragment(*(raw(_label(f"{kind} · {count}", "var(--muted)"))
                         for kind, count in sorted(source_counts.items())))
    known_targets = {str(row.get("id") or "") for row in
                     [*(record.get("statements") or []), *(record.get("findings") or [])]}
    issue_links = []
    for claim in envelope.get("claims") or []:
        if claim.get("posture") != "unsupported":
            continue
        cid = str(claim.get("id") or "")
        issue_links.append(h("li", {},
            h("a", {"href": f"#{cid}"}, t("claim_issue_link")) if cid in known_targets
            else h("span", {}, t("claim_contract_unverified"))))
    exact_refs = (h("div" if passive else "details", {"class_": "sl-research-sources" if passive else "claim-exact-refs"},
                    h("p" if passive else "summary", {}, f'{t("claim_source_counts")} · {len(refs)}'),
                    h("div", {"class_": "sl-claim-sources"},
                      fragment(*(raw(render_ref(ref, store, passive=passive)) for ref in refs)))) if refs else None)
    aria = f"{heading}. {detail}"
    return h("div", {"class_": "claim-notice claim-notice--" +
                     ("verified" if complete else "unverified") + (" sl-research-claim-notice" if passive else ""),
                     "id": "claim-health", "role": "status", "aria-label": aria},
             raw(_icon("check" if complete else "warning")),
             h("div", {"class_": "claim-health-body"}, h("strong", {}, heading),
               h("div", {"class_": "muted"}, detail),
               h("div", {"class_": "claim-counts", "aria-label": detail}, count_chips),
               h("div", {"class_": "sl-claim-sources"},
                 h("span", {"class_": "muted"}, f'{t("claim_source_counts")}:'), sources)
               if source_counts else None,
               h("ul", {"class_": "claim-issues"}, fragment(*issue_links)) if issue_links else None,
               exact_refs))


def render_stance(st: dict | None, *, passive: bool = False) -> str:
    """The one stance chip — label + color resolved from the canonical VALUE via the data-driven scale
    (artifacts.stance_meta → i18n label_key). Stored label strings never pick the key: a compatibility free
    label ('mixed') is ignored, an unresolvable host token (`label_raw`) only surfaces as the tooltip.
    Passive output shows the supplied numeric value and recorded labels directly;
    it neither loads a vocabulary nor hides a compatibility label in a tooltip."""
    if not st:
        return ""
    if passive:
        return h("span", {"class_": "sl-research-badge"}, str(st.get("value", "")),
                 f' · {st["label"]}' if st.get("label") else None,
                 f' · {st["label_raw"]}' if st.get("label_raw") else None)
    meta = _A.stance_meta(st.get("value", 0))
    return _label(t(meta["label_key"]), meta["color"], title=st.get("label_raw"))


# Raw memory-ref anatomy (ux-contract §10 W4): host-authored grounding texts often open with
# the memory line's timestamp ("2026-06-11 08:45: …") and/or an "Open loop:" marker. The chip
# renders those as a quiet mono date + a localized quiet marker instead of a grey text slab.
_REF_TS = _re.compile(r"^\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2})(?::\d{2})?)?\s*[:·–—-]?\s*")
_REF_LOOP = _re.compile(r"^\s*(?:open\s+loops?|offene[rs]?\s+loops?)\s*[:·–—-]\s*", _re.I)


def _trim(text: str, n: int = 110) -> str:
    """Word-boundary trim with a real ellipsis — chip text stays scannable, the full text
    rides the tooltip."""
    s = " ".join((text or "").split())
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(" ,;:·–—-") + "…"


def _passive_ref(r: dict, *, show_role: bool) -> str:
    """Full supplied reference for a surface without tooltips or navigation."""
    address = f'{r.get("kind", "")}:{r["id"]}' if r.get("id") else ""
    if address and r.get("anchor"):
        address += f'#{r["anchor"]}'
    texts = list(dict.fromkeys(str(r[key]) for key in ("quote", "text") if r.get(key)))
    return h("span", {"class_": "sl-research-reference"},
             [h("span", {}, text) for text in texts],
             h("code", {}, address) if address else None,
             h("span", {"class_": "muted small"}, str(r["role"]).replace("_", " "))
             if show_role and r.get("role") else None)


def render_ref(r: dict, store=None, *, show_role: bool = True, passive: bool = False) -> str:
    """A cross-reference chip (spec/artifact-cross-references.md). With a `store` and a record-pointing
    Ref, it RESOLVES the addressed artifact/part LIVE — showing the current persona/title + the typed
    role + a deep-link to the part (never a stale copy); a broken ref renders honestly. Without a store
    (or for memory/observed-state/external refs) it falls back to the plain grounding chip — formatted
    quietly (§10 W4): a leading memory timestamp renders as a mono `11 Jun · 08:45` prefix, an
    "Open loop:" marker as a localized quiet label, and the body is word-trimmed with the full text
    on the tooltip. The kind→route mapping lives in the domain layer (artifacts.ref_href) so no kind
    literal is hardcoded here. `show_role=False` drops the typed-role suffix — for chip groups whose
    lead label already states the role ("Based on: …"), where the suffix would just repeat it.
    `passive=True` never resolves: full supplied text and kind:id#anchor remain visible
    when tooltips and navigation are unavailable."""
    if passive:
        return _passive_ref(r, show_role=show_role)
    role = r.get("role") if show_role else None
    rolebit = (" · " + role.replace("_", " ")) if role else ""
    if store is not None and r.get("id") and _A.ref_href(r):
        res = _A.resolve_ref(r, store)
        who = (store.get_persona(res["persona_id"]) or {}).get("display_name") if res.get("persona_id") else ""
        label = who or res.get("title") or r.get("id")
        cls = "srcchip xref" + ("" if res.get("exists") else " xref-broken")
        return h("a", {"class_": cls, "href": res["href"], "title": (res.get("text") or "")[:240]},
                 raw(_icon("link")), " ", label,
                 h("span", {"class_": "xref-role"}, rolebit) if rolebit else None)
    href = _A.ref_href(r)
    full = str(r.get("quote") or r.get("text") or r.get("id") or "")
    if href:
        return h("a", {"class_": "srcchip", "href": href, "title": full[:240]},
                 raw(_icon("link")), " ", _trim(full), rolebit or None)
    ico = "memory" if r.get("kind") == "memory" else ("compass" if r.get("kind") == "prototype_state" else "link")
    txt, ts_html, loop_html = full, None, None
    m = _REF_TS.match(txt)
    if m:
        from . import ui
        ts = (ui.local_ts(f"{m.group(1)} {m.group(2)}")
              if m.group(2) else ui.fmt_day(m.group(1)))
        ts_html = h("span", {"class_": "srcchip-ts"}, ts)
        txt = txt[m.end():]
    lm = _REF_LOOP.match(txt)
    if lm:
        loop_html = h("span", {"class_": "srcchip-mark"}, t("ref_open_loop"))
        txt = txt[lm.end():]
    return h("span", {"class_": "srcchip", "title": full[:240] if full != txt or len(full) > 110 else None},
             raw(_icon(ico)), " ", ts_html, loop_html, _trim(txt))


def _refs_line(refs: list, label: str, store=None, *, passive: bool = False) -> str:
    if not refs:
        return ""
    return h("p", {"class_": "muted small turn-refs"},
             h("span", {"class_": "turn-refs__lbl"}, label, ": "),
             fragment(*(raw(render_ref(r, store, passive=passive)) for r in refs)))


def render_prompt(p: dict, *, n: int | None = None, passive: bool = False) -> str:
    """A posed prompt. As a transcript header (question/proposal) with an optional ordinal."""
    ey = {"question": t("question"), "proposal": t("council_motion"),
          "goal": t("question"), "focus": t("question"), "hypothesis": t("council_motion")}.get(p.get("kind"), t("question"))
    label = f'{ey} {n}' if (n is not None and p.get("kind") == "question") else ey
    ico = "compass" if p.get("kind") in ("question", "goal", "focus") else "bulb"
    return h("div", {"class_": "qround-q sl-research-prompt" if passive else "qround-q"}, None if passive else raw(_icon(ico)),
             h("div", {}, h("div", {"class_": "qround-n"}, label),
               h("p", {}, raw(_prose(p.get("text", ""))))))


def _backlinks_line(st: dict, backlinks) -> str:
    """The REVERSE cross-references (spec/artifact-cross-references.md §4): who points AT this part — e.g.
    'cited by <synthesis>'. `backlinks` is {part_id: [{href, label, role}]}."""
    bl = (backlinks or {}).get(st.get("id")) if st.get("id") else None
    if not bl:
        return ""
    chips = [h("a", {"class_": "srcchip xref", "href": r["href"]}, raw(_icon("link")), " ", r.get("label") or "—",
               h("span", {"class_": "xref-role"}, " · " + r["role"].replace("_", " ")) if r.get("role") else None)
             for r in bl]
    return h("p", {"class_": "muted small turn-refs"},
             h("span", {"class_": "turn-refs__lbl"}, t("cited_by"), ": "), fragment(*chips))


def _quotes_details(refs: list, store=None) -> str:
    """Grounding refs that carry verbatim QUOTES, dosed as an expandable list (ux-contract §3.6):
    a quiet summary with the count, each quote as a small blockquote with its source chip. Refs
    without a quote keep the plain chip line (the caller appends it)."""
    return h("details", {"class_": "turn-quotes"},
             h("summary", {"class_": "muted small"}, t("n_quotes", n=len(refs))),
             fragment(*(h("blockquote", {"class_": "turn-quote"},
                          h("p", {}, f"„{r['quote']}“"), raw(render_ref(r, store)))
                        for r in refs)))


def _prepare_statement_rows(items, store=None, backlinks=None, *, show_persona=True,
                            expand_quotes=False, passive=False):
    """Resolve product-only identity/media and refs before the pure rendering core."""
    from ..ui_components.statements import StatementPresentation
    people, rows = {}, []
    for st in items:
        if not st:
            continue
        pid = st.get("persona_id", "")
        if pid not in people:
            person = store.get_persona(pid) if pid and show_persona and store is not None and not passive else None
            people[pid] = (person, raw(_avatar(person, 26)) if person else None)
        person, avatar = people[pid]
        refs = st.get("refs") or []
        quoted = [ref for ref in refs if ref.get("quote")] if expand_quotes and not passive else []
        plain = [ref for ref in refs if ref not in quoted]
        meta = st.get("meta") or {}
        grounded = (raw(_label(t("grounded_yes") if bool(meta["grounded"]) else t("grounded_no"),
                              "var(--green)" if bool(meta["grounded"]) else "var(--muted)"))
                    if "grounded" in meta else None)
        posture = raw(render_claim_posture_chip(meta["claim_posture"])) if meta.get("claim_posture") else None
        rows.append(StatementPresentation(st, persona=person, avatar=avatar,
            references=raw(_refs_line(plain, t("council_drew_on"), store, passive=passive)),
            quotes=raw(_quotes_details(quoted, store)) if quoted else None,
            backlinks=raw(_backlinks_line(st, backlinks)) if not passive else None,
            stance=raw(render_stance(st["stance"], passive=passive)) if st.get("stance") else None,
            grounded=grounded, posture=posture))
    return rows


def _statement_body(st: dict, store=None, backlinks=None, *, clamp_at: int | None = None,
                    expand_quotes: bool = False, passive: bool = False) -> str:
    from ..ui_components.statements import statement_body
    row = _prepare_statement_rows([st], store, backlinks, show_persona=False,
                                  expand_quotes=expand_quotes, passive=passive)[0]
    return statement_body(row, clamp_at=clamp_at, passive=passive)


def _persona_card(sts: list, store=None, *, head_extra=None, backlinks=None, show_persona=True,
                  clamp_at: int | None = None, expand_quotes: bool = False, passive: bool = False) -> str:
    from ..ui_components.statements import persona_card
    rows = _prepare_statement_rows(sts, store, backlinks, show_persona=show_persona,
                                   expand_quotes=expand_quotes, passive=passive)
    return persona_card(rows, head_extra=head_extra, show_persona=show_persona,
                        clamp_at=clamp_at, passive=passive)


def render_statement(st: dict, store=None, *, head_extra=None, show_persona=True,
                     clamp_at: int | None = None, expand_quotes: bool = False, passive: bool = False) -> str:
    """The existing product adapter; passive mode uses supplied values without resolution."""
    return _persona_card([st], store, head_extra=head_extra, show_persona=show_persona,
                         clamp_at=clamp_at, expand_quotes=expand_quotes, passive=passive)


def render_statements(items: list, store=None, *, group_by: str = "persona", prompts: list | None = None,
                      backlinks=None, clamp_at: int | None = None, expand_quotes: bool = False,
                      collapsible: bool = False, passive: bool = False) -> str:
    """Product-compatible adapter over one pure prompt/persona grouping renderer.

    Passive mode performs no Store/media resolution and retains complete supplied
    prose, input snapshots and reference addresses without interactive controls.
    """
    from ..ui_components.statements import render_statements as render_prepared
    rows = _prepare_statement_rows(items, store, backlinks, expand_quotes=expand_quotes, passive=passive)
    prompt_rows = prompts or []
    headers = [render_prompt(prompt, n=None if len(prompt_rows) == 1 else n, passive=passive)
               for n, prompt in enumerate(prompt_rows, 1)]
    further = h("div", {"class_": "qround-q sl-research-prompt" if passive else "qround-q"},
                None if passive else raw(_icon("bulb")),
                h("div", {}, h("div", {"class_": "qround-n"}, t("further_answers"))))
    return render_prepared(rows, group_by=group_by, prompts=prompt_rows, prompt_headers=headers,
                           further_header=further, clamp_at=clamp_at, collapsible=collapsible, passive=passive)


def render_finding(f: dict, *, n: int | None = None, store=None, passive: bool = False) -> str:
    """One authored finding — the ONE row every finding section uses (key_problem, pain_solver, cluster,
    segment, ranking, recommendation, …): a left block (prose title, optional muted detail, members,
    grounding refs) and right-aligned chips (effort·impact score + stance). Numbered → the .rec form.
    The row carries id=<part-id> so other artifacts can deep-link to this exact finding."""
    meta = f.get("meta") or {}
    score = f.get("score")
    detail = meta.get("detail")
    left = [h("strong", {}, raw(_prose(f.get("text", "")))) if detail else h("span", {}, raw(_prose(f.get("text", ""))))]
    if detail:
        left.append(h("div", {"class_": "muted small", "style": "margin-top:2px"}, raw(_prose(detail))))
    if meta.get("members"):
        left.append(h("div", {"class_": "muted small", "style": "margin-top:2px"}, "· " + ", ".join(str(m) for m in meta["members"])))
    rl = _refs_line(f.get("refs") or [], t("rel_based_on"), store, passive=passive)
    if rl:
        left.append(raw(rl))
    chips = []
    if isinstance(score, dict) and score.get("effort") and score.get("value"):
        chips.append(h("span", {"class_": "axchip"}, t("effort_value", a=score["effort"], n=score["value"])))
    if meta.get("stance"):
        chips.append(raw(render_stance(meta["stance"], passive=passive)))
    if meta.get("claim_posture"):
        chips.append(raw(render_claim_posture_chip(meta["claim_posture"])))
    num = h("span", {"class_": "recnum"}, str(n)) if n is not None else None
    body = h("div", {"class_": "fbody"}, fragment(*left))
    right = h("div", {"class_": "fchips"}, fragment(*chips)) if chips else None
    attrs = {"class_": ("rec" if n is not None else "fitem") + (" sl-research-finding" if passive else "")}
    if f.get("id"):
        attrs["id"] = f["id"]
    return h("div", attrs, num, body, right)


def render_findings(items: list, *, numbered: bool = False, store=None, passive: bool = False) -> str:
    """The rows of a finding list section (one render_finding per item). The caller wraps them in a
    section with the data-driven id (artifacts.finding_kind(kind)['id']) and an i18n label."""
    rows = [render_finding(f, n=(i if numbered else None), store=store, passive=passive) for i, f in enumerate(items, 1)]
    return fragment(*rows)

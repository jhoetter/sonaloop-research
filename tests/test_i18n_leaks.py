"""THE I18N LEAK GUARD — no hard-coded user-visible literal in the web chrome
(ticket i18n-full-coverage-and-language-switcher).

A lint-style AST scan over sonaloop/web/**: every string constant that lands in a
user-visible position must come through t() (or the docs hub's bilingual
inline-pair pattern). It fails — naming file:line and the literal — when someone
adds a hard-coded button label, page title, empty state, pill or tooltip.

WHAT COUNTS as user-visible (the scan's positive list):
  - string-constant CHILDREN of h(tag, ...) calls (including literal parts of
    f-strings), except children of h("kbd", ...) — key glyphs are not prose;
  - values of the user-visible ATTRIBUTES (title, aria-label, placeholder, alt,
    data-drawer-title, data-empty, data_label) in an h() attrs dict;
  - the text-taking arguments of the known page-builder HELPERS (_empty_state,
    _list_page, _hero, _label, ... — see _HELPER_TEXT_ARGS).

WHAT IS COVERED ELSEWHERE (pruned, not scanned into):
  - any nested call — t(...) IS the goal, h(...) scans itself, helper calls are
    scanned via _HELPER_TEXT_ARGS;
  - subscripts/comparisons/comprehensions — record data, not authored UI text;
  - `("…de…" if de else "…en…")` conditionals — the docs hub's documented
    bilingual inline-pair pattern (web/_docs.py module docstring): long prose is
    bilingual BY CONSTRUCTION there, keeping the t() table lean. The pattern is
    recognized by its conventional flag name `de`.

KNOWN LIMITS (documented, accepted):
  - literals assigned to a variable FIRST and passed later escape the scan
    (the audit cleaned these up; new builders should inline t() calls);
  - text embedded in raw JS/HTML template strings (e.g. chrome-module *_JS)
    escapes it — those modules seed their labels as JSON via t() by convention;
  - module-level word tables escape it (the calendar's day/month names now come
    from t(); don't add new ones).
A string that is genuinely NOT translatable prose (a parsed token, a key glyph)
goes into ALLOWED_LITERALS with a comment — never silently.
"""
from __future__ import annotations

import ast
import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parent.parent / "sonaloop" / "web"

# At least one real word (two letters incl. umlauts) makes a string "prose";
# separators like " · ", "—", "(", numbers and css lengths pass freely.
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")

# Attribute keys whose VALUES the user sees (tooltips, screen readers, inputs).
_VISIBLE_ATTRS = {"title", "aria-label", "placeholder", "alt",
                  "data-drawer-title", "data-empty", "data_label"}

# Page-builder helpers and WHICH of their arguments are user-visible text:
# {helper: (positional indices, keyword names)}. Extend when a new text-taking
# helper appears — the canary below (test_guard_catches_a_planted_label) only
# proves h() coverage, so helper coverage lives in this table.
_HELPER_TEXT_ARGS: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "_empty_state": ((0, 1), ()),
    "_list_page": ((), ("title", "lead", "empty_msg")),
    "_hero": ((0,), ("sub",)),
    "_label": ((0,), ("title",)),
    "_study_lead": ((1,), ("question", "qlabel")),
    "form_page": ((), ("title", "lead", "submit_label")),
    "field": ((1,), ("label", "hint")),
    "_layout": ((0,), ()),
    "render_page": ((0,), ()),
    "detail_page": ((), ("title",)),
    "_row": ((2,), ("sub",)),
    "_doc_subpage": ((2, 3), ()),
    "_docs_shell": ((1,), ()),
    "_sub_h": ((0,), ()),
}

# Exact literals that LOOK like words but are not translatable UI prose.
ALLOWED_LITERALS = {
    "PRIO ",     # re-rendering the host-AUTHORED "[PRIO n]" token (content, not chrome)
    "esc",       # a <kbd> key glyph seeded next to kbd children (palette footer)
    "Format",    # docs concept-group tag — identical word in de and en
    "rungs.",    # f"rungs.{k}" — a data-path tooltip on capability badges, not prose
    "![[fig:",   # the parsed authored figure-reference token retained by the passive report
}

_PRUNE = (ast.Call, ast.Subscript, ast.Compare, ast.comprehension)


def _is_bilingual_pair(node: ast.AST) -> bool:
    """The docs hub's `("…" if de else "…")` inline-pair pattern — both languages
    present by construction, so the literals inside are NOT leaks."""
    return (isinstance(node, ast.IfExp)
            and isinstance(node.test, ast.Name) and node.test.id == "de")


def _texts(expr: ast.AST) -> list[ast.Constant]:
    """String constants in `expr`, pruning nested calls / data lookups / pairs."""
    out: list[ast.Constant] = []

    def visit(n: ast.AST) -> None:
        if isinstance(n, _PRUNE) or _is_bilingual_pair(n):
            return
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n)
        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(expr)
    return out


def _scan_source(src: str, where: str) -> list[str]:
    offenders: list[str] = []

    def flag(c: ast.Constant, what: str) -> None:
        if c.value in ALLOWED_LITERALS or not _WORD.search(c.value):
            return
        offenders.append(f"{where}:{c.lineno}: {what}: {c.value!r}")

    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name == "h":
            tag = node.args[0] if node.args else None
            if isinstance(tag, ast.Constant) and tag.value == "kbd":
                continue
            for i, arg in enumerate(node.args):
                if i == 0:
                    continue
                if isinstance(arg, ast.Dict):
                    for k, v in zip(arg.keys, arg.values):
                        if isinstance(k, ast.Constant) and k.value in _VISIBLE_ATTRS:
                            for c in _texts(v):
                                flag(c, f"h() attr {k.value}")
                    continue
                for c in _texts(arg):
                    flag(c, "h() child")
        elif name in _HELPER_TEXT_ARGS:
            pos, kws = _HELPER_TEXT_ARGS[name]
            for i in pos:
                if i < len(node.args):
                    for c in _texts(node.args[i]):
                        flag(c, f"{name}() arg {i}")
            for kw in node.keywords:
                if kw.arg in kws:
                    for c in _texts(kw.value):
                        flag(c, f"{name}() {kw.arg}=")
    return offenders


def test_no_hardcoded_user_visible_literals_in_web_chrome():
    offenders: list[str] = []
    for path in sorted(WEB.rglob("*.py")):
        offenders += _scan_source(path.read_text(), str(path.relative_to(WEB.parent.parent)))
    assert not offenders, (
        "hard-coded user-visible literal(s) in the web chrome — route them through "
        "t() (add the key to EVERY language in web/_i18n.py), or use the docs hub's "
        "(de if de else en) pair for long doc prose:\n  " + "\n  ".join(offenders))


def test_guard_catches_a_planted_label():
    """The guard's own canary: a hard-coded button label MUST be flagged, the
    t()-routed / kbd / pair / data forms must NOT."""
    bad = 'x = h("button", {"class_": "sl-btn"}, "Save now")'
    assert _scan_source(bad, "<planted>") == ['<planted>:1: h() child: \'Save now\'']
    for ok in (
        'x = h("button", {"class_": "sl-btn"}, t("save"))',
        'x = h("kbd", {}, "esc")',
        'x = h("p", {}, "Hallo Welt" if de else "Hello world")',
        'x = h("p", {}, rec["title"])',
        'x = h("p", {}, f"{n} · {m}")',
        'x = _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="projects")',
    ):
        assert _scan_source(ok, "<planted>") == [], ok
    planted_helper = 'x = _empty_state("Nothing here", t("runtime_maybe_cleared"))'
    assert _scan_source(planted_helper, "<planted>")


# --------------------------------------------------- the visible language switcher

def test_language_switcher_in_settings_popover():
    """The sidebar settings popover carries a de/en switch with the current language
    marked active, labelled through t("language")."""
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS

    client = TestClient(web.create_app())
    html = client.get("/?lang=en").text
    pop = html.split('class="sl-um-pop"')[1].split("sl-um-trigger")[0]
    assert 'href="?lang=de"' in pop and 'href="?lang=en"' in pop
    assert STRINGS["en"]["language"] in pop
    # current language is visibly marked
    en_link = pop.split('href="?lang=en"')[0].rsplit("<a ", 1)[1]
    assert "is-active" in en_link
    de_html = client.get("/?lang=de").text
    de_pop = de_html.split('class="sl-um-pop"')[1].split("sl-um-trigger")[0]
    assert STRINGS["de"]["language"] in de_pop
    de_link = de_pop.split('href="?lang=de"')[0].rsplit("<a ", 1)[1]
    assert "is-active" in de_link


def test_explicit_lang_choice_persists_via_cookie_and_setting():
    """?lang= is the switcher's write path: it sets the ui_lang cookie (1y) and the
    persisted setting; subsequent requests keep the language with no query param."""
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.config import _read_settings

    client = TestClient(web.create_app())
    r = client.get("/?lang=de")
    assert r.cookies.get("ui_lang") == "de"
    # the persisted setting (settings.json; conftest's env override shadows
    # ui_language() itself, so assert the stored value the middleware wrote)
    assert _read_settings().get("ui_language") == "de"
    follow = client.get("/")                       # cookie rides along automatically
    assert '<html lang="de">' in follow.text

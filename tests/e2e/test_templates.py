"""E2E: compiled t-string templates in the real browser parser and kernel."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_text_and_attribute_slots(goto_feature):
    page = goto_feature("templates")
    expect(page.get_by_test_id("tpl-count")).to_have_text("Count: 0 (doubled: 0)")
    page.get_by_test_id("tpl-inc").click()
    expect(page.get_by_test_id("tpl-count")).to_have_text("Count: 1 (doubled: 2)")
    expect(page.get_by_test_id("tpl-kind")).to_have_attribute("class", "btn btn-primary")
    page.get_by_test_id("tpl-kind").click()
    expect(page.get_by_test_id("tpl-kind")).to_have_attribute("class", "btn btn-danger")


def test_whitespace_follows_jsx_rules(goto_feature):
    page = goto_feature("templates")
    text = page.get_by_test_id("tpl-whitespace").evaluate("node => node.textContent")
    assert text == "one two   three"


def test_value_binding_and_input(goto_feature):
    page = goto_feature("templates")
    expect(page.get_by_test_id("tpl-name")).to_have_value("Ada")
    page.get_by_test_id("tpl-name").fill("Grace")
    expect(page.get_by_test_id("tpl-greeting")).to_have_text("Hello, Grace!")


def test_rows_clone_inside_a_table_body(goto_feature):
    page = goto_feature("templates")
    expect(page.get_by_test_id("tpl-row")).to_have_count(3)
    page.get_by_test_id("tpl-add").click()
    expect(page.get_by_test_id("tpl-row")).to_have_count(4)
    expect(page.get_by_test_id("tpl-row").nth(3)).to_have_text("3row 3")
    page.get_by_test_id("tpl-relabel").click()
    expect(page.get_by_test_id("tpl-row").first).to_have_text("0first!")
    # The rows are real <tr> children of the <tbody> (no parser rewrites).
    assert page.get_by_test_id("tpl-body").evaluate("node => [...node.children].every(c => c.tagName === 'TR')")


def test_a_re_rendered_template_patches_in_place(goto_feature):
    page = goto_feature("templates")
    badge = page.get_by_test_id("tpl-badge")
    handle = badge.element_handle()
    page.get_by_test_id("tpl-inc").click()
    expect(badge).to_have_text("10")
    expect(badge).to_have_attribute("title", "n=1")
    assert handle.evaluate("node => node.isConnected")


def test_component_tags_and_show(goto_feature):
    page = goto_feature("templates")
    expect(page.get_by_test_id("tpl-card")).to_contain_text("Card")
    expect(page.get_by_test_id("tpl-card-child")).to_have_text("child 0")
    page.get_by_test_id("tpl-inc").click()
    expect(page.get_by_test_id("tpl-card-child")).to_have_text("child 1")
    expect(page.get_by_test_id("tpl-hidden")).to_be_visible()
    page.get_by_test_id("tpl-show").click()
    expect(page.get_by_test_id("tpl-shown")).to_be_visible()


def test_event_spellings(goto_feature):
    page = goto_feature("templates")
    for name in ("lower", "camel", "colon"):
        page.get_by_test_id(f"tpl-{name}").click()
    expect(page.get_by_test_id("tpl-heard")).to_have_text("abc")


def test_svg_expands_into_namespaced_nodes(goto_feature):
    page = goto_feature("templates")
    svg = page.get_by_test_id("tpl-svg")
    assert svg.evaluate("node => node.namespaceURI") == "http://www.w3.org/2000/svg"
    assert svg.evaluate("node => node.getAttribute('viewBox')") == "0 0 10 10"
    page.get_by_test_id("tpl-inc").click()
    assert svg.evaluate("node => node.firstElementChild.getAttribute('r')") == "1"


REARRANGED = [
    "<p><span><div>x</div></span></p>",
    "<p><em><ul><li>x</li></ul></em></p>",
    "<ul><li><div><li>x</li></div></li></ul>",
    "<dl><dd><span><dt>x</dt></span></dd></dl>",
]
KEPT = [
    "<p><button><div>x</div></button></p>",
    "<ul><li><ul><li>x</li></ul></li></ul>",
    "<dl><dd><dl><dt>x</dt></dl></dd></dl>",
]


def test_the_real_parser_rearranges_exactly_what_templates_reject(goto_feature):
    page = goto_feature("templates")
    parse = "markup => { const t = document.createElement('template'); t.innerHTML = markup; return t.innerHTML; }"
    for markup in REARRANGED:
        assert page.evaluate(parse, markup) != markup, markup
    for markup in KEPT:
        assert page.evaluate(parse, markup) == markup, markup
    run = "code => window.__WYB.pyodide.runPython(code)"
    verdicts = page.evaluate(
        run,
        """
import json
from string.templatelib import Template
from wybthon import TemplateError, html

def verdict(markup):
    try:
        html(Template(markup))
        return "accepted"
    except TemplateError:
        return "rejected"

json.dumps([verdict(m) for m in %r] + [verdict(m) for m in %r])
"""
        % (REARRANGED, KEPT),
    )
    assert verdicts == '["rejected", "rejected", "rejected", "rejected", "accepted", "accepted", "accepted"]'


def test_helper_markup_the_parser_would_rearrange_mounts_in_the_real_kernel(goto_feature):
    page = goto_feature("templates")
    markup = page.evaluate(
        "code => window.__WYB.pyodide.runPython(code)",
        """
from js import document
from wybthon import render
from wybthon.dom import Element
from wybthon.elements import div, p, span

host = document.createElement("div")
document.body.appendChild(host)
root = render(div(p(span(div("block"))), p(span(div("again")))), Element(node=host))
html_out = host.innerHTML
root.dispose()
host.remove()
html_out
""",
    )
    assert markup == "<div><p><span><div>block</div></span></p><p><span><div>again</div></span></p></div>"


def test_a_restored_event_handler_fires_in_the_real_kernel(goto_feature):
    page = goto_feature("templates")
    run = "code => window.__WYB.pyodide.runPython(code)"
    page.evaluate(
        run,
        """
from js import document
from wybthon import create_signal, event, flush, html, render
from wybthon.dom import Element
from wybthon.elements import div

_hits = []
_handlers = [
    lambda: _hits.append("first"),
    None,
    lambda: _hits.append("restored"),
    event(lambda: _hits.append("once"), once=True),
    lambda: _hits.append("plain"),
]
_mode, _set_mode = create_signal(0)
_host = document.createElement("div")
document.body.appendChild(_host)
def _view():
    return html(t'<button id="restore-btn" onclick={_handlers[_mode()]}>go</button>')

_root = render(div(_view), Element(node=_host))
""",
    )
    for mode, clicks in ((0, 1), (1, 1), (2, 1), (3, 2), (4, 2)):
        page.evaluate(run, f"_set_mode({mode}); flush()")
        for _ in range(clicks):
            page.click("#restore-btn")
    hits = page.evaluate(run, "import json; _root.dispose(); _host.remove(); json.dumps(_hits)")
    assert hits == '["first", "restored", "once", "plain", "plain"]'

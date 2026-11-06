# ruff: noqa: E501
"""Server rendering writes exactly the markup the browser's hydration expects (RFC 0006).

Each view covers markup with serialization rules of its own: controlled
selects, textareas, raw text, SVG, styles and classes, boundaries, and
flow control. The expected HTML is what the renderer before RFC 0006
produced by mounting into an in-memory DOM and serializing it, so a
change here is a change to what hydration claims.
"""

import asyncio

import pytest

from wybthon import (
    Errored,
    For,
    Fragment,
    Loading,
    Match,
    NoHydration,
    ParentProps,
    Portal,
    Repeat,
    Reveal,
    Show,
    Switch,
    client_only,
    component,
    create_memo,
    create_signal,
    create_unique_id,
    dynamic,
    h,
    html,
)
from wybthon.server import render_to_stream, render_to_string


class CardProps(ParentProps):
    title: str = ""


@component
def Card(props: CardProps):
    return html(t"<section><h3>{props.title}</h3>{props.children}</section>")


@component
def Boom():
    raise ValueError("boom")


def select_controlled():
    choice, _ = create_signal("b")
    return html(t"""<select value={choice()}>
      <option value="a">A</option><option value="b">B</option><option>c</option>
    </select>""")


def select_multiple():
    return h(
        "select",
        {"multiple": True, "selected_values": ["x", "z"]},
        h("option", {"value": "x"}, "X"),
        h("optgroup", {}, h("option", {"value": "y"}, "Y"), h("option", {"value": "z"}, "Z")),
    )


def textarea_value():
    text, _ = create_signal("\nline <b>")
    return html(t"<form><textarea value={text()}></textarea><textarea>static</textarea></form>")


def pre_newline():
    return html(t"<pre>{chr(10)}x</pre>")


def svg_markup():
    r, _ = create_signal(4)
    return html(t'<svg viewBox="0 0 10 10"><circle r={r()} cx="5" /><foreignObject><div>hi</div></foreignObject></svg>')


def styles_and_classes():
    on, _ = create_signal(True)
    return h(
        "div",
        {
            "class": {"a": on, "b": False, "c d": True},
            "style": {"background_color": "red", "margin": None, "fontSize": "2px"},
            "dataset": {"user_id": 5, "flag": True, "off": False},
            "aria_label": 'x"y',
            "hidden": False,
            "draggable": True,
            "tabindex": 0,
        },
        h("span", {"style": "color:blue;  ; width : 2px"}, "s"),
        h("span", {"class": ["e", ["f", None]], "style": "nocolon"}, "t"),
    )


def raw_text():
    return h("div", {}, h("script", {}, "if (a < b && c) {}"), h("style", {}, "a > b {}"), "x < y")


def inner_html():
    return h("div", {"inner_html": "<b>raw</b>"}, "ignored")


def inputs():
    v, _ = create_signal(None)
    return html(t'<p><input value={v()} checked={True} disabled={False} required><input type="checkbox" checked></p>')


def nested_components():
    return html(t"""<main>
      <{Card} title="One"><p>first</p>{Card(title="Two", children=["a", 1, None, True])}</{Card}>
      {Fragment("x", Fragment("y", html(t"<i>z</i>")), [1, [2, 3]])}
    </main>""")


def flow():
    items, _ = create_signal([{"id": 1, "n": "a"}, {"id": 2, "n": "b"}])
    empty, _ = create_signal([])
    mode, _ = create_signal(2)

    def row(item, i):
        return html(t"<li data-i={i()}>{item['n']}</li>")

    return html(t"""<div>
      <ul>{For(items(), row)}</ul>
      <ul>{For(empty(), row, fallback=html(t"<li>none</li>"))}</ul>
      <ol>{For(items(), lambda item, i: html(t"<li>{item()['n']}</li>"), keyed=False)}</ol>
      {Repeat(3, lambda i: html(t"<b>{i}</b>"))}
      {Show(mode() > 1, lambda: html(t"<p>big</p>"), fallback=html(t"<p>small</p>"))}
      {Show(mode() > 5, html(t"<p>never</p>"))}
      {Show(lambda: {"v": 9}, lambda v: html(t"<em>{v()['v']}</em>"), keyed=False)}
      {Switch(Match(mode() == 1, html(t"<p>one</p>")), Match(mode() == 2, html(t"<p>two</p>")), fallback="other")}
    </div>""")


def errors_and_boundaries():
    def fallback(err, reset):
        return html(t"<p class='err'>{str(err())}</p>")

    async def slow():
        return "late"

    value = create_memo(slow)
    return html(t"""<div>
      {Errored(Boom(), fallback=fallback)}
      {Errored(html(t"<span>{int('x')}</span>"), fallback=fallback)}
      {Errored(Card(title="fine"), fallback=fallback)}
      {Reveal([Loading(html(t"<b>{value()}</b>"), fallback="wait a"), Loading(html(t"<b>ok</b>"), fallback="wait b")], collapsed=True)}
      {Loading(Loading(html(t"<i>{value()}</i>"), fallback="inner"), fallback="outer")}
    </div>""")


def misc():
    tag, _ = create_signal("h2")
    return html(t"""<div id={create_unique_id()}>
      {NoHydration(html(t"<p>static</p>"))}
      {client_only(lambda: html(t"<p>client</p>"), fallback=html(t"<p>server</p>"))}
      {Portal(html(t"<p>portal</p>"))}
      {dynamic(tag)(children=["dyn"])}
      {(lambda: None)}{(lambda: True)}{(lambda: "")}{(lambda: 0)}{(lambda: 1.5)}
      {(lambda: [html(t"<b>a</b>"), "b"])}
      text &amp; {"<esc>"} more
    </div>""")


def content_props():
    markup, _ = create_signal("<b>raw</b>")
    attrs = {"inner_html": "<i>spread</i>", "class": "s"}
    plain = {"id": "p", "data-x": 1}
    return html(t"""<div>
      <section inner_html={markup()}><p>hidden</p></section>
      <article {attrs}><p>hidden too</p></article>
      <aside {plain}><p>shown</p></aside>
      <input {plain} value={markup()}>
    </div>""")


@component
def Raises():
    raise RuntimeError("fallback broke")


def late_errors():
    # The `Loading` fallback raises while the boundary resolves, after the
    # `Errored` content rendered: the boundary still shows its fallback.
    async def slow():
        return "data"

    value = create_memo(slow)

    def failed(err, reset):
        return html(t"<p class='late'>{str(err())}</p>")

    return html(t"""<div>
      {Errored(Loading(html(t"<b>{value()}</b>"), fallback=lambda: Raises()), fallback=failed)}
      <i>after</i>
    </div>""")


EXPECTED = {
    "select_controlled string": '<select><option value="a">A</option><option value="b" selected>B</option><option>c</option></select><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "select_controlled await": '<select><option value="a">A</option><option value="b" selected>B</option><option>c</option></select><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "select_multiple string": '<select multiple><option value="x" selected>X</option><optgroup><option value="y">Y</option><option value="z" selected>Z</option></optgroup></select><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "select_multiple await": '<select multiple><option value="x" selected>X</option><optgroup><option value="y">Y</option><option value="z" selected>Z</option></optgroup></select><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "textarea_value string": '<form><textarea>\n\nline &lt;b&gt;</textarea><textarea>static</textarea></form><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "textarea_value await": '<form><textarea>\n\nline &lt;b&gt;</textarea><textarea>static</textarea></form><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "pre_newline string": '<pre>\n\nx</pre><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "pre_newline await": '<pre>\n\nx</pre><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "svg_markup string": '<svg viewBox="0 0 10 10"><circle r="4" cx="5"></circle><foreignObject><div>hi</div></foreignObject></svg><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "svg_markup await": '<svg viewBox="0 0 10 10"><circle r="4" cx="5"></circle><foreignObject><div>hi</div></foreignObject></svg><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "styles_and_classes string": '<div class="a c d" data-user-id="5" data-flag aria-label="x&quot;y" draggable="true" tabindex="0" style="background-color: red; font-size: 2px"><span style="color: blue; width: 2px">s</span><span class="e f">t</span></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "styles_and_classes await": '<div class="a c d" data-user-id="5" data-flag aria-label="x&quot;y" draggable="true" tabindex="0" style="background-color: red; font-size: 2px"><span style="color: blue; width: 2px">s</span><span class="e f">t</span></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "raw_text string": '<div><script>if (a < b && c) {}</script><style>a > b {}</style>x &lt; y</div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "raw_text await": '<div><script>if (a < b && c) {}</script><style>a > b {}</style>x &lt; y</div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "inner_html string": '<div><b>raw</b></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "inner_html await": '<div><b>raw</b></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "inputs string": '<p><input required checked><input type="checkbox" checked></p><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "inputs await": '<p><input required checked><input type="checkbox" checked></p><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "nested_components string": '<main><section><h3>One</h3><!----><p>first</p><section><h3>Two</h3><!---->a1<!----><!----></section><!----><!----></section>xy<i>z</i>123</main><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "nested_components await": '<main><section><h3>One</h3><!----><p>first</p><section><h3>Two</h3><!---->a1<!----><!----></section><!----><!----></section>xy<i>z</i>123</main><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "flow string": '<div><ul><!----><li data-i="0">a</li><li data-i="1">b</li><!----></ul><ul><!----><li>none</li><!----></ul><ol><!----><li>a</li><li>b</li><!----></ol><!----><b>0</b><b>1</b><b>2</b><!----><!----><p>big</p><!----><!----><!----><!----><em>9</em><!----><!----><p>two</p><!----></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "flow await": '<div><ul><!----><li data-i="0">a</li><li data-i="1">b</li><!----></ul><ul><!----><li>none</li><!----></ul><ol><!----><li>a</li><li>b</li><!----></ol><!----><b>0</b><b>1</b><b>2</b><!----><!----><p>big</p><!----><!----><!----><!----><em>9</em><!----><!----><p>two</p><!----></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "errors_and_boundaries string": '<div><p class="err">boom</p><!----><p class="err">invalid literal for int() with base 10: \'x\'</p><!----><section><h3>fine</h3><!----></section><!----><!----><!--wyb:be02472af1a21-->wait a<!----><!--/wyb:be02472af1a21--><!--wyb:b170e769adff8--><!----><!--/wyb:b170e769adff8--><!----><!--wyb:b93aefde66d5e--><!--wyb:b5f5f3d3889a3-->inner<!----><!--/wyb:b5f5f3d3889a3--><!----><!----><!--/wyb:b93aefde66d5e--></div><script type="application/json" data-wyb-state>{"v":{},"x":{"297f12eeb351":["ValueError","boom"],"d900e2c45550":["ValueError","invalid literal for int() with base 10: \'x\'"]}}</script>',
    "errors_and_boundaries await": '<div><p class="err">boom</p><!----><p class="err">invalid literal for int() with base 10: \'x\'</p><!----><section><h3>fine</h3><!----></section><!----><!----><!--wyb:be02472af1a21--><b>late</b><!----><!----><!--/wyb:be02472af1a21--><!--wyb:b170e769adff8--><b>ok</b><!----><!----><!--/wyb:b170e769adff8--><!----><!--wyb:b93aefde66d5e--><!--wyb:b5f5f3d3889a3--><i>late</i><!----><!----><!--/wyb:b5f5f3d3889a3--><!----><!----><!--/wyb:b93aefde66d5e--></div><script type="application/json" data-wyb-state>{"v":{},"x":{"297f12eeb351":["ValueError","boom"],"d900e2c45550":["ValueError","invalid literal for int() with base 10: \'x\'"]}}</script>',
    "misc string": '<div id="wyb-hcf3241877926"><!--wyb:nh--><p>static</p><!--/wyb:nh--><!----><p>server</p><!----><h2>dyn</h2><!----><!----><!----><!---->01.5<!----><b>a</b>b<!----><!---->text &amp; &lt;esc&gt; more</div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "misc await": '<div id="wyb-hcf3241877926"><!--wyb:nh--><p>static</p><!--/wyb:nh--><!----><p>server</p><!----><h2>dyn</h2><!----><!----><!----><!---->01.5<!----><b>a</b>b<!----><!---->text &amp; &lt;esc&gt; more</div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "content_props string": '<div><section><b>raw</b></section><article class="s"><i>spread</i></article><aside id="p" data-x="1"><p>shown</p></aside><input id="p" data-x="1" value="&lt;b&gt;raw&lt;/b&gt;"></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "content_props await": '<div><section><b>raw</b></section><article class="s"><i>spread</i></article><aside id="p" data-x="1"><p>shown</p></aside><input id="p" data-x="1" value="&lt;b&gt;raw&lt;/b&gt;"></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
    "late_errors string": '<div><p class="late">fallback broke</p><!----><i>after</i></div><script type="application/json" data-wyb-state>{"v":{},"x":{"297f12eeb351":["RuntimeError","fallback broke"]}}</script>',
    "late_errors await": '<div><!--wyb:ba613e30b4b73--><b>data</b><!----><!----><!--/wyb:ba613e30b4b73--><!----><i>after</i></div><script type="application/json" data-wyb-state>{"v":{}}</script>',
}

VIEWS = {name.split()[0]: globals()[name.split()[0]] for name in EXPECTED}


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_server_output_is_what_hydration_claims(case):
    name, mode = case.split()
    view = VIEWS[name]
    if mode == "string":
        html = render_to_string(view)
    else:

        async def complete():
            return await render_to_stream(view, timeout=1)

        html = asyncio.run(complete())
    assert html == EXPECTED[case]

"""Compiled t-string templates (`html`, RFC 0003)."""

from typing import Any

import pytest

from wybthon import (
    Errored,
    For,
    Loading,
    ParentProps,
    Prop,
    Props,
    Show,
    TemplateError,
    component,
    create_memo,
    create_signal,
    diagnostics,
    div,
    event,
    flush,
    html,
    kernel,
    span,
    templates,
)
from wybthon.testing import cleanup, fire, render


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


def ops_during(fn: Any) -> dict[str, int]:
    """Kernel op counts emitted (and committed) while `fn` runs."""
    with diagnostics.profile() as prof:
        fn()
        flush()
        kernel.commit()
    return {k: v for k, v in prof.counts.items() if k.startswith("op_")}


CLONE = f"op_{kernel.OP_CLONE}"
DISPOSE = f"op_{kernel.OP_DISPOSE}"


# ---------------------------------------------------------------------------
# Compilation and caching
# ---------------------------------------------------------------------------


def test_a_literal_compiles_once():
    def row(label: str) -> Any:
        return html(t"<li class='row'>{label}</li>")

    a, b = row("a"), row("b")
    assert a.props is b.props
    assert a.children == ("a",) and b.children == ("b",)


def test_requires_a_t_string():
    with pytest.raises(TypeError, match="t-string"):
        html("<p>nope</p>")


def test_static_markup_renders():
    screen = render(html(t'<section id="s"><h1 class="title">Hi &amp; bye</h1><br><input disabled></section>'))
    assert screen.html() == '<section id="s"><h1 class="title">Hi &amp; bye</h1><br><input disabled=""></section>'


def test_whitespace_follows_jsx_rules():
    view = html(t"""
        <ul>
            <li>  one
                two  </li>
            <li>{"x"} y</li>
        </ul>
    """)
    screen = render(view)
    assert screen.html() == "<ul><li>  one two  </li><li>x y</li></ul>"


def test_pre_keeps_text_verbatim():
    screen = render(html(t"<pre>a\n  b\n</pre>"))
    assert screen.html() == "<pre>a\n  b\n</pre>"


def test_comments_are_dropped():
    screen = render(html(t"<p>a<!-- hidden -->b</p>"))
    assert screen.html() == "<p>ab</p>"


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: html(t"<div><span></div>"), "doesn't match"),
        (lambda: html(t"<div>"), "Unclosed tag"),
        (lambda: html(t"</div>"), "Unexpected closing tag"),
        (lambda: html(t"<table><tr><td>x</td></tr></table>"), "add a <tbody>"),
        (lambda: html(t"<p><div>x</div></p>"), "inside <p>"),
        (lambda: html(t"<a><span><a>x</a></span></a>"), "nested inside another <a>"),
        (lambda: html(t"<ul><li><li>x</li></li></ul>"), "direct child"),
        (lambda: html(t"<style>{'x'}</style>"), "static text only"),
        (lambda: html(t"<tbody>text</tbody>"), "can't contain text"),
        (lambda: html(t"<!doctype html>"), "Doctypes"),
        (lambda: html(t"<div onclick='a{'b'}'></div>"), "single interpolation"),
    ],
)
def test_malformed_or_rewritten_markup_is_rejected(make, message):
    with pytest.raises(TemplateError, match=message):
        make()


def test_errors_name_the_template():
    with pytest.raises(TemplateError, match=r"in template: t'<b>\{\.\.\.\}</i>'"):
        html(t"<b>{1}</i>")


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


def test_child_slots_take_text_nodes_lists_and_none():
    screen = render(html(t"<div>{'text'}|{span('node')}|{[span('a'), 'b']}|{None}|{42}</div>"))
    assert screen.html() == "<div>text|<span>node</span>|<span>a</span>b||42</div>"


def test_reactive_child_and_attribute_slots_update():
    count, set_count = create_signal(1)
    cls, set_cls = create_signal("a")
    screen = render(html(t"<p class={cls}>n={count}</p>"))
    assert screen.html() == '<p class="a">n=1</p>'
    set_count(2)
    set_cls("b")
    flush()
    assert screen.html() == '<p class="b">n=2</p>'


def test_a_text_hole_fills_its_slot_in_the_clone_command():
    label, set_label = create_signal("x")
    counts = ops_during(lambda: render(html(t"<li><b>{label}</b></li>")))
    assert counts[CLONE] == 1
    assert counts.get(f"op_{kernel.OP_HOLE_TEXT}", 0) == 0
    assert counts.get(DISPOSE, 0) == 0


def test_partial_attributes_render_as_one_binding():
    kind, set_kind = create_signal("primary")
    screen = render(html(t'<button class="btn btn-{kind} {"wide"}">go</button>'))
    assert screen.html() == '<button class="btn btn-primary wide">go</button>'
    set_kind("danger")
    flush()
    assert screen.html() == '<button class="btn btn-danger wide">go</button>'


def test_events_in_every_spelling_bind_delegated_handlers():
    hits: list[str] = []
    view = html(
        t"""<div>
            <button onclick={(lambda: hits.append("lower"))}>a</button>
            <button onClick={(lambda e: hits.append(e.type))}>b</button>
            <button on:click={(lambda: hits.append("colon"))}>c</button>
        </div>"""
    )
    screen = render(view)
    for name in ("a", "b", "c"):
        fire.click(screen.get_by_text(name))
    assert hits == ["lower", "click", "colon"]


def test_event_options_use_a_direct_listener_and_fire_once():
    hits: list[int] = []
    screen = render(html(t"<button onclick={event(lambda: hits.append(1), once=True)}>x</button>"))
    button = screen.get_by_text("x")
    fire.click(button)
    fire.click(button)
    assert hits == [1]


def test_refs_and_spreads():
    seen: list[Any] = []
    attrs = {"id": "field", "aria_label": "Name", "on_input": lambda e: seen.append(e.target.value)}
    screen = render(html(t'<form><input type="text" {attrs} ref={seen.append}></form>'))
    node = screen.get_by_label_text("Name")
    assert node.attributes["id"] == "field"
    assert len(seen) == 1
    fire.input(node, "Ada")
    assert seen[-1] == "Ada"


def test_conversion_and_format_specs_apply():
    price, set_price = create_signal(3.14159)
    screen = render(html(t"<p>{price:.2f} {'x'!r}</p>"))
    assert screen.text() == "3.14 'x'"
    set_price(2.5)
    flush()
    assert screen.text() == "2.50 'x'"


def test_multiple_roots_and_text_only_templates_make_fragments():
    name, set_name = create_signal("Ada")
    screen = render(div(html(t"<b>a</b><i>b</i>"), html(t"Hello, {name}!")))
    assert screen.html() == "<div><b>a</b><i>b</i>Hello, Ada!</div>"
    set_name("Grace")
    flush()
    assert screen.text() == "abHello, Grace!"


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


class CardProps(ParentProps):
    title: Prop[str]
    tone: str = "plain"


@component
def Card(props: CardProps):
    return html(t'<section class="card {props.tone}"><h2>{props.title}</h2>{props.children}</section>')


def test_component_tags_pass_attributes_and_children():
    count, set_count = create_signal(1)
    screen = render(
        html(
            t"""<main>
                <{Card} title="Hi" tone="loud"><p>body {count}</p></{Card}>
                <{Card} title={count} />
            </main>"""
        )
    )
    assert screen.html() == (
        '<main><section class="card loud"><h2>Hi</h2><p>body 1</p></section>'
        '<section class="card plain"><h2>1</h2></section></main>'
    )
    set_count(2)
    flush()
    assert screen.text() == "Hibody 22"


def test_component_tag_content_is_one_child_per_top_level_node():
    from wybthon import children

    seen: list[int] = []

    @component
    def Counted(props: ParentProps):
        resolved = children(lambda: props.children())
        seen.append(len(resolved.to_array()))
        return html(t"<div>{props.children}</div>")

    screen = render(html(t"<main><{Counted}><b>a</b><i>b</i>text</{Counted}></main>"))
    assert seen == [3]
    assert screen.html() == "<main><div><b>a</b><i>b</i>text</div></main>"


def test_component_tags_validate_props_in_dev_mode():
    with pytest.raises(TypeError, match="unexpected prop"):
        render(html(t"<div><{Card} title='x' bogus='y' /></div>"))


def test_interpolated_component_calls_mount_in_place():
    screen = render(html(t"<div>{Card(title='a')}<hr>{Card(title='b')}</div>"))
    assert screen.text() == "ab"


def test_a_non_component_tag_is_an_error():
    with pytest.raises(TemplateError, match="needs a component"):
        render(html(t"<div><{'span'} /></div>"))


# ---------------------------------------------------------------------------
# Control flow and boundaries
# ---------------------------------------------------------------------------


def test_rows_mount_with_one_clone_command_each():
    items, set_items = create_signal([{"id": i, "label": f"r{i}"} for i in range(5)])
    view = html(t"<ul>{For(items, lambda item, i: html(t'<li data-id={item["id"]}>{item["label"]}</li>'))}</ul>")
    screen = render(view)
    counts = ops_during(lambda: set_items(lambda xs: [*xs, *({"id": 10 + i, "label": "x"} for i in range(3))]))
    assert counts[CLONE] == 3
    assert len(screen.get_all_by_text("x")) == 3
    counts = ops_during(lambda: set_items([]))
    assert counts == {f"op_{kernel.OP_DISPOSE_RANGE}": 1}
    assert screen.html() == "<ul></ul>"


def test_show_switches_between_templates():
    on, set_on = create_signal(False)
    screen = render(html(t"<div>{Show(on, html(t'<b>yes</b>'), html(t'<i>no</i>'))}</div>"))
    assert screen.html() == "<div><i>no</i></div>"
    set_on(True)
    flush()
    assert screen.html() == "<div><b>yes</b></div>"


def test_errored_catches_a_failing_slot():
    def boom() -> str:
        raise ValueError("nope")

    screen = render(Errored(html(t"<p>{boom}</p>"), fallback=lambda err: html(t"<em>{(lambda: str(err()))}</em>")))
    assert screen.text() == "nope"


def test_loading_holds_a_template_until_data_arrives():
    import asyncio

    gate = asyncio.Event()

    async def load() -> str:
        await gate.wait()
        return "data"

    async def main() -> None:
        @component
        def View():
            value = create_memo(load)
            return Loading(html(t"<p>{value}</p>"), fallback=html(t"<i>wait</i>"))

        screen = render(View())
        flush()
        assert screen.text() == "wait"
        gate.set()
        for _ in range(5):
            await asyncio.sleep(0)
            flush()
        assert screen.text() == "data"

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Re-rendering: slot-wise patching
# ---------------------------------------------------------------------------


def test_a_re_rendered_template_patches_only_changed_slots():
    n, set_n = create_signal(1)
    static = span("static")
    screen = render(div(lambda: html(t"<p title={n()}>{n() * 10}{static}</p>")))
    p = screen.container.childNodes[0].childNodes[0]
    counts = ops_during(lambda: set_n(2))
    assert screen.container.childNodes[0].childNodes[0] is p
    assert screen.html() == '<div><p title="2">20<span>static</span></p></div>'
    # The number's slot is followed by another slot, so its anchor is a comment
    # the first text replaced; later text is a write to that node.
    assert counts == {f"op_{kernel.OP_SET_ATTR}": 1, f"op_{kernel.OP_HOLE_TEXT}": 1}


def test_a_different_literal_replaces_the_instance():
    on, set_on = create_signal(True)
    screen = render(div(lambda: html(t"<b>a</b>") if on() else html(t"<i>b</i>")))
    set_on(False)
    flush()
    assert screen.html() == "<div><i>b</i></div>"


def test_patching_a_component_slot_keeps_its_state():
    n, set_n = create_signal("a")
    mounts: list[int] = []

    class LeafProps(Props):
        label: Prop[str]

    @component
    def Leaf(props: LeafProps):
        mounts.append(1)
        return html(t"<b>{props.label}</b>")

    screen = render(div(lambda: html(t"<p><{Leaf} label={n()} /></p>")))
    set_n("b")
    flush()
    assert screen.text() == "b"
    assert mounts == [1]


def test_child_slot_switches_between_text_nodes_and_holes():
    mode, set_mode = create_signal(0)
    count, set_count = create_signal(1)
    values = ["text", span("node"), count, None]
    screen = render(div(lambda: html(t"<p>{values[mode()]}</p>")))
    seen = []
    for m in range(4):
        set_mode(m)
        flush()
        seen.append(screen.html())
    set_mode(2)
    flush()
    set_count(5)
    flush()
    assert seen == [
        "<div><p>text</p></div>",
        "<div><p><span>node</span></p></div>",
        "<div><p>1</p></div>",
        "<div><p></p></div>",
    ]
    assert screen.text() == "5"


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


def test_unmount_releases_handlers_refs_and_bindings():
    from wybthon import _dom_props, events

    cls, _ = create_signal("x")
    rows, set_rows = create_signal(list(range(20)))
    refs: list[Any] = []

    def row(r: int, i: Any) -> Any:
        return html(t"<li class={cls} onclick={(lambda: None)} ref={refs.append}>{r}</li>")

    view = html(t"<ul>{For(rows, row)}</ul>")
    handlers_before = len(events._handlers)
    bindings_before = len(_dom_props._bindings)
    refs_before = len(_dom_props._ref_cleanups)
    render(view)
    assert len(events._handlers) == handlers_before + 20
    set_rows([])
    flush()
    assert len(events._handlers) == handlers_before
    assert len(_dom_props._bindings) == bindings_before
    assert len(_dom_props._ref_cleanups) == refs_before


def test_generated_mount_functions_are_inspectable():
    templates._debug_sources = []
    try:
        render(html(t"<p class={(lambda: 'x')}>{'a'}</p>"))
        assert templates._debug_sources
        assert "prop_slot" in templates._debug_sources[-1]
    finally:
        templates._debug_sources = None


# ---------------------------------------------------------------------------
# Server rendering and hydration
# ---------------------------------------------------------------------------


@component
def Counter():
    count, set_count = create_signal(3)

    def increment() -> None:
        set_count(lambda n: n + 1)

    return html(t'<div class="counter"><p>Count: {count}!</p><button onclick={increment}>+</button></div>')


def test_server_rendering_matches_the_element_helpers(wyb):
    from test_ssr import strip_state

    from wybthon.server import render_to_string

    from_template = strip_state(render_to_string(html(t'<div class="a"><{Card} title="T">x</{Card}>{[1, 2]}</div>')))
    from_helpers = strip_state(render_to_string(div(Card(title="T")["x"], [1, 2], class_="a")))
    assert from_template == from_helpers
    assert from_template.startswith('<div class="a"><section class="card plain"><h2>T</h2>')


def test_hydration_adopts_template_markup(wyb):
    from test_ssr import find, hydrate_from, visible

    from wybthon.server import render_to_string

    html_out = render_to_string(Counter())
    result = hydrate_from(wyb, html_out, Counter())
    assert result.mismatches == 0
    assert result.created_elements == []
    result.backend.dispatch("click", find(result.container, "button"))
    flush()
    assert visible(result.container) == "Count: 4!+"


def test_svg_templates_expand_into_namespaced_nodes():
    screen = render(html(t'<svg viewBox="0 0 10 10"><circle r={5} /></svg>'))
    svg = screen.container.childNodes[0]
    assert svg.attributes.get("xmlns") == "http://www.w3.org/2000/svg"
    assert svg.childNodes[0].attributes["r"] == "5"


def test_built_in_factories_work_as_component_tags():
    from wybthon import Errored, create_context, use_context
    from wybthon.router import Link

    on, set_on = create_signal(True)
    Theme = create_context("light")

    @component
    def Themed():
        return html(t"<i>{use_context(Theme)}</i>")

    def broken():
        raise ValueError("nope")

    screen = render(
        html(
            t"""<div>
                  <{Show} when={on} fallback={html(t"<b>off</b>")}><b>on</b></{Show}>
                  <{Theme} value="dark"><{Themed} /></{Theme}>
                  <{Errored} fallback="failed"><p>{broken}</p></{Errored}>
                  <{Link} href="/docs" class="nav">Docs</{Link}>
                </div>"""
        )
    )
    assert screen.text() == "ondarkfailedDocs"
    link = screen.get_by_text("Docs")
    assert link.attributes["href"] == "/docs"
    assert link.attributes["class"] == "nav"
    set_on(False)
    flush()
    assert screen.text() == "offdarkfailedDocs"


def test_an_action_is_a_handler_with_or_without_the_event():
    from wybthon import action

    calls: list[str] = []

    @action
    def save() -> None:
        calls.append("save")

    @action
    def typed(e: Any) -> None:
        calls.append(e.type)

    screen = render(html(t"<div><button onclick={save}>a</button><button onclick={typed}>b</button></div>"))
    fire.click(screen.get_by_text("a"))
    fire.click(screen.get_by_text("b"))
    assert calls == ["save", "click"]

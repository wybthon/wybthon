"""Compiled t-string templates (`html`, RFC 0003 and RFC 0004)."""

from string.templatelib import Interpolation, Template
from typing import Any

import pytest

import wybthon
from wybthon import (
    Errored,
    For,
    Loading,
    ParentProps,
    Props,
    Show,
    TemplateError,
    compiler,
    component,
    create_memo,
    create_signal,
    diagnostics,
    event,
    flush,
    h,
    html,
    kernel,
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


def uncompiled(source: str, **names: Any) -> Any:
    """Evaluate Python source the compiler never sees: its templates compile at run time."""
    return eval(source, {"html": html, **names})


def load_module(source: str, filename: str = "mod.py") -> dict[str, Any]:
    """Compile a module's source with `wybthon.compiler` and run it; returns its namespace."""
    namespace: dict[str, Any] = {"__name__": filename.removesuffix(".py")}
    exec(compiler.compile_source(source, filename), namespace)
    return namespace


# ---------------------------------------------------------------------------
# Compilation and caching
# ---------------------------------------------------------------------------


def test_a_literal_compiles_once():
    def row(label: str) -> Any:
        return html(t"<li class='row'>{label}</li>")

    a, b = row("a"), row("b")
    assert a.props is b.props
    assert a.children == ("a",) and b.children == ("b",)


def test_an_uncompiled_literal_compiles_once_and_is_cached_by_identity():
    namespace: dict[str, Any] = {}
    exec("from wybthon import html\ndef row(label):\n    return html(t'<li>{label}</li>')\n", namespace)
    before = set(templates._by_identity)
    a, b = namespace["row"]("a"), namespace["row"]("b")
    added = [templates._by_identity[k] for k in set(templates._by_identity) - before]
    assert [entry.strings for entry in added] == [("<li>", "</li>")]
    assert a.props is b.props
    assert a.children == ("a",) and b.children == ("b",)
    assert render(a).html() == "<li>a</li>"


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


# Malformed templates are compile-time errors in a compiled module, so these
# are evaluated without the compiler, where `html()` raises at run time.
@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("""html(t"<div><span></div>")""", "doesn't match"),
        ("""html(t"<div>")""", "Unclosed tag"),
        ("""html(t"</div>")""", "Unexpected closing tag"),
        ("""html(t"<table><tr><td>x</td></tr></table>")""", "add a <tbody>"),
        ("""html(t"<p><div>x</div></p>")""", "inside <p>"),
        ("""html(t"<a><span><a>x</a></span></a>")""", "nested inside another <a>"),
        ("""html(t"<ul><li><li>x</li></li></ul>")""", "direct child"),
        ("""html(t"<style>{'x'}</style>")""", "static text only"),
        ("""html(t"<tbody>text</tbody>")""", "can't contain text"),
        ("""html(t"<!doctype html>")""", "Doctypes"),
        ("""html(t"<div onclick='a{'b'}'></div>")""", "single interpolation"),
    ],
)
def test_malformed_or_rewritten_markup_is_rejected(source, message):
    with pytest.raises(TemplateError, match=message):
        uncompiled(source)


def test_errors_name_the_template():
    with pytest.raises(TemplateError, match=r"in template: t'<b>\{\.\.\.\}</i>'"):
        html(Template("<b>", Interpolation(1, "1"), "</i>"))


def test_the_compiler_reports_a_malformed_template_with_its_file_and_line():
    with pytest.raises(SyntaxError, match="doesn't match") as info:
        load_module('from wybthon import html\n\nview = html(t"<div><span></div>")\n', "broken.py")
    assert (info.value.filename, info.value.lineno) == ("broken.py", 3)


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------


def test_child_slots_take_text_nodes_lists_and_none():
    screen = render(
        html(t"<div>{'text'}|{html(t'<span>node</span>')}|{[html(t'<span>a</span>'), 'b']}|{None}|{42}</div>")
    )
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


def test_dynamic_expressions_are_reactive_in_every_position():
    count, set_count = create_signal(1)
    active, set_active = create_signal(False)
    price, set_price = create_signal(1.5)
    screen = render(
        html(
            t"""<div class={"on" if active() else "off"} data-n="n{count() + 1}">
                  <p>{count() * 2}</p><b>{price():.2f}</b><{Card} title={str(count())} /><i>{str(count() + 10)}</i>
                </div>"""
        )
    )
    assert screen.html() == (
        '<div class="off" data-n="n2"><p>2</p><b>1.50</b>'
        '<section class="card plain"><h2>1</h2></section><i>11</i></div>'
    )
    set_count(3)
    set_active(True)
    set_price(2.25)
    flush()
    assert screen.html() == (
        '<div class="on" data-n="n4"><p>6</p><b>2.25</b><section class="card plain"><h2>3</h2></section><i>13</i></div>'
    )


def test_a_template_in_a_hole_updates_its_bindings_without_re_running():
    n, set_n = create_signal(1)
    runs: list[int] = []

    def view() -> Any:
        runs.append(1)
        return html(t"<p title={n()}>{n() * 10}</p>")

    screen = render(html(t"<div>{view}</div>"))
    set_n(2)
    flush()
    assert screen.html() == '<div><p title="2">20</p></div>'
    assert runs == [1]


def test_a_template_made_in_a_loop_sees_that_iterations_values():
    labels = ["a", "b", "c"]
    views = []
    for i in range(3):
        views.append(html(t"<i>{labels[i].upper()}</i>"))
    screen = render(html(t"<p>{views}</p>"))
    assert screen.text() == "ABC"


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
    screen = render(html(t"<p>{price:.2f} {'x'!r} {price()!r}</p>"))
    assert screen.text() == "3.14 'x' 3.14159"
    set_price(2.5)
    flush()
    assert screen.text() == "2.50 'x' 2.5"


def test_multiple_roots_and_text_only_templates_make_fragments():
    name, set_name = create_signal("Ada")
    screen = render(html(t"<div>{html(t'<b>a</b><i>b</i>')}{html(t'Hello, {name}!')}</div>"))
    assert screen.html() == "<div><b>a</b><i>b</i>Hello, Ada!</div>"
    set_name("Grace")
    flush()
    assert screen.text() == "abHello, Grace!"


# ---------------------------------------------------------------------------
# The dev-mode check of uncompiled templates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        """html(t"<p>{count() * 2}</p>")""",
        """html(t"<p class={'on' if count() else 'off'}>x</p>")""",
        """html(t"<p class='n-{count()}'>x</p>")""",
        """html(t"<p>{count():>3}</p>")""",
    ],
)
def test_an_uncompiled_dynamic_expression_evaluated_once_is_an_error(source):
    count, _ = create_signal(1)
    with pytest.raises(TemplateError, match=r"was evaluated once instead of becoming reactive"):
        uncompiled(source, count=count)


def test_the_uncompiled_error_names_the_expression():
    count, _ = create_signal(1)
    with pytest.raises(TemplateError, match=r"\{count\(\) \* 2\}"):
        uncompiled("""html(t"<p>{count() * 2}</p>")""", count=count)


def test_an_uncompiled_dynamic_expression_that_returns_a_callable_is_accepted():
    count, set_count = create_signal(1)
    accessors = {"count": count}
    screen = render(uncompiled("""html(t"<p>{accessors['count']}</p>")""", accessors=accessors))
    set_count(2)
    flush()
    assert screen.text() == "2"


def test_uncompiled_handlers_refs_spreads_and_tags_are_not_checked():
    hits: list[str] = []
    handlers: dict[str, Any] = {"click": None}
    refs: dict[str, Any] = {}
    cards = [Card]

    def attrs() -> dict[str, str]:
        return {"id": "b"}

    view = uncompiled(
        """html(t"<div><button onclick={handlers.get('click')} ref={refs.get('button')} {attrs()}>x</button>"""
        """<{cards[0]} title='t' /></div>")""",
        handlers=handlers,
        refs=refs,
        attrs=attrs,
        cards=cards,
    )
    screen = render(view)
    fire.click(screen.get_by_text("x"))
    assert hits == []
    assert screen.get_by_text("x").attributes["id"] == "b"
    assert screen.text() == "xt"


def test_the_uncompiled_check_is_skipped_outside_dev_mode():
    count, set_count = create_signal(1)
    wybthon.set_dev_mode(False)
    try:
        view = uncompiled("""html(t"<p>{count() * 2}</p>")""", count=count)
    finally:
        wybthon.set_dev_mode(True)
    screen = render(view)
    set_count(5)
    flush()
    # Evaluated once: an uncompiled template doesn't defer its expressions.
    assert screen.text() == "2"


# ---------------------------------------------------------------------------
# Precompiled entries
# ---------------------------------------------------------------------------

PRECOMPILED_MODULE = """
from wybthon import create_signal, html

count, set_count = create_signal(1)


def row(label):
    return html(t"<li class={label}>{label}: {count() * 2}</li>")
"""


def test_precompiled_templates_mount_with_one_clone_each_and_never_parse():
    namespace = load_module(PRECOMPILED_MODULE)
    entry = namespace["__wybthon_t0__"]
    assert isinstance(entry, templates.Precompiled)
    identities = set(templates._by_identity)
    screens: list[Any] = []
    for label in ("a", "b", "c"):
        counts = ops_during(lambda label=label: screens.append(render(namespace["row"](label))))
        assert counts[CLONE] == 1
    assert set(templates._by_identity) == identities
    assert entry.strings not in templates._by_value
    assert entry.entry is not None and entry.entry.eager == ()
    assert [s.html() for s in screens] == [f'<li class="{x}">{x}: 2</li>' for x in "abc"]
    namespace["set_count"](5)
    flush()
    assert [s.text() for s in screens] == ["a: 10", "b: 10", "c: 10"]


def test_a_compiled_template_builds_no_t_string_and_never_calls_html():
    namespace = load_module(PRECOMPILED_MODULE)

    def fail(template: Any) -> Any:
        raise AssertionError("a compiled template called html()")

    namespace["html"] = fail
    with render(namespace["row"]("a")) as screen:
        assert screen.html() == '<li class="a">a: 2</li>'


def test_a_precompiled_entry_loads_once():
    entry = load_module(PRECOMPILED_MODULE)["__wybthon_t0__"]
    fresh = templates.Precompiled(entry.strings, entry.data, entry.factories, tuple(entry.probes))
    first = fresh.render(("a", "a", lambda: 2))
    assert fresh.entry is not None and fresh.element is first.props
    assert fresh.render(("b", "b", lambda: 4)).props is first.props


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


class CardProps(ParentProps):
    title: str
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
        resolved = children(lambda: props.children)
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


def test_interpolated_component_calls_receive_getters_for_dynamic_arguments():
    name, set_name = create_signal("a")
    mounts: list[int] = []

    @component
    def Leaf(props: CardProps):
        mounts.append(1)
        return html(t"<b>{props.title}</b>")

    screen = render(html(t"<div>{Leaf(title=name().upper())}</div>"))
    set_name("b")
    flush()
    assert screen.text() == "B"
    assert mounts == [1]


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


def test_show_takes_a_dynamic_condition():
    count, set_count = create_signal(1)
    screen = render(html(t"<div>{Show(count() > 2, html(t'<b>big</b>'), html(t'<i>small</i>'))}</div>"))
    assert screen.html() == "<div><i>small</i></div>"
    set_count(3)
    flush()
    assert screen.html() == "<div><b>big</b></div>"


def test_errored_catches_a_failing_slot():
    def boom() -> str:
        raise ValueError("nope")

    screen = render(Errored(html(t"<p>{boom}</p>"), fallback=lambda err: html(t"<em>{str(err())}</em>")))
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
#
# A hole re-renders a template when the hole itself reads a signal; the
# template's own interpolations are static here, so each re-render brings
# new values for the same literal.
# ---------------------------------------------------------------------------


def test_a_re_rendered_template_patches_only_changed_slots():
    n, set_n = create_signal(1)
    static = html(t"<span>static</span>")

    def view() -> Any:
        value = n()
        return html(t"<p title={value}>{value * 10}{static}</p>")

    screen = render(html(t"<div>{view}</div>"))
    p = screen.container.childNodes[0].childNodes[0]
    counts = ops_during(lambda: set_n(2))
    assert screen.container.childNodes[0].childNodes[0] is p
    assert screen.html() == '<div><p title="2">20<span>static</span></p></div>'
    # The number's slot is followed by another slot, so its anchor is a comment
    # the first text replaced; later text is a write to that node.
    assert counts == {f"op_{kernel.OP_SET_ATTR}": 1, f"op_{kernel.OP_HOLE_TEXT}": 1}


def test_a_different_literal_replaces_the_instance():
    on, set_on = create_signal(True)
    screen = render(html(t"<div>{html(t'<b>a</b>') if on() else html(t'<i>b</i>')}</div>"))
    assert screen.html() == "<div><b>a</b></div>"
    set_on(False)
    flush()
    assert screen.html() == "<div><i>b</i></div>"


def test_patching_a_component_slot_keeps_its_state():
    n, set_n = create_signal("a")
    mounts: list[int] = []

    class LeafProps(Props):
        label: str

    @component
    def Leaf(props: LeafProps):
        mounts.append(1)
        return html(t"<b>{props.label}</b>")

    def view() -> Any:
        label = n()
        return html(t"<p><{Leaf} label={label} /></p>")

    screen = render(html(t"<div>{view}</div>"))
    set_n("b")
    flush()
    assert screen.text() == "b"
    assert mounts == [1]


SWITCHED = [
    "<div><p>text</p></div>",
    "<div><p><span>node</span></p></div>",
    "<div><p>1</p></div>",
    "<div><p></p></div>",
]


def test_child_slot_switches_between_text_nodes_and_holes():
    mode, set_mode = create_signal(0)
    count, set_count = create_signal(1)
    values = ["text", html(t"<span>node</span>"), count, None]

    def view() -> Any:
        value = values[mode()]
        return html(t"<p>{value}</p>")

    screen = render(html(t"<div>{view}</div>"))
    seen = []
    for m in range(4):
        set_mode(m)
        flush()
        seen.append(screen.html())
    set_mode(2)
    flush()
    set_count(5)
    flush()
    assert seen == SWITCHED
    assert screen.text() == "5"


def test_a_reactive_child_switches_between_text_nodes_and_holes():
    mode, set_mode = create_signal(0)
    count, set_count = create_signal(1)
    values = ["text", html(t"<span>node</span>"), count, None]
    screen = render(html(t"<div><p>{values[mode()]}</p></div>"))
    seen = []
    for m in range(4):
        set_mode(m)
        flush()
        seen.append(screen.html())
    set_mode(2)
    flush()
    set_count(5)
    flush()
    assert seen == SWITCHED
    assert screen.text() == "5"


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


def test_unmount_releases_handlers_refs_and_bindings():
    from wybthon import _dom_props, events

    def handler_count() -> int:
        return sum(len(tuple(events.handlers_of(entry))) for entry in events._handlers.values())

    cls, _ = create_signal("x")
    rows, set_rows = create_signal(list(range(20)))
    refs: list[Any] = []

    def row(r: int, i: Any) -> Any:
        return html(t"<li class={cls} onclick={(lambda: None)} ref={refs.append}>{r}</li>")

    view = html(t"<ul>{For(rows, row)}</ul>")
    handlers_before = handler_count()
    bindings_before = len(_dom_props._bindings)
    refs_before = len(_dom_props._ref_cleanups)
    render(view)
    assert handler_count() == handlers_before + 20
    set_rows([])
    flush()
    assert handler_count() == handlers_before
    assert len(_dom_props._bindings) == bindings_before
    assert len(_dom_props._ref_cleanups) == refs_before


def test_generated_mount_functions_are_inspectable():
    # Precompiled templates carry their mount functions in the module, so the
    # template is compiled at run time here.
    templates._debug_sources = []
    try:
        render(uncompiled("""html(t"<p class={(lambda: 'x')}>{'a'}</p>")"""))
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


def test_server_rendering_matches_h(wyb):
    from test_ssr import strip_state

    from wybthon.server import render_to_string

    from_template = strip_state(render_to_string(html(t'<div class="a"><{Card} title="T">x</{Card}>{[1, 2]}</div>')))
    from_h = strip_state(render_to_string(h("div", {"class_": "a"}, Card(title="T")["x"], [1, 2])))
    assert from_template == from_h
    assert from_template.startswith('<div class="a"><section class="card plain"><h2>T</h2>')


def test_server_rendering_evaluates_dynamic_expressions(wyb):
    from test_ssr import strip_state

    from wybthon.server import render_to_string

    count, _ = create_signal(2)
    out = strip_state(render_to_string(html(t"<p class={'n' + str(count())}>{count() * 2}</p>")))
    assert out.startswith('<p class="n2">4')


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
    from wybthon import create_context, use_context
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


# ---------------------------------------------------------------------------
# Review regressions (PR #40)
#
# Handlers are never deferred, so a hole that reads the mode re-renders the
# template with a new handler each time.
# ---------------------------------------------------------------------------


def test_an_event_handler_restored_after_none_fires_again():
    hits: list[str] = []
    handlers = [lambda: hits.append("first"), None, lambda: hits.append("restored")]
    mode, set_mode = create_signal(0)

    def view() -> Any:
        return html(t"<button onclick={handlers[mode()]}>go</button>")

    screen = render(html(t"<div>{view}</div>"))
    for m in range(3):
        set_mode(m)
        flush()
        fire.click(screen.get_by_text("go"))
    assert hits == ["first", "restored"]


def test_a_spent_once_handler_can_be_replaced_by_a_plain_one():
    hits: list[str] = []
    handlers = [event(lambda: hits.append("once"), once=True), lambda: hits.append("plain")]
    mode, set_mode = create_signal(0)

    def view() -> Any:
        return html(t"<button onclick={handlers[mode()]}>go</button>")

    screen = render(html(t"<div>{view}</div>"))
    fire.click(screen.get_by_text("go"))
    set_mode(1)
    flush()
    fire.click(screen.get_by_text("go"))
    fire.click(screen.get_by_text("go"))
    assert hits == ["once", "plain", "plain"]


def test_a_plain_handler_can_become_a_capture_handler_and_back():
    hits: list[str] = []
    handlers = [lambda: hits.append("plain"), event(lambda: hits.append("capture"), capture=True)]
    mode, set_mode = create_signal(0)

    def view() -> Any:
        return html(t"<button onclick={handlers[mode()]}>go</button>")

    screen = render(html(t"<div>{view}</div>"))
    button = screen.get_by_text("go")
    fire.click(button)
    set_mode(1)
    flush()
    backend = kernel._backend
    assert (button_id := next(i for i, n in backend._nodes.items() if n is button))
    assert (button_id, "click:capture") in backend._listener_options
    set_mode(0)
    flush()
    fire.click(button)
    assert hits == ["plain", "plain"]


def test_identical_markup_with_different_format_specs_formats_each():
    price = 3.14159
    first = render(html(t"<p>{price}</p>"))
    second = render(html(t"<p>{price:.2f}</p>"))
    third = render(html(t"<p>{price!r:>10}</p>"))
    assert first.text() == "3.14159"
    assert second.text() == "3.14"
    assert third.html() == "<p>   3.14159</p>"


def test_literals_sharing_one_strings_tuple_keep_their_own_formats():
    def views(x: float) -> tuple[Any, Any]:
        return html(t"<i>{x}</i>"), html(t"<i>{x:.1f}</i>")

    a, b = views(2.25)
    assert render(a).text() == "2.25"
    assert render(b).text() == "2.2"


@pytest.mark.parametrize(
    "source",
    [
        """html(t"<p><span><div>{42}</div></span></p>")""",
        """html(t"<p><em><b><ul><li>x</li></ul></b></em></p>")""",
        """html(t"<p><span><table><tbody></tbody></table></span></p>")""",
    ],
)
def test_a_block_anywhere_inside_a_p_is_rejected(source):
    with pytest.raises(TemplateError, match="inside <p>"):
        uncompiled(source)


def test_list_items_and_definitions_close_through_inline_and_div_elements():
    with pytest.raises(TemplateError, match="another <li>"):
        uncompiled("""html(t"<ul><li><div><li>x</li></div></li></ul>")""")
    with pytest.raises(TemplateError, match="unless a <dl>"):
        uncompiled("""html(t"<dl><dd><span><dt>x</dt></span></dd></dl>")""")


def test_scope_boundaries_and_nested_lists_are_accepted():
    screen = render(
        html(
            t"""<div>
                  <p><button><div>in button</div></button></p>
                  <ul><li><ul><li>nested</li></ul></li></ul>
                  <dl><dd><dl><dt>inner</dt></dl></dd></dl>
                </div>"""
        )
    )
    assert screen.text() == "in buttonnestedinner"


def test_h_markup_the_parser_would_rearrange_mounts_per_node():
    # `h()` builds DOM nodes directly, so markup a template would reject
    # (block content in a <p>, nested <a>) mounts node by node.
    with diagnostics.profile() as prof:
        screen = render(
            h(
                "div",
                None,
                h("p", None, h("span", None, h("div", None, "block"))),
                h("a", {"href": "#o"}, h("span", None, h("a", {"href": "#i"}, "inner"))),
            )
        )
        kernel.commit()
    assert prof.counts[f"op_{kernel.OP_CREATE_ELEMENT}"] >= 2
    assert (
        screen.html()
        == '<div><p><span><div>block</div></span></p><a href="#o"><span><a href="#i">inner</a></span></a></div>'
    )

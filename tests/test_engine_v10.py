"""Engine v10 (RFC 0011): parameters as props, and lazy flow-control branches."""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Callable
from typing import Any

import pytest

from wybthon import (
    Children,
    Errored,
    For,
    Loading,
    Match,
    Show,
    Switch,
    component,
    create_signal,
    flush,
    html,
    is_static,
    lazy,
)
from wybthon.compiler import compile_source, transform
from wybthon.testing import render


def compiled(source: str) -> str:
    source = textwrap.dedent(source)
    return ast.unparse(transform(ast.parse(source), "m.py", source))


# ---------------------------------------------------------------------------
# Parameters are props
# ---------------------------------------------------------------------------


def test_the_body_reads_props_and_the_signature_is_kept():
    out = compiled(
        """
        from wybthon import component, html

        @component
        def Card(title: str, body: str = ""):
            '''A card.'''
            return html(t"<p>{title}{body}</p>")
        """
    )
    assert "def Card(__wybthon_props0__, /):" in out
    assert "lambda: __wybthon_props0__.title" in out
    assert "@__wybthon__.props(Card)\ndef Card(title: str, body: str='')" in out


def test_a_component_without_parameters_is_left_alone():
    out = compiled(
        """
        from wybthon import component, html

        @component
        def Plain():
            return html(t"<p>x</p>")
        """
    )
    assert "__wybthon_props" not in out


def test_the_decorator_is_recognized_by_alias_and_through_the_package():
    out = compiled(
        """
        import wybthon as w
        from wybthon import component as comp

        @comp
        def A(x: int):
            return x

        @w.component
        def B(y: int):
            return y
        """
    )
    assert "return __wybthon_props0__.x" in out
    assert "return __wybthon_props1__.y" in out


def test_a_function_that_is_not_a_component_is_left_alone():
    out = compiled(
        """
        from wybthon import component, html

        def row(title):
            return html(t"<p>{title}</p>")
        """
    )
    assert "__wybthon_props" not in out


def test_components_nested_in_components_read_their_own_props():
    @component
    def Outer(label: str):
        @component
        def Inner(label: str, suffix: str = "?"):
            return html(t"<i>{label}{suffix}</i>")

        def inner_label() -> str:
            return label.upper()

        return html(t"<p>{label}:{Inner(label=inner_label())}</p>")

    name, set_name = create_signal("a")
    with render(html(t"<div><{Outer} label={name()} /></div>")) as screen:
        assert screen.text() == "a:A?"
        set_name("b")
        flush()
        assert screen.text() == "b:B?"


def test_a_handler_reads_the_latest_prop():
    seen: list[str] = []

    @component
    def Button(label: str):
        def click() -> None:
            seen.append(label)

        return html(t"<button onclick={click}>go</button>")

    name, set_name = create_signal("first")
    from wybthon.testing import fire

    with render(html(t"<{Button} label={name()} />")) as screen:
        fire.click(screen.get_by_text("go"))
        set_name("second")
        flush()
        fire.click(screen.get_by_text("go"))
    assert seen == ["first", "second"]


def test_a_prop_passed_through_stays_reactive():
    @component
    def Leaf(text: str):
        return html(t"<b>{text}</b>")

    @component
    def Middle(text: str, children: Children = None):
        return html(t"<span><{Leaf} text={text} />{children}</span>")

    name, set_name = create_signal("x")
    with render(html(t"<{Middle} text={name()}><i>kid</i></{Middle}>")) as screen:
        assert screen.text() == "xkid"
        set_name("y")
        flush()
        assert screen.text() == "ykid"


def test_is_static_asks_about_the_parameter():
    reports: list[tuple[bool, bool]] = []

    @component
    def Probe(a: str, b: str = ""):
        reports.append((is_static(a), is_static(b)))
        return html(t"<i></i>")

    value, _ = create_signal("v")
    with render(html(t'<div><{Probe} a="x" b={value()} /></div>')):
        pass
    assert reports == [(True, False)]
    with pytest.raises(TypeError, match="compiled component"):
        is_static("plain value")


def test_a_rest_parameter_follows_new_values_from_a_rerendering_parent():
    title, set_title = create_signal("one")

    @component
    def Box(**attrs: Any):
        return html(t"<div {attrs}></div>")

    def view() -> Any:
        return Box(id="b", title=title())

    with render(html(t"<section>{view()}</section>")) as screen:
        assert screen.html() == '<section><div id="b" title="one"></div></section>'
        set_title("two")
        flush()
        assert screen.html() == '<section><div id="b" title="two"></div></section>'


def test_a_rest_parameter_does_not_swallow_key():
    @component
    def Box(**attrs: Any):
        return html(t"<div {attrs}></div>")

    with pytest.raises(TypeError, match="components take no key"):
        Box(id="b", key="k")


def test_handlers_on_a_component_tag_reach_callbacks_and_rest_spreads():
    from wybthon.testing import fire

    clicks: list[str] = []

    @component
    def Button(label: str, **attrs: Any):
        return html(t"<button {attrs}>{label}</button>")

    @component
    def Confirm(on_confirm: Callable[[], None]):
        return html(t"<button onclick={on_confirm}>ok</button>")

    def save() -> None:
        clicks.append("save")

    def confirm() -> None:
        clicks.append("confirm")

    view = html(t"<div><{Button} label='Save' onclick={save} /><{Confirm} onconfirm={confirm} /></div>")
    with render(view) as screen:
        fire.click(screen.get_by_text("Save"))
        fire.click(screen.get_by_text("ok"))
        assert "onclick" not in screen.html()
    assert clicks == ["save", "confirm"]


def test_an_async_component_body_is_rejected_at_its_first_render_like_any_other():
    # Components aren't coroutines; the compiler keeps `async def` as written.
    out = compiled(
        """
        from wybthon import component

        @component
        async def Bad(x: int):
            return x
        """
    )
    assert "async def Bad(__wybthon_props0__, /):" in out


# ---------------------------------------------------------------------------
# Lazy branches
# ---------------------------------------------------------------------------


def test_hidden_show_content_is_never_built():
    built: list[str] = []

    @component
    def Panel(name: str):
        built.append(name)
        return html(t"<p>{name}</p>")

    open_, set_open = create_signal(False)
    with render(html(t"<div>{Show(open_(), Panel(name='content'), fallback=Panel(name='fallback'))}</div>")) as screen:
        assert screen.text() == "fallback"
        assert built == ["fallback"]
        set_open(True)
        flush()
        assert screen.text() == "content"
        assert built == ["fallback", "content"]


def test_markup_content_is_built_each_time_the_branch_shows():
    calls: list[int] = []

    def count() -> int:
        calls.append(1)
        return len(calls)

    open_, set_open = create_signal(False)
    with render(html(t"<div>{Show(open_(), html(t'<p>shown {count()}</p>'))}</div>")) as screen:
        assert screen.text() == ""
        assert calls == []
        set_open(True)
        flush()
        assert screen.text() == "shown 1"
        set_open(False)
        flush()
        set_open(True)
        flush()
        assert screen.text() == "shown 2"


def test_content_components_still_receive_getters():
    value, set_value = create_signal(1)

    @component
    def Value(n: int):
        return html(t"<p>{n}</p>")

    with render(html(t"<div>{Show(True, Value(n=value() * 10))}</div>")) as screen:
        assert screen.text() == "10"
        set_value(2)
        flush()
        assert screen.text() == "20"


def test_switch_matches_and_fallback_are_lazy():
    built: list[str] = []

    @component
    def Mark(name: str):
        built.append(name)
        return html(t"<b>{name}</b>")

    status, set_status = create_signal("a")
    view = html(
        t"""<div>{
            Switch(
                Match(status() == "a", Mark(name="a")),
                Match(status() == "b", Mark(name="b")),
                fallback=Mark(name="none"),
            )
        }</div>"""
    )
    with render(view) as screen:
        assert screen.text() == "a"
        assert built == ["a"]
        set_status("c")
        flush()
        assert screen.text() == "none"
        assert built == ["a", "none"]


def test_errored_and_loading_content_is_built_inside_the_boundary():
    @component
    def Broken():
        raise ValueError("boom")

    def failed(err: Any, reset: Callable[[], None]) -> Any:
        return html(t"<p>caught {str(err())}</p>")

    view = html(t"<div>{Errored(Loading(Broken(), fallback=html(t'<p>wait</p>')), fallback=failed)}</div>")
    with render(view) as screen:
        assert screen.text() == "caught boom"


def test_lazy_content_in_a_loop_sees_its_own_iteration():
    def views() -> list[Any]:
        out = []
        for label in ("a", "b"):
            out.append(Show(True, html(t"<i>{label}</i>")))
        return out

    with render(html(t"<p>{views()}</p>")) as screen:
        assert screen.text() == "ab"


def test_python_code_outside_templates_is_lazy_too():
    built: list[str] = []

    @component
    def Mark(name: str):
        built.append(name)
        return html(t"<b>{name}</b>")

    view = Show(False, Mark(name="hidden"), fallback=Mark(name="shown"))
    assert built == []
    with render(view) as screen:
        assert screen.text() == "shown"
    assert built == ["shown"]


def test_callbacks_and_names_are_passed_as_they_are():
    out = compiled(
        """
        from wybthon import Show, html

        def view(user, greeting, fallback):
            return Show(user, greeting, fallback=fallback)
        """
    )
    assert "Show(user, greeting, fallback=fallback)" in out


def test_a_lowercase_call_in_content_is_left_eager():
    # It may return a callback, which the flow control would call with its value.
    out = compiled(
        """
        from wybthon import Show

        def view(user, make_row):
            return Show(user, make_row("kind"))
        """
    )
    assert "Show(user, make_row('kind'))" in out


# ---------------------------------------------------------------------------
# Routes take the route props they declare
# ---------------------------------------------------------------------------


def test_a_lazy_route_component_receives_only_what_it_declares():
    from wybthon.router import Route, create_router

    @component
    def Page(params: dict[str, str]):
        return html(t"<p>page {params['id']}</p>")

    @component
    def Home():
        return html(t"<p>home</p>")

    lazy_page = lazy(lambda: Page)
    router = create_router([Route("/", Home), Route("/p/:id", lazy_page)])
    from wybthon.router import navigate

    with render(router()) as screen:
        navigate("/p/5")
        flush()
        assert "page 5" in screen.text()


def test_the_compiled_module_runs_under_the_import_hook_cache_tag():
    from wybthon import _hook

    assert _hook.COMPILER_TAG == "wyb4"
    assert _hook.is_candidate(b"from wybthon import component\n")
    assert _hook.is_candidate(b"from wybthon import Show\n")
    assert not _hook.is_candidate(b"import wybthon\n")
    code = compile_source("from wybthon import component\n\n@component\ndef A(x: int):\n    return x\n", "m.py")
    namespace: dict[str, Any] = {}
    exec(code, namespace)
    assert namespace["A"].signature.__wybthon_body__ is namespace["A"].fn


def test_for_rows_are_unaffected():
    items, set_items = create_signal(["a"])
    with render(html(t"<ul>{For(items(), lambda item, i: html(t'<li>{item}</li>'))}</ul>")) as screen:
        set_items(["a", "b"])
        flush()
        assert screen.text() == "ab"

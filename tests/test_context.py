from typing import Any

import pytest
from conftest import collect_texts

from wybthon import html
from wybthon.component import component
from wybthon.context import Context, ContextNotFoundError, create_context, use_context
from wybthon.flow import Show
from wybthon.reactivity import Props, create_signal, flush, prop


def texts(node):
    return [t for t in collect_texts(node) if t and t.strip()]


def test_provider_value_is_read_by_descendant_component(wyb, root_element):
    Theme = create_context()

    @component
    def Child():
        theme = use_context(Theme)
        return html(t"<p>{theme}</p>")

    root = wyb["reconciler"].render(Theme("dark", html(t"<div>{Child()}</div>")), root_element)
    assert texts(root_element.element) == ["dark"]
    root.dispose()


def test_default_value_when_no_provider(wyb, root_element):
    Theme = create_context("light")

    @component
    def Child():
        return html(t"<p>{use_context(Theme)}</p>")

    root = wyb["reconciler"].render(Child(), root_element)
    assert texts(root_element.element) == ["light"]
    root.dispose()


def test_use_context_without_provider_or_default_raises(wyb):
    Theme = create_context(name="Theme")
    assert not Theme.has_default
    with pytest.raises(ContextNotFoundError) as info:
        use_context(Theme)
    assert "Theme" in str(info.value)
    assert issubclass(ContextNotFoundError, LookupError)


def test_nested_providers_shadow_outer_value(wyb, root_element):
    Theme = create_context("light")

    class ChildProps(Props):
        label: str = prop(default="")

    @component
    def Child(props: ChildProps):
        theme = use_context(Theme)
        return html(t"<span>{props.label}={theme}</span>")

    view = html(t"""<div>
        {Child(label="a")}
        {Theme("inner", Child(label="b"))}
        {Child(label="c")}
    </div>""")
    root = wyb["reconciler"].render(Theme("outer", view), root_element)
    assert texts(root_element.element) == ["a", "=", "outer", "b", "=", "inner", "c", "=", "outer"]
    root.dispose()


def test_accessor_value_stays_live(wyb, root_element):
    Theme = create_context()
    theme, set_theme = create_signal("light")

    @component
    def Child():
        t = use_context(Theme)
        return html(t"<p>theme:{t()}</p>")

    root = wyb["reconciler"].render(Theme(theme, Child()), root_element)
    assert texts(root_element.element) == ["theme:", "light"]
    set_theme("dark")
    flush()
    assert texts(root_element.element) == ["theme:", "dark"]
    root.dispose()


def test_provider_value_visible_inside_show_subtree(wyb, root_element):
    Theme = create_context("fallback")
    visible, set_visible = create_signal(False)

    @component
    def Child():
        return html(t"<p>{use_context(Theme)}</p>")

    root = wyb["reconciler"].render(Theme("provided", Show(visible, lambda: Child())), root_element)
    assert texts(root_element.element) == []
    set_visible(True)
    flush()
    assert texts(root_element.element) == ["provided"]
    root.dispose()


def test_use_context_inside_hole(wyb, root_element):
    Theme = create_context()
    root = wyb["reconciler"].render(Theme("hole-value", html(t"<div>{use_context(Theme)}</div>")), root_element)
    assert texts(root_element.element) == ["hole-value"]
    root.dispose()


def test_context_name_repr_and_identity(wyb):
    named = create_context(name="Theme")
    anonymous = create_context()
    assert isinstance(named, Context)
    assert named.name == "Theme"
    assert repr(named) == "Context(Theme)"
    assert repr(anonymous).startswith("Context(")
    assert anonymous.name is None
    assert named != anonymous
    assert len({named, anonymous}) == 2


def test_provider_children_by_item_syntax_and_reactive_context_prop(wyb, root_element):
    Theme = create_context("light")
    theme, set_theme = create_signal("dark")

    class LabelProps(Props):
        prefix: str

    @component
    def Label(props: LabelProps):
        current = use_context(Theme)
        return html(t"<p>{f'{props.prefix}:{current() if callable(current) else current}'}</p>")

    labels = [Label(prefix="a"), Label(prefix="b")]
    root = wyb["reconciler"].render(Theme(theme, html(t"<div>{labels}</div>")), root_element)
    assert texts(root_element.element) == ["a:dark", "b:dark"]
    set_theme("light")
    flush()
    assert texts(root_element.element) == ["a:light", "b:light"]
    root.dispose()


# ---------------------------------------------------------------------------
# Providers in templates
# ---------------------------------------------------------------------------


def test_provider_in_a_template_evaluates_a_getter_value_once(wyb, root_element):
    # `Theme(theme(), ...)` is dynamic, so the compiler passes a getter; the
    # provider evaluates it once, untracked, and stores the plain value.
    Theme = create_context("none")
    theme, set_theme = create_signal("light")
    seen: list[Any] = []

    @component
    def Child():
        value = use_context(Theme)
        seen.append(value)
        return html(t"<p>{value}</p>")

    wyb["reconciler"].render(html(t"<div>{Theme(theme(), Child())}</div>"), root_element)
    assert seen == ["light"]
    assert texts(root_element.element) == ["light"]
    set_theme("dark")
    flush()
    # The provided value was a snapshot: no re-render, no new value.
    assert seen == ["light"]
    assert texts(root_element.element) == ["light"]


def test_provider_in_a_template_keeps_an_accessor_value(wyb, root_element):
    # `Theme(theme, ...)` passes the signal itself: it stays an accessor.
    Theme = create_context()
    theme, set_theme = create_signal("light")
    seen: list[Any] = []

    @component
    def Child():
        value = use_context(Theme)
        seen.append(value)
        return html(t"<p>{value()}</p>")

    wyb["reconciler"].render(html(t"<div>{Theme(theme, Child())}</div>"), root_element)
    assert seen == [theme]
    assert texts(root_element.element) == ["light"]
    set_theme("dark")
    flush()
    assert texts(root_element.element) == ["dark"]
    assert len(seen) == 1


def test_provider_in_a_template_scopes_every_child(wyb, root_element):
    Theme = create_context("light")

    @component
    def Child():
        return html(t"<i>{use_context(Theme)}</i>")

    view = html(t"<div>{Theme('dark', Child(), html(t'<b>{use_context(Theme)}</b>'))}</div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["dark", "dark"]


def test_provider_as_a_component_tag(wyb, root_element):
    Theme = create_context("light")
    theme, set_theme = create_signal("dark")
    view = html(t"<div><{Theme} value={theme}><p>{use_context(Theme)()}</p></{Theme}></div>")
    wyb["reconciler"].render(view, root_element)
    assert texts(root_element.element) == ["dark"]
    set_theme("dim")
    flush()
    assert texts(root_element.element) == ["dim"]

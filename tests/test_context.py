import pytest
from conftest import collect_texts

from wybthon.component import component
from wybthon.context import Context, ContextNotFoundError, create_context, use_context
from wybthon.flow import Show
from wybthon.html import div, p, span
from wybthon.reactivity import create_signal, flush


def texts(node):
    return [t for t in collect_texts(node) if t]


def test_provider_value_is_read_by_descendant_component(wyb, root_element):
    Theme = create_context()

    @component
    def Child():
        theme = use_context(Theme)
        return p(theme)

    root = wyb["reconciler"].render(Theme("dark", div(Child())), root_element)
    assert texts(root_element.element) == ["dark"]
    root.dispose()


def test_default_value_when_no_provider(wyb, root_element):
    Theme = create_context("light")

    @component
    def Child():
        return p(use_context(Theme))

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

    @component
    def Child(label=""):
        return span(label, "=", use_context(Theme))

    root = wyb["reconciler"].render(
        Theme("outer", div(Child(label="a"), Theme("inner", Child(label="b")), Child(label="c"))),
        root_element,
    )
    assert texts(root_element.element) == ["a", "=", "outer", "b", "=", "inner", "c", "=", "outer"]
    root.dispose()


def test_accessor_value_stays_live(wyb, root_element):
    Theme = create_context()
    theme, set_theme = create_signal("light")

    @component
    def Child():
        t = use_context(Theme)
        return p(lambda: f"theme:{t()}")

    root = wyb["reconciler"].render(Theme(theme, Child()), root_element)
    assert texts(root_element.element) == ["theme:light"]
    set_theme("dark")
    flush()
    assert texts(root_element.element) == ["theme:dark"]
    root.dispose()


def test_provider_value_visible_inside_show_subtree(wyb, root_element):
    Theme = create_context("fallback")
    visible, set_visible = create_signal(False)

    @component
    def Child():
        return p(use_context(Theme))

    root = wyb["reconciler"].render(Theme("provided", Show(visible, lambda: Child())), root_element)
    assert texts(root_element.element) == []
    set_visible(True)
    flush()
    assert texts(root_element.element) == ["provided"]
    root.dispose()


def test_use_context_inside_hole(wyb, root_element):
    Theme = create_context()
    root = wyb["reconciler"].render(Theme("hole-value", div(lambda: use_context(Theme))), root_element)
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

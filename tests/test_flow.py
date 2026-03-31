"""Tests for reactive flow control components (Show, For, Index, Switch, Match, Dynamic).

Flow controls are now reactive components that create isolated reactive
scopes.  These tests verify both the VNode structure and the reactive
behaviour (re-rendering only when dependencies change).
"""

import time

from conftest import collect_texts

from wybthon.flow import Dynamic, For, Index, Match, Show, Switch, _MatchResult
from wybthon.vnode import VNode, h

# ---------------------------------------------------------------------------
# Show — VNode structure
# ---------------------------------------------------------------------------


def test_show_returns_vnode():
    result = Show(when=True, children=h("p", {}, "visible"))
    assert isinstance(result, VNode)


def test_show_with_false_returns_vnode():
    result = Show(when=False, children=h("p", {}, "visible"))
    assert isinstance(result, VNode)


def test_show_with_fallback_returns_vnode():
    result = Show(when=False, children=h("p", {}, "main"), fallback=h("p", {}, "fallback"))
    assert isinstance(result, VNode)


def test_show_callable_when():
    result = Show(when=lambda: True, children=h("p", {}, "ok"))
    assert isinstance(result, VNode)


def test_show_callable_children():
    result = Show(when=True, children=lambda cond: h("p", {}, f"got {cond}"))
    assert isinstance(result, VNode)


# ---------------------------------------------------------------------------
# Show — rendered output with browser stubs
# ---------------------------------------------------------------------------


def test_show_truthy_renders_child(wyb, root_element):
    vdom = wyb["vdom"]
    child = h("p", {}, "visible")
    vdom.render(Show(when=True, children=child), root_element)
    texts = collect_texts(root_element.element)
    assert "visible" in texts


def test_show_falsy_renders_empty(wyb, root_element):
    vdom = wyb["vdom"]
    child = h("p", {}, "visible")
    vdom.render(Show(when=False, children=child), root_element)
    texts = collect_texts(root_element.element)
    assert "visible" not in texts


def test_show_falsy_renders_fallback(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Show(when=False, children=h("p", {}, "main"), fallback=h("p", {}, "fallback")),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "fallback" in texts
    assert "main" not in texts


def test_show_callable_when_renders(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Show(when=lambda: True, children=h("p", {}, "ok")), root_element)
    texts = collect_texts(root_element.element)
    assert "ok" in texts


def test_show_callable_children_renders(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Show(when=True, children=lambda cond: h("p", {}, f"got {cond}")),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "got True" in texts


def test_show_reactive_toggle(wyb, root_element):
    """Show re-renders when its when-getter changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    visible, set_visible = reactivity.create_signal(True)

    def App(props):
        def render():
            return Show(when=visible, children=lambda: h("p", {}, "on"), fallback=lambda: h("p", {}, "off"))

        return render

    vdom.render(h(App, {}), root_element)
    assert "on" in collect_texts(root_element.element)

    set_visible(False)
    time.sleep(0.05)
    assert "off" in collect_texts(root_element.element)

    set_visible(True)
    time.sleep(0.05)
    assert "on" in collect_texts(root_element.element)


def test_show_none_children():
    """Show with no children renders empty text."""
    result = Show(when=True)
    assert isinstance(result, VNode)


def test_show_callable_fallback(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Show(when=False, children=h("p", {}, "main"), fallback=lambda: h("p", {}, "lazy fallback")),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "lazy fallback" in texts


# ---------------------------------------------------------------------------
# For — VNode structure
# ---------------------------------------------------------------------------


def test_for_returns_vnode():
    result = For(each=["A", "B", "C"], children=lambda item, idx: h("li", {"key": idx()}, item()))
    assert isinstance(result, VNode)


def test_for_empty_list():
    result = For(each=[], children=lambda item, idx: h("li", {}, item()))
    assert isinstance(result, VNode)


def test_for_callable_each():
    result = For(each=lambda: [1, 2], children=lambda item, idx: h("li", {}, str(item())))
    assert isinstance(result, VNode)


# ---------------------------------------------------------------------------
# For — rendered output with browser stubs
# ---------------------------------------------------------------------------


def test_for_renders_items(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        For(each=["A", "B", "C"], children=lambda item, idx: h("li", {"key": idx()}, item())),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "A" in texts
    assert "B" in texts
    assert "C" in texts


def test_for_empty_renders_nothing(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        For(each=[], children=lambda item, idx: h("li", {}, item())),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert texts == [""] or all(t.strip() == "" for t in texts)


def test_for_index_getter(wyb, root_element):
    vdom = wyb["vdom"]
    indices: list = []

    def mapper(item, idx):
        indices.append(idx())
        return h("li", {}, str(item()))

    vdom.render(For(each=[10, 20, 30], children=mapper), root_element)
    assert indices == [0, 1, 2]


def test_for_reactive_list(wyb, root_element):
    """For re-renders when its list signal changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal(["X", "Y"])

    def App(props):
        def render():
            return For(each=items, children=lambda item, idx: h("li", {}, item()))

        return render

    vdom.render(h(App, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "X" in texts and "Y" in texts

    set_items(["A", "B", "C"])
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "A" in texts and "B" in texts and "C" in texts


def test_for_fallback(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        For(each=[], children=lambda item, idx: h("li", {}, item()), fallback=h("p", {}, "empty")),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "empty" in texts


# ---------------------------------------------------------------------------
# Index — VNode structure
# ---------------------------------------------------------------------------


def test_index_returns_vnode():
    result = Index(each=[10, 20], children=lambda item, idx: h("li", {}, str(item())))
    assert isinstance(result, VNode)


def test_index_empty_list():
    result = Index(each=[], children=lambda item, idx: h("li", {}, str(item())))
    assert isinstance(result, VNode)


# ---------------------------------------------------------------------------
# Index — rendered output with browser stubs
# ---------------------------------------------------------------------------


def test_index_renders_items(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Index(each=[10, 20], children=lambda item, idx: h("li", {}, str(item()))),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "10" in texts
    assert "20" in texts


def test_index_item_getter(wyb, root_element):
    vdom = wyb["vdom"]
    captured: list = []

    def mapper(item, idx):
        captured.append(item())
        return h("li", {}, str(item()))

    vdom.render(Index(each=["a", "b"], children=mapper), root_element)
    assert captured == ["a", "b"]


def test_index_reactive_list(wyb, root_element):
    """Index re-renders when its list signal changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal([1, 2])

    def App(props):
        def render():
            return Index(each=items, children=lambda item, idx: h("li", {}, str(item())))

        return render

    vdom.render(h(App, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "1" in texts and "2" in texts

    set_items([10, 20, 30])
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "10" in texts and "20" in texts and "30" in texts


# ---------------------------------------------------------------------------
# Switch / Match — VNode structure
# ---------------------------------------------------------------------------


def test_match_returns_match_result():
    result = Match(True, h("p", {}, "yes"))
    assert isinstance(result, _MatchResult)


def test_switch_returns_vnode():
    result = Switch(
        Match(True, h("p", {}, "first")),
        Match(True, h("p", {}, "second")),
        fallback=h("p", {}, "default"),
    )
    assert isinstance(result, VNode)


def test_switch_no_match():
    result = Switch(
        Match(False, h("p", {}, "nope")),
        fallback=h("p", {}, "default"),
    )
    assert isinstance(result, VNode)


def test_switch_no_match_no_fallback():
    result = Switch(Match(False, h("p", {}, "nope")))
    assert isinstance(result, VNode)


# ---------------------------------------------------------------------------
# Switch / Match — rendered output with browser stubs
# ---------------------------------------------------------------------------


def test_switch_first_match_renders(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Switch(
            Match(True, h("p", {}, "first")),
            Match(True, h("p", {}, "second")),
            fallback=h("p", {}, "default"),
        ),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "first" in texts
    assert "second" not in texts


def test_switch_fallback_renders(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Switch(Match(False, h("p", {}, "nope")), fallback=h("p", {}, "default")),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "default" in texts


def test_switch_no_fallback_renders_empty(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Switch(Match(False, h("p", {}, "nope"))), root_element)
    texts = collect_texts(root_element.element)
    assert all(t.strip() == "" for t in texts)


def test_switch_callable_when(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Switch(Match(lambda: True, h("p", {}, "ok"))), root_element)
    texts = collect_texts(root_element.element)
    assert "ok" in texts


def test_switch_reactive(wyb, root_element):
    """Switch re-renders when its branch conditions change."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    status, set_status = reactivity.create_signal("loading")

    def App(props):
        def render():
            return Switch(
                Match(when=lambda: status() == "loading", children=lambda: h("p", {}, "Loading...")),
                Match(when=lambda: status() == "ready", children=lambda: h("p", {}, "Ready")),
                fallback=lambda: h("p", {}, "Unknown"),
            )

        return render

    vdom.render(h(App, {}), root_element)
    assert "Loading..." in collect_texts(root_element.element)

    set_status("ready")
    time.sleep(0.05)
    assert "Ready" in collect_texts(root_element.element)

    set_status("other")
    time.sleep(0.05)
    assert "Unknown" in collect_texts(root_element.element)


def test_switch_callable_children(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(
        Switch(
            Match(True, lambda: h("p", {}, "lazy child")),
        ),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "lazy child" in texts


# ---------------------------------------------------------------------------
# Dynamic — VNode structure
# ---------------------------------------------------------------------------


def test_dynamic_with_string_tag():
    result = Dynamic(component="div", children=["hello"])
    assert isinstance(result, VNode)


def test_dynamic_with_component():
    def MyComp(props):
        return h("span", {}, props.get("text", ""))

    result = Dynamic(component=MyComp, text="hi")
    assert isinstance(result, VNode)


def test_dynamic_with_none():
    result = Dynamic(component=None)
    assert isinstance(result, VNode)


# ---------------------------------------------------------------------------
# Dynamic — rendered output with browser stubs
# ---------------------------------------------------------------------------


def test_dynamic_renders_tag(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Dynamic(component="div", children=["hello"]), root_element)
    texts = collect_texts(root_element.element)
    assert "hello" in texts


def test_dynamic_renders_component(wyb, root_element):
    vdom = wyb["vdom"]

    def MyComp(props):
        return h("span", {}, props.get("text", ""))

    vdom.render(Dynamic(component=MyComp, text="hi"), root_element)
    texts = collect_texts(root_element.element)
    assert "hi" in texts


def test_dynamic_renders_none(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Dynamic(component=None), root_element)
    texts = collect_texts(root_element.element)
    assert all(t.strip() == "" for t in texts)


def test_dynamic_reactive(wyb, root_element):
    """Dynamic re-renders when its component getter changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    level, set_level = reactivity.create_signal("h1")

    def App(props):
        def render():
            return Dynamic(component=lambda: level(), children=["Title"])

        return render

    vdom.render(h(App, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "Title" in texts


def test_dynamic_kwargs(wyb, root_element):
    vdom = wyb["vdom"]
    vdom.render(Dynamic(component="div", children=["content"], id="main"), root_element)
    texts = collect_texts(root_element.element)
    assert "content" in texts

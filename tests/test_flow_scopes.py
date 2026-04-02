"""Tests for fine-grained reactive scopes in flow controls.

Verifies that For/Index create per-item/per-index reactive scopes,
and that Show uses keyed conditional rendering.
"""

import time

from conftest import collect_texts

from wybthon.flow import For, Index, Show
from wybthon.vnode import h

# ---------------------------------------------------------------------------
# For — per-item reactive scopes
# ---------------------------------------------------------------------------


def test_for_item_getter_is_signal(wyb, root_element):
    """For provides signal-backed item getters."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal(["A", "B", "C"])
    captured_getters: list = []

    def mapper(item, idx):
        captured_getters.append(item)
        return h("li", {}, item())

    def App(props):
        def render():
            return For(each=items, children=mapper)

        return render

    vdom.render(h(App, {}), root_element)
    assert len(captured_getters) == 3
    assert captured_getters[0]() == "A"
    assert captured_getters[1]() == "B"
    assert captured_getters[2]() == "C"


def test_for_index_getter_is_signal(wyb, root_element):
    """For provides signal-backed index getters that update on reorder."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    a, b, c = ["A"], ["B"], ["C"]
    items, set_items = reactivity.create_signal([a, b, c])
    captured_idx_getters: list = []

    def mapper(item, idx):
        captured_idx_getters.append(idx)
        return h("li", {}, str(idx()))

    def App(props):
        def render():
            return For(each=items, children=mapper)

        return render

    vdom.render(h(App, {}), root_element)
    assert captured_idx_getters[0]() == 0
    assert captured_idx_getters[1]() == 1
    assert captured_idx_getters[2]() == 2

    set_items([c, a, b])
    time.sleep(0.05)

    assert captured_idx_getters[0]() == 1
    assert captured_idx_getters[1]() == 2
    assert captured_idx_getters[2]() == 0


def test_for_disposes_scope_on_item_removal(wyb, root_element):
    """When an item leaves a For list, its scope is disposed."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    a, b, c = ["A"], ["B"], ["C"]
    items, set_items = reactivity.create_signal([a, b, c])
    cleanup_log: list = []

    def mapper(item, idx):
        reactivity.on_cleanup(lambda _i=idx(): cleanup_log.append(_i))
        return h("li", {}, "item")

    def App(props):
        def render():
            return For(each=items, children=mapper)

        return render

    vdom.render(h(App, {}), root_element)
    assert cleanup_log == []

    set_items([a])
    time.sleep(0.05)

    assert 1 in cleanup_log
    assert 2 in cleanup_log


# ---------------------------------------------------------------------------
# Index — per-index reactive scopes
# ---------------------------------------------------------------------------


def test_index_item_getter_updates_in_place(wyb, root_element):
    """Index item getters update when the value at that position changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal(["A", "B"])
    captured_getters: list = []

    def mapper(item, idx):
        captured_getters.append(item)
        return h("li", {}, item())

    def App(props):
        def render():
            return Index(each=items, children=mapper)

        return render

    vdom.render(h(App, {}), root_element)
    assert captured_getters[0]() == "A"
    assert captured_getters[1]() == "B"

    set_items(["X", "Y"])
    time.sleep(0.05)

    assert captured_getters[0]() == "X"
    assert captured_getters[1]() == "Y"


def test_index_disposes_on_shrink(wyb, root_element):
    """Index disposes scopes for excess positions when the list shrinks."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    items, set_items = reactivity.create_signal(["A", "B", "C"])
    cleanup_log: list = []

    def mapper(item, idx):
        reactivity.on_cleanup(lambda _i=idx: cleanup_log.append(_i))
        return h("li", {}, item())

    def App(props):
        def render():
            return Index(each=items, children=mapper)

        return render

    vdom.render(h(App, {}), root_element)
    assert cleanup_log == []

    set_items(["A"])
    time.sleep(0.05)

    assert 1 in cleanup_log
    assert 2 in cleanup_log


# ---------------------------------------------------------------------------
# Show — keyed conditional scope
# ---------------------------------------------------------------------------


def test_show_keyed_scope_disposal(wyb, root_element):
    """Show disposes the branch scope when truthiness changes."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    visible, set_visible = reactivity.create_signal(True)

    def child_fn():
        return h("p", {}, "visible")

    def App(props):
        def render():
            return Show(
                when=visible,
                children=child_fn,
                fallback=lambda: h("p", {}, "hidden"),
            )

        return render

    vdom.render(h(App, {}), root_element)
    assert "visible" in collect_texts(root_element.element)

    set_visible(False)
    time.sleep(0.05)
    assert "hidden" in collect_texts(root_element.element)

    set_visible(True)
    time.sleep(0.05)
    assert "visible" in collect_texts(root_element.element)


def test_show_stable_when_condition_unchanged(wyb, root_element):
    """Show does not dispose the branch scope when truthiness is unchanged."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    count, set_count = reactivity.create_signal(1)

    def App(props):
        def render():
            return Show(
                when=lambda: count() > 0,
                children=lambda: h("p", {}, f"count={count()}"),
            )

        return render

    vdom.render(h(App, {}), root_element)
    assert "count=1" in collect_texts(root_element.element)

    set_count(5)
    time.sleep(0.05)
    assert "count=5" in collect_texts(root_element.element)

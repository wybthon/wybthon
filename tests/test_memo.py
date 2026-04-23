"""Tests for memo() – memoized function components (new reactive-prop model)."""

import time

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401


def test_memo_renders_initially(wyb, root_element):
    vdom = wyb["vdom"]

    render_count = [0]

    def Display(props):
        render_count[0] += 1
        return vdom.h("p", {}, "value=", props.value("value"))

    MemoDisplay = vdom.memo(Display)

    vdom.render(vdom.h(MemoDisplay, {"value": "A"}), root_element)

    assert render_count[0] == 1
    assert "A" in collect_texts(root_element.element)


def test_memo_skips_rerender_same_props(wyb, root_element):
    """When parent re-renders but passes the same prop references, memo skips."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    comp_mod = wyb["component"]

    child_renders = [0]
    parent_setter = [None]
    stable_value = "stable"

    def Child(props):
        child_renders[0] += 1
        return vdom.h("span", {}, "child:", props.value("label"))

    MemoChild = vdom.memo(Child)

    @comp_mod.component
    def Parent():
        count, set_count = reactivity.create_signal(0)
        parent_setter[0] = set_count
        return vdom.h(
            "div",
            {},
            vdom.h("p", {}, count),
            vdom.h(MemoChild, {"label": stable_value}),
        )

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1

    parent_setter[0](1)
    time.sleep(0.05)

    assert child_renders[0] == 1


def test_memo_rerenders_on_changed_props(wyb, root_element):
    """Without memo, a parent re-render still updates the child's reactive hole on prop change."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    comp_mod = wyb["component"]

    child_setup_runs = [0]
    parent_setter = [None]

    def Child(props):
        child_setup_runs[0] += 1
        # Auto-hole on the count getter.
        return vdom.h("span", {}, "count=", props["count"])

    MemoChild = vdom.memo(Child)

    @comp_mod.component
    def Parent():
        count, set_count = reactivity.create_signal(0)
        parent_setter[0] = set_count
        return vdom.h("div", {}, vdom.h(MemoChild, {"count": count}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_setup_runs[0] == 1
    assert "0" in collect_texts(root_element.element)

    parent_setter[0](1)
    time.sleep(0.05)

    assert child_setup_runs[0] == 1, "child setup runs once; updates flow through the hole"
    assert "1" in collect_texts(root_element.element)


def test_memo_custom_comparison(wyb, root_element):
    """Custom are_props_equal can control when re-renders happen."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    comp_mod = wyb["component"]

    child_renders = [0]
    parent_setter = [None]

    def Child(props):
        child_renders[0] += 1
        return vdom.h("span", {}, "v=", props["value"])

    MemoChild = vdom.memo(Child, are_props_equal=lambda old, new: True)

    @comp_mod.component
    def Parent():
        count, set_count = reactivity.create_signal(0)
        parent_setter[0] = set_count
        return vdom.h("div", {}, vdom.h(MemoChild, {"value": count()}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1

    parent_setter[0](1)
    time.sleep(0.05)

    assert child_renders[0] == 1


def test_memo_with_signals(wyb, root_element):
    """Memo components work with signals when they re-render."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    child_setter = [None]

    def Child(props):
        local, set_local = reactivity.create_signal(0)
        child_setter[0] = set_local
        return vdom.h("span", {}, "local=", local)

    MemoChild = vdom.memo(Child)

    vdom.render(vdom.h(MemoChild, {}), root_element)
    assert "0" in collect_texts(root_element.element)

    child_setter[0](5)
    time.sleep(0.05)

    assert "5" in collect_texts(root_element.element)

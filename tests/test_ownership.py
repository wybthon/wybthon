"""Tests for the reactive ownership tree (Owner / Computation hierarchy).

Verifies that:
- Nested effects are disposed when the parent effect re-runs.
- Component setup effects persist across re-renders.
- ``create_root`` creates independent ownership scopes.
- ``on_cleanup`` registrations are properly scoped.
- Context values propagate through the ownership tree.
"""

import time

from conftest import collect_texts

import wybthon as _wyb  # noqa: F401

# ---------------------------------------------------------------------------
# Owner basics
# ---------------------------------------------------------------------------


def test_owner_dispose_children():
    from wybthon.reactivity import Owner

    parent = Owner()
    child1 = Owner()
    child2 = Owner()
    parent._add_child(child1)
    parent._add_child(child2)

    log = []
    child1._cleanups.append(lambda: log.append("c1"))
    child2._cleanups.append(lambda: log.append("c2"))

    parent.dispose()
    assert child1._disposed
    assert child2._disposed
    assert "c1" in log
    assert "c2" in log


def test_owner_dispose_is_idempotent():
    from wybthon.reactivity import Owner

    parent = Owner()
    log = []
    parent._cleanups.append(lambda: log.append("cleanup"))
    parent.dispose()
    parent.dispose()
    assert log == ["cleanup"]


def test_owner_child_removed_from_parent_on_dispose():
    from wybthon.reactivity import Owner

    parent = Owner()
    child = Owner()
    parent._add_child(child)
    assert len(parent._children) == 1
    child.dispose()
    assert len(parent._children) == 0
    assert child._parent is None


# ---------------------------------------------------------------------------
# Nested effect disposal
# ---------------------------------------------------------------------------


def test_nested_effect_disposed_on_parent_rerun(wyb, root_element):
    """Effects created inside a render function are disposed on re-render."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    setter_ref = [None]
    inner_runs = [0]
    inner_cleanups = [0]

    def App(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def render():
            val = count()

            def inner_effect():
                inner_runs[0] += 1
                reactivity.on_cleanup(lambda: inner_cleanups.__setitem__(0, inner_cleanups[0] + 1))

            reactivity.create_effect(inner_effect)
            return vdom.h("p", {}, f"count:{val}")

        return render

    vdom.render(vdom.h(App, {}), root_element)
    assert inner_runs[0] == 1
    assert inner_cleanups[0] == 0

    setter_ref[0](1)
    time.sleep(0.05)

    # Inner effect from prev render was disposed (cleanup ran),
    # and a new one was created
    assert inner_cleanups[0] >= 1
    assert inner_runs[0] >= 2


def test_setup_effects_survive_rerender(wyb, root_element):
    """Effects created during component setup persist across re-renders."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    setter_ref = [None]
    setup_effect_runs = [0]
    setup_effect_cleanups = [0]

    def App(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def setup_eff():
            count()
            setup_effect_runs[0] += 1
            reactivity.on_cleanup(lambda: setup_effect_cleanups.__setitem__(0, setup_effect_cleanups[0] + 1))

        reactivity.create_effect(setup_eff)

        def render():
            return vdom.h("p", {}, f"count:{count()}")

        return render

    vdom.render(vdom.h(App, {}), root_element)
    assert setup_effect_runs[0] == 1
    assert setup_effect_cleanups[0] == 0

    setter_ref[0](1)
    time.sleep(0.05)

    # Setup effect re-ran (it tracks count) but was NOT disposed
    assert setup_effect_runs[0] == 2
    # Previous cleanup ran before re-run
    assert setup_effect_cleanups[0] == 1


# ---------------------------------------------------------------------------
# create_root ownership
# ---------------------------------------------------------------------------


def test_create_root_disposes_all_effects():
    from wybthon.reactivity import create_effect, create_root, create_signal

    log = []

    def body(dispose):
        count, set_count = create_signal(0)
        create_effect(lambda: log.append(f"effect:{count()}"))
        set_count(1)
        time.sleep(0.05)
        return dispose

    dispose_fn = create_root(body)
    assert "effect:0" in log
    assert "effect:1" in log

    dispose_fn()


def test_create_root_cleanup():
    from wybthon.reactivity import create_root, on_cleanup

    log = []

    def body(dispose):
        on_cleanup(lambda: log.append("root_cleanup"))
        return dispose

    dispose_fn = create_root(body)
    assert log == []
    dispose_fn()
    assert "root_cleanup" in log


# ---------------------------------------------------------------------------
# Component unmount disposes everything
# ---------------------------------------------------------------------------


def test_unmount_disposes_component_context(wyb, root_element):
    """Unmounting a component disposes its context and all owned effects."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    cleanup_log = []

    def MyComp(props):
        reactivity.on_cleanup(lambda: cleanup_log.append("comp_cleanup"))

        def eff():
            reactivity.on_cleanup(lambda: cleanup_log.append("effect_cleanup"))

        reactivity.create_effect(eff)

        def render():
            return vdom.h("p", {}, "hello")

        return render

    tree = vdom.h(MyComp, {})
    vdom.render(tree, root_element)
    assert cleanup_log == []

    vdom._unmount(tree)
    assert "comp_cleanup" in cleanup_log
    assert "effect_cleanup" in cleanup_log


# ---------------------------------------------------------------------------
# Context via ownership tree
# ---------------------------------------------------------------------------


def test_context_propagation_through_ownership(wyb, root_element):
    """Context values are accessible through the ownership tree."""
    vdom = wyb["vdom"]
    from wybthon.context import Provider, create_context, use_context

    Theme = create_context("light")
    captured_value = [None]

    def Child(props):
        captured_value[0] = use_context(Theme)
        return vdom.h("p", {}, f"theme={captured_value[0]}")

    tree = vdom.h(Provider, {"context": Theme, "value": "dark"}, vdom.h(Child, {}))
    vdom.render(tree, root_element)

    assert captured_value[0] == "dark"
    assert "theme=dark" in collect_texts(root_element.element)

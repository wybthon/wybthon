"""Tests for signals-first primitives (create_signal, create_effect, create_memo, on_mount, on_cleanup)."""

import time

import pytest
from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401

# --------------------------------------------------------------------------- #
# create_signal
# --------------------------------------------------------------------------- #


def test_create_signal_initial_render(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    render_log = []

    def Counter(props):
        count, set_count = reactivity.create_signal(0)

        def render():
            val = count()
            render_log.append(val)
            return vdom.h("p", {}, f"Count: {val}")

        return render

    vdom.render(vdom.h(Counter, {}), root_element)
    assert render_log == [0]
    assert "Count: 0" in collect_texts(root_element.element)


def test_create_signal_re_renders_on_set(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    setter_ref = [None]
    render_log = []

    def Counter(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def render():
            val = count()
            render_log.append(val)
            return vdom.h("p", {}, f"Count: {val}")

        return render

    vdom.render(vdom.h(Counter, {}), root_element)
    assert render_log == [0]
    assert "Count: 0" in collect_texts(root_element.element)

    setter_ref[0](1)
    time.sleep(0.05)
    assert len(render_log) == 2
    assert render_log[-1] == 1
    assert "Count: 1" in collect_texts(root_element.element)


def test_create_signal_updater_function(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    setter_ref = [None]
    render_log = []

    def Counter(props):
        count, set_count = reactivity.create_signal(10)
        setter_ref[0] = set_count

        def render():
            val = count()
            render_log.append(val)
            return vdom.h("p", {}, f"{val}")

        return render

    vdom.render(vdom.h(Counter, {}), root_element)
    assert render_log == [10]

    setter_ref[0](15)
    time.sleep(0.05)
    assert render_log[-1] == 15


def test_create_signal_lazy_initializer(wyb, root_element):
    """Signals are created once during setup – no lazy initializer needed."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    values = []

    def MyComp(props):
        val, _ = reactivity.create_signal(42)

        def render():
            v = val()
            values.append(v)
            return vdom.h("p", {}, str(v))

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert values == [42]


# --------------------------------------------------------------------------- #
# create_effect
# --------------------------------------------------------------------------- #


def test_create_effect_runs_on_mount(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    log = []

    def MyComp(props):
        reactivity.create_effect(lambda: log.append("mounted"))
        return vdom.h("p", {}, "hello")

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert "mounted" in log


def test_on_cleanup_runs_on_unmount(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    log = []

    def MyComp(props):
        log.append("setup")
        reactivity.on_cleanup(lambda: log.append("cleanup"))
        return vdom.h("p", {}, "hello")

    tree = vdom.h(MyComp, {})
    vdom.render(tree, root_element)
    assert "setup" in log
    assert "cleanup" not in log

    vdom._unmount(tree)
    assert "cleanup" in log


def test_create_effect_auto_tracks_signals(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    effect_log = []
    setter_ref = [None]

    def MyComp(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count
        reactivity.create_effect(lambda: effect_log.append(count()))

        def render():
            return vdom.h("p", {}, f"{count()}")

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert effect_log == [0]

    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]

    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]


def test_create_effect_cleanup_per_run(wyb, root_element):
    """on_cleanup inside create_effect runs before each re-execution."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    log = []
    setter_ref = [None]

    def MyComp(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def tracked_effect():
            val = count()
            log.append(f"run:{val}")
            reactivity.on_cleanup(lambda: log.append(f"cleanup:{val}"))

        reactivity.create_effect(tracked_effect)

        def render():
            return vdom.h("p", {}, f"{count()}")

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert log == ["run:0"]

    setter_ref[0](1)
    time.sleep(0.05)
    assert "cleanup:0" in log
    assert "run:1" in log


# --------------------------------------------------------------------------- #
# on_mount
# --------------------------------------------------------------------------- #


def test_on_mount_runs_after_mount(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    log = []

    def MyComp(props):
        reactivity.on_mount(lambda: log.append("mounted"))

        def render():
            return vdom.h("p", {}, "hello")

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert "mounted" in log


def test_on_mount_error_outside_component():
    """on_mount raises RuntimeError when called outside a component."""
    from wybthon.reactivity import on_mount

    with pytest.raises(RuntimeError, match="inside a component"):
        on_mount(lambda: None)


def test_on_cleanup_error_outside_component():
    """on_cleanup raises RuntimeError when called outside a component or effect."""
    from wybthon.reactivity import on_cleanup

    with pytest.raises(RuntimeError, match="inside a component"):
        on_cleanup(lambda: None)


# --------------------------------------------------------------------------- #
# create_memo
# --------------------------------------------------------------------------- #


def test_create_memo(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    compute_calls = [0]
    setter_ref = [None]

    def MyComp(props):
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def expensive():
            compute_calls[0] += 1
            return count() * 10

        result = reactivity.create_memo(expensive)

        def render():
            return vdom.h("p", {}, f"{result()}")

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert compute_calls[0] == 1
    assert "0" in collect_texts(root_element.element)

    setter_ref[0](1)
    time.sleep(0.05)
    assert compute_calls[0] == 2
    assert "10" in collect_texts(root_element.element)


# --------------------------------------------------------------------------- #
# Multiple signals in one component
# --------------------------------------------------------------------------- #


def test_multiple_signals(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    setter_a_ref = [None]
    setter_b_ref = [None]

    def MyComp(props):
        a, set_a = reactivity.create_signal("hello")
        b, set_b = reactivity.create_signal(42)
        setter_a_ref[0] = set_a
        setter_b_ref[0] = set_b

        def render():
            return vdom.h("div", {}, vdom.h("p", {}, a()), vdom.h("p", {}, str(b())))

        return render

    vdom.render(vdom.h(MyComp, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "hello" in texts
    assert "42" in texts

    setter_a_ref[0]("world")
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "world" in texts
    assert "42" in texts

    setter_b_ref[0](99)
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "world" in texts
    assert "99" in texts


# --------------------------------------------------------------------------- #
# Nested function components with signals
# --------------------------------------------------------------------------- #


def test_nested_components(wyb, root_element):
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    child_setter_ref = [None]

    def Child(props):
        count, set_count = reactivity.create_signal(0)
        child_setter_ref[0] = set_count

        def render():
            return vdom.h("span", {}, f"child:{count()}")

        return render

    def Parent(props):
        label, _ = reactivity.create_signal("parent")

        def render():
            return vdom.h("div", {}, vdom.h("p", {}, label()), vdom.h(Child, {}))

        return render

    vdom.render(vdom.h(Parent, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "parent" in texts
    assert "child:0" in texts

    child_setter_ref[0](5)
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "parent" in texts
    assert "child:5" in texts


# --------------------------------------------------------------------------- #
# Stateless function components reading raw signals
# --------------------------------------------------------------------------- #


def test_function_component_reads_signal_reactively(wyb, root_element):
    """Stateless function components that read raw signals re-render."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    external_sig = reactivity.signal("initial")
    render_count = [0]

    def Display(props):
        render_count[0] += 1
        val = external_sig.get()
        return vdom.h("p", {}, val)

    vdom.render(vdom.h(Display, {}), root_element)
    assert render_count[0] == 1
    assert "initial" in collect_texts(root_element.element)

    external_sig.set("updated")
    time.sleep(0.05)
    assert render_count[0] == 2
    assert "updated" in collect_texts(root_element.element)

"""Tests for the hooks system (use_state, use_effect, use_memo, use_ref, use_callback)."""

import time

import pytest
from conftest import collect_texts

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon as _wybthon_pkg  # noqa: F401

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_use_state_initial_render(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    render_log = []

    def Counter(props):
        count, _set = hooks.use_state(0)
        render_log.append(count)
        return vdom.h("p", {}, f"Count: {count}")

    root = root_element
    vdom.render(vdom.h(Counter, {}), root)

    assert render_log == [0]
    texts = collect_texts(root.element)
    assert "Count: 0" in texts


def test_use_state_re_renders_on_set(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    setter_ref = [None]
    render_log = []

    def Counter(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        render_log.append(count)
        return vdom.h("p", {}, f"Count: {count}")

    root = root_element
    vdom.render(vdom.h(Counter, {}), root)

    assert render_log == [0]
    assert "Count: 0" in collect_texts(root.element)

    setter_ref[0](1)
    time.sleep(0.05)

    assert len(render_log) == 2
    assert render_log[-1] == 1
    assert "Count: 1" in collect_texts(root.element)


def test_use_state_updater_function(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    setter_ref = [None]
    render_log = []

    def Counter(props):
        count, set_count = hooks.use_state(10)
        setter_ref[0] = set_count
        render_log.append(count)
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(Counter, {}), root)
    assert render_log == [10]

    setter_ref[0](lambda prev: prev + 5)
    time.sleep(0.05)
    assert render_log[-1] == 15


def test_use_state_lazy_initializer(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    init_calls = [0]

    def expensive_init():
        init_calls[0] += 1
        return 42

    values = []

    def MyComp(props):
        val, _ = hooks.use_state(expensive_init)
        values.append(val)
        return vdom.h("p", {}, str(val))

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert init_calls[0] == 1
    assert values == [42]


def test_use_effect_runs_after_mount(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    log = []

    def MyComp(props):
        hooks.use_effect(lambda: log.append("mounted"), [])
        return vdom.h("p", {}, "hello")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)

    assert "mounted" in log


def test_use_effect_cleanup_on_unmount(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    log = []

    def MyComp(props):
        def setup():
            log.append("setup")
            return lambda: log.append("cleanup")

        hooks.use_effect(setup, [])
        return vdom.h("p", {}, "hello")

    root = root_element
    tree = vdom.h(MyComp, {})
    vdom.render(tree, root)
    assert "setup" in log
    assert "cleanup" not in log

    vdom._unmount(tree)
    assert "cleanup" in log


def test_use_effect_no_deps_runs_every_render(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    effect_runs = [0]
    setter_ref = [None]

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        hooks.use_effect(lambda: effect_runs.__setitem__(0, effect_runs[0] + 1))
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert effect_runs[0] == 1

    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_runs[0] == 2


def test_use_effect_empty_deps_runs_only_on_mount(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    effect_runs = [0]
    setter_ref = [None]

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        hooks.use_effect(lambda: effect_runs.__setitem__(0, effect_runs[0] + 1), [])
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert effect_runs[0] == 1

    setter_ref[0](1)
    time.sleep(0.05)
    # Effect should NOT have run again
    assert effect_runs[0] == 1


def test_use_effect_deps_re_runs_on_change(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    effect_log = []
    setter_ref = [None]

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        hooks.use_effect(lambda: effect_log.append(count), [count])
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert effect_log == [0]

    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]

    # Same value → signal skips, no re-render, no effect
    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]


def test_use_memo(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    compute_calls = [0]
    setter_ref = [None]

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        bucket = count // 2

        def expensive():
            compute_calls[0] += 1
            return bucket * 10

        result = hooks.use_memo(expensive, [bucket])
        return vdom.h("p", {}, f"{result}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert compute_calls[0] == 1
    assert "0" in collect_texts(root.element)

    setter_ref[0](1)
    time.sleep(0.05)
    # bucket is still 0 → memo should NOT recompute
    assert compute_calls[0] == 1

    setter_ref[0](2)
    time.sleep(0.05)
    # bucket is now 1 → memo should recompute
    assert compute_calls[0] == 2
    assert "10" in collect_texts(root.element)


def test_use_ref_persists_across_renders(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    setter_ref = [None]
    ref_ids = []

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        my_ref = hooks.use_ref("initial")
        ref_ids.append(id(my_ref))
        return vdom.h("p", {}, f"{my_ref.current}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert "initial" in collect_texts(root.element)

    setter_ref[0](1)
    time.sleep(0.05)

    assert len(ref_ids) == 2
    assert ref_ids[0] == ref_ids[1]


def test_use_callback_stable_reference(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    setter_ref = [None]
    callback_ids = []

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        cb = hooks.use_callback(lambda: count, [])
        callback_ids.append(id(cb))
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)

    setter_ref[0](1)
    time.sleep(0.05)

    assert len(callback_ids) == 2
    assert callback_ids[0] == callback_ids[1]


def test_multiple_hooks_in_one_component(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    setter_a_ref = [None]
    setter_b_ref = [None]

    def MyComp(props):
        a, set_a = hooks.use_state("hello")
        b, set_b = hooks.use_state(42)
        setter_a_ref[0] = set_a
        setter_b_ref[0] = set_b
        return vdom.h("div", {}, vdom.h("p", {}, a), vdom.h("p", {}, str(b)))

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    texts = collect_texts(root.element)
    assert "hello" in texts
    assert "42" in texts

    setter_a_ref[0]("world")
    time.sleep(0.05)
    texts = collect_texts(root.element)
    assert "world" in texts
    assert "42" in texts

    setter_b_ref[0](99)
    time.sleep(0.05)
    texts = collect_texts(root.element)
    assert "world" in texts
    assert "99" in texts


def test_hooks_error_outside_component():
    """Hooks raise RuntimeError when called outside a component render."""
    from wybthon.hooks import use_effect, use_ref, use_state

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_state(0)

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_effect(lambda: None)

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_ref()


def test_nested_function_components_with_hooks(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    child_setter_ref = [None]

    def Child(props):
        count, set_count = hooks.use_state(0)
        child_setter_ref[0] = set_count
        return vdom.h("span", {}, f"child:{count}")

    def Parent(props):
        label, _ = hooks.use_state("parent")
        return vdom.h("div", {}, vdom.h("p", {}, label), vdom.h(Child, {}))

    root = root_element
    vdom.render(vdom.h(Parent, {}), root)
    texts = collect_texts(root.element)
    assert "parent" in texts
    assert "child:0" in texts

    child_setter_ref[0](5)
    time.sleep(0.05)
    texts = collect_texts(root.element)
    assert "parent" in texts
    assert "child:5" in texts


def test_function_component_reads_signal_reactively(wyb, root_element):
    """Function components that read raw signals (without hooks) also re-render."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    external_sig = reactivity.signal("initial")

    render_count = [0]

    def Display(props):
        render_count[0] += 1
        val = external_sig.get()
        return vdom.h("p", {}, val)

    root = root_element
    vdom.render(vdom.h(Display, {}), root)
    assert render_count[0] == 1
    assert "initial" in collect_texts(root.element)

    external_sig.set("updated")
    time.sleep(0.05)
    assert render_count[0] == 2
    assert "updated" in collect_texts(root.element)


# --------------------------------------------------------------------------- #
# use_layout_effect
# --------------------------------------------------------------------------- #


def test_use_layout_effect_runs_on_mount(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    log = []

    def MyComp(props):
        hooks.use_layout_effect(lambda: log.append("layout_mounted"), [])
        return vdom.h("p", {}, "hello")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)

    assert "layout_mounted" in log


def test_use_layout_effect_runs_before_regular_effects(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    order = []

    def MyComp(props):
        hooks.use_effect(lambda: order.append("effect"), [])
        hooks.use_layout_effect(lambda: order.append("layout_effect"), [])
        return vdom.h("p", {}, "hello")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)

    assert order.index("layout_effect") < order.index("effect")


def test_use_layout_effect_cleanup_on_unmount(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    log = []

    def MyComp(props):
        def setup():
            log.append("layout_setup")
            return lambda: log.append("layout_cleanup")

        hooks.use_layout_effect(setup, [])
        return vdom.h("p", {}, "hello")

    root = root_element
    tree = vdom.h(MyComp, {})
    vdom.render(tree, root)
    assert "layout_setup" in log
    assert "layout_cleanup" not in log

    vdom._unmount(tree)
    assert "layout_cleanup" in log


def test_use_layout_effect_deps_control_rerun(wyb, root_element):
    vdom, hooks = wyb["vdom"], wyb["hooks"]

    effect_log = []
    setter_ref = [None]

    def MyComp(props):
        count, set_count = hooks.use_state(0)
        setter_ref[0] = set_count
        hooks.use_layout_effect(lambda: effect_log.append(count), [count])
        return vdom.h("p", {}, f"{count}")

    root = root_element
    vdom.render(vdom.h(MyComp, {}), root)
    assert effect_log == [0]

    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]

    # Same value → no re-render → no layout effect
    setter_ref[0](1)
    time.sleep(0.05)
    assert effect_log == [0, 1]


def test_use_layout_effect_error_outside_component():
    """use_layout_effect raises RuntimeError when called outside a component."""
    from wybthon.hooks import use_layout_effect

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_layout_effect(lambda: None)

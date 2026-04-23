"""Tests for the @component decorator (new fully-reactive props model)."""

import time

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401

# ---------------------------------------------------------------------------
# Tests — pure decorator behaviour (no browser stubs needed)
# ---------------------------------------------------------------------------


def test_component_has_marker():
    from wybthon.component import component

    @component
    def Greet(name="world"):
        pass

    assert getattr(Greet, "_wyb_component", False) is True


def test_component_preserves_name():
    from wybthon.component import component

    @component
    def MyWidget(label=""):
        pass

    assert MyWidget.__name__ == "MyWidget"


def test_component_passes_reactive_accessors():
    """Each parameter is bound to a callable getter (the reactive accessor)."""
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name="world", greeting="Hello"):
        captured["name"] = name
        captured["greeting"] = greeting

    Greet({"name": "Alice", "greeting": "Hi"})
    assert callable(captured["name"])
    assert callable(captured["greeting"])
    assert captured["name"]() == "Alice"
    assert captured["greeting"]() == "Hi"


def test_component_uses_defaults_for_missing_props():
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name="world", greeting="Hello"):
        captured["name"] = name
        captured["greeting"] = greeting

    Greet({"name": "Bob"})
    assert captured["name"]() == "Bob"
    assert captured["greeting"]() == "Hello"


def test_component_all_defaults():
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name="world"):
        captured["name"] = name

    Greet({})
    assert captured["name"]() == "world"


def test_component_ignores_extra_props():
    """Props not in the function signature are silently ignored at the call surface."""
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name="world"):
        captured["name"] = name

    Greet({"name": "Alice", "id": 42, "style": "bold"})
    assert set(captured.keys()) == {"name"}
    assert captured["name"]() == "Alice"


def test_component_children_param():
    from wybthon.component import component

    captured = {}

    @component
    def Wrapper(children=None):
        captured["children"] = children

    kids = ["child1", "child2"]
    Wrapper({"children": kids})
    assert callable(captured["children"])
    assert captured["children"]() == ["child1", "child2"]


def test_proxy_mode_for_single_positional_param():
    """A single positional param with no default receives the ReactiveProps proxy directly."""
    from wybthon.component import component
    from wybthon.reactivity import ReactiveProps

    captured = {}

    @component
    def Advanced(props):
        captured["props"] = props

    Advanced({"x": 1, "y": 2})
    assert isinstance(captured["props"], ReactiveProps)
    assert captured["props"].x() == 1
    assert captured["props"].y() == 2


# ---------------------------------------------------------------------------
# Tests — rendering with VDOM stubs
# ---------------------------------------------------------------------------


def test_component_renders_via_h(wyb, root_element):
    """@component function renders correctly when used with h()."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name="world"):
        # ``name`` is a callable — pass it as a child for an auto-hole,
        # or call it once for a static value.
        return vdom.h("p", {}, "Hello, ", name, "!")

    vdom.render(vdom.h(Greet, {"name": "Alice"}), root_element)

    texts = collect_texts(root_element.element)
    assert "Alice" in texts
    assert "Hello, " in texts


def test_component_renders_with_defaults(wyb, root_element):
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name="world"):
        return vdom.h("p", {}, "Hello, ", name, "!")

    vdom.render(vdom.h(Greet, {}), root_element)

    texts = collect_texts(root_element.element)
    assert "world" in texts


def test_component_direct_call_returns_vnode(wyb):
    """Calling a @component with kwargs directly returns a VNode."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name="world"):
        return vdom.h("p", {}, name)

    result = Greet(name="Direct")
    assert isinstance(result, vdom.VNode)
    assert result.props.get("name") == "Direct"


def test_component_direct_call_renders(wyb, root_element):
    """A VNode from a direct call renders correctly."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name="world"):
        return vdom.h("p", {}, "Hello, ", name, "!")

    vnode = Greet(name="Direct")
    vdom.render(vnode, root_element)

    texts = collect_texts(root_element.element)
    assert "Direct" in texts


def test_component_direct_call_no_args(wyb, root_element):
    """Calling @component() with no args uses all defaults."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name="world"):
        return vdom.h("p", {}, "Hello, ", name, "!")

    vdom.render(Greet(), root_element)

    texts = collect_texts(root_element.element)
    assert "world" in texts


def test_component_direct_call_with_children(wyb, root_element):
    """Positional args in direct calls become children."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Wrapper(title="", children=None):
        kids = children() or []
        return vdom.h("div", {}, vdom.h("h3", {}, title), *kids)

    child1 = vdom.h("p", {}, "child one")
    child2 = vdom.h("p", {}, "child two")
    vdom.render(Wrapper(child1, child2, title="Card"), root_element)

    texts = collect_texts(root_element.element)
    assert "Card" in texts
    assert "child one" in texts
    assert "child two" in texts


def test_component_with_create_signal(wyb, root_element):
    """@component works with create_signal (stateful pattern)."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    setter_ref = [None]

    @comp_mod.component
    def Counter(initial=0):
        # ``initial`` is a getter; call inside ``untrack`` so we don't
        # subscribe to it (and to silence the dev warning).
        seed = reactivity.untrack(initial)
        count, set_count = reactivity.create_signal(seed)
        setter_ref[0] = set_count
        return vdom.h("p", {}, "Count: ", count)

    vdom.render(vdom.h(Counter, {"initial": 10}), root_element)
    assert "Count: " in collect_texts(root_element.element)
    assert "10" in collect_texts(root_element.element)

    setter_ref[0](20)
    time.sleep(0.05)

    assert "20" in collect_texts(root_element.element)


def test_component_with_create_effect(wyb, root_element):
    """@component works with create_effect."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    log = []

    @comp_mod.component
    def EffectComp():
        reactivity.create_effect(lambda: log.append("effect"))
        return vdom.h("p", {}, "hello")

    vdom.render(vdom.h(EffectComp, {}), root_element)

    assert "effect" in log


def test_component_with_memo(wyb, root_element):
    """@component works when wrapped with memo()."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    child_renders = [0]
    parent_setter = [None]
    stable_label = "stable"

    @comp_mod.component
    def Child(label=""):
        child_renders[0] += 1
        return vdom.h("span", {}, "child:", label)

    MemoChild = vdom.memo(Child)

    @comp_mod.component
    def Parent():
        count, set_count = reactivity.create_signal(0)
        parent_setter[0] = set_count
        return vdom.h(
            "div",
            {},
            vdom.h("p", {}, count),
            vdom.h(MemoChild, {"label": stable_label}),
        )

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1

    parent_setter[0](1)
    time.sleep(0.05)

    assert child_renders[0] == 1


def test_component_no_params(wyb, root_element):
    """@component with no parameters works correctly."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Divider():
        return vdom.h("hr", {})

    vdom.render(vdom.h(Divider, {}), root_element)

    assert root_element.element.childNodes[0].tag == "hr"


def test_component_nested(wyb, root_element):
    """Nested @component functions work correctly."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Inner(value="inner"):
        return vdom.h("span", {}, value)

    @comp_mod.component
    def Outer(label="outer"):
        return vdom.h(
            "div",
            {},
            vdom.h("p", {}, label),
            vdom.h(Inner, {"value": "nested"}),
        )

    vdom.render(vdom.h(Outer, {"label": "parent"}), root_element)

    texts = collect_texts(root_element.element)
    assert "parent" in texts
    assert "nested" in texts


def test_component_runs_once_static_prop_capture(wyb, root_element):
    """Calling a prop accessor at setup captures its value statically.

    The component body still runs only once on mount.  To get reactive
    updates, pass the accessor itself into the VNode tree (auto-hole).
    """
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    child_renders = [0]
    parent_setter = [None]

    @comp_mod.component
    def Child(count=0):
        child_renders[0] += 1
        # Eager unwrap → static capture
        snapshot = reactivity.untrack(count)
        return vdom.h("span", {}, f"count={snapshot}")

    @comp_mod.component
    def Parent():
        val, set_val = reactivity.create_signal(0)
        parent_setter[0] = set_val
        return vdom.h("div", {}, vdom.h(Child, {"count": val}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1
    assert "count=0" in collect_texts(root_element.element)

    parent_setter[0](5)
    time.sleep(0.1)

    assert child_renders[0] == 1, "child body must not re-run"
    assert "count=0" in collect_texts(root_element.element), "static read keeps old value"


def test_component_re_renders_via_reactive_prop(wyb, root_element):
    """Passing the prop accessor into the tree creates an auto-hole."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    child_renders = [0]
    parent_setter = [None]

    @comp_mod.component
    def Child(count=0):
        child_renders[0] += 1
        # Pass the accessor → reactive auto-hole
        return vdom.h("span", {}, "count=", count)

    @comp_mod.component
    def Parent():
        val, set_val = reactivity.create_signal(0)
        parent_setter[0] = set_val
        return vdom.h("div", {}, vdom.h(Child, {"count": val}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1
    assert "0" in collect_texts(root_element.element)

    parent_setter[0](5)
    time.sleep(0.1)

    assert child_renders[0] == 1, "body still runs only once"
    assert "5" in collect_texts(root_element.element), "auto-hole updates the DOM"


def test_component_exported_from_package():
    """The component decorator is accessible from the top-level package."""
    from wybthon.component import component

    assert callable(component)


def test_component_reactive_props_update_via_get_props(wyb, root_element):
    """``get_props()`` returns the reactive proxy for advanced cases."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    parent_setter = [None]

    @comp_mod.component
    def Display(message="default"):
        # Identical to passing the accessor; this path also exercises
        # ``get_props()`` for advanced use.
        props = reactivity.get_props()
        return vdom.h("p", {}, props["message"])

    @comp_mod.component
    def Parent():
        msg, set_msg = reactivity.create_signal("hello")
        parent_setter[0] = set_msg
        return vdom.h("div", {}, vdom.h(Display, {"message": msg}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert "hello" in collect_texts(root_element.element)

    parent_setter[0]("goodbye")
    time.sleep(0.1)
    assert "goodbye" in collect_texts(root_element.element)


def test_create_effect_prev_value(wyb, root_element):
    """create_effect passes previous return value to callback when it accepts a parameter."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    log = []
    setter_ref = [None]

    @comp_mod.component
    def MyComp():
        count, set_count = reactivity.create_signal(0)
        setter_ref[0] = set_count

        def my_effect(prev):
            log.append(("prev", prev, "cur", count()))
            return count()

        reactivity.create_effect(my_effect)
        return vdom.h("p", {}, count)

    vdom.render(vdom.h(MyComp, {}), root_element)
    assert log == [("prev", None, "cur", 0)]

    setter_ref[0](5)
    time.sleep(0.05)
    assert log[-1] == ("prev", 0, "cur", 5)

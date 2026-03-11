"""Tests for the @component decorator."""

import time

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401

# ---------------------------------------------------------------------------
# Tests — pure decorator behaviour (no browser stubs needed)
# ---------------------------------------------------------------------------


def test_component_has_marker():
    from wybthon.component import component

    @component
    def Greet(name: str = "world"):
        pass

    assert getattr(Greet, "_wyb_component", False) is True


def test_component_preserves_name():
    from wybthon.component import component

    @component
    def MyWidget(label: str = ""):
        pass

    assert MyWidget.__name__ == "MyWidget"


def test_component_extracts_kwargs_from_dict():
    """When called with a single props dict (VDOM engine path), kwargs are extracted."""
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name: str = "world", greeting: str = "Hello"):
        captured["name"] = name
        captured["greeting"] = greeting

    Greet({"name": "Alice", "greeting": "Hi"})
    assert captured == {"name": "Alice", "greeting": "Hi"}


def test_component_uses_defaults_for_missing_props():
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name: str = "world", greeting: str = "Hello"):
        captured["name"] = name
        captured["greeting"] = greeting

    Greet({"name": "Bob"})
    assert captured == {"name": "Bob", "greeting": "Hello"}


def test_component_all_defaults():
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name: str = "world"):
        captured["name"] = name

    Greet({})
    assert captured == {"name": "world"}


def test_component_ignores_extra_props():
    """Props not in the function signature are silently ignored."""
    from wybthon.component import component

    captured = {}

    @component
    def Greet(name: str = "world"):
        captured["name"] = name

    Greet({"name": "Alice", "id": 42, "style": "bold"})
    assert captured == {"name": "Alice"}


def test_component_children_param():
    from wybthon.component import component

    captured = {}

    @component
    def Wrapper(children=None):
        captured["children"] = children

    Greet_children = ["child1", "child2"]
    Wrapper({"children": Greet_children})
    assert captured["children"] == ["child1", "child2"]


# ---------------------------------------------------------------------------
# Tests — rendering with VDOM stubs
# ---------------------------------------------------------------------------


def test_component_renders_via_h(wyb, root_element):
    """@component function renders correctly when used with h()."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name: str = "world"):
        return vdom.h("p", {}, f"Hello, {name}!")

    vdom.render(vdom.h(Greet, {"name": "Alice"}), root_element)

    texts = collect_texts(root_element.element)
    assert "Hello, Alice!" in texts


def test_component_renders_with_defaults(wyb, root_element):
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name: str = "world"):
        return vdom.h("p", {}, f"Hello, {name}!")

    vdom.render(vdom.h(Greet, {}), root_element)

    texts = collect_texts(root_element.element)
    assert "Hello, world!" in texts


def test_component_direct_call_returns_vnode(wyb):
    """Calling a @component with kwargs directly returns a VNode."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name: str = "world"):
        return vdom.h("p", {}, f"Hello, {name}!")

    result = Greet(name="Direct")
    assert isinstance(result, vdom.VNode)
    assert result.props.get("name") == "Direct"


def test_component_direct_call_renders(wyb, root_element):
    """A VNode from a direct call renders correctly."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name: str = "world"):
        return vdom.h("p", {}, f"Hello, {name}!")

    vnode = Greet(name="Direct")
    vdom.render(vnode, root_element)

    texts = collect_texts(root_element.element)
    assert "Hello, Direct!" in texts


def test_component_direct_call_no_args(wyb, root_element):
    """Calling @component() with no args uses all defaults."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Greet(name: str = "world"):
        return vdom.h("p", {}, f"Hello, {name}!")

    vdom.render(Greet(), root_element)

    texts = collect_texts(root_element.element)
    assert "Hello, world!" in texts


def test_component_direct_call_with_children(wyb, root_element):
    """Positional args in direct calls become children."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]

    @comp_mod.component
    def Wrapper(title: str = "", children=None):
        kids = children if children else []
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
    render_log = []

    @comp_mod.component
    def Counter(initial: int = 0):
        count, set_count = reactivity.create_signal(initial)
        setter_ref[0] = set_count

        def render():
            val = count()
            render_log.append(val)
            return vdom.h("p", {}, f"Count: {val}")

        return render

    vdom.render(vdom.h(Counter, {"initial": 10}), root_element)

    assert render_log == [10]
    assert "Count: 10" in collect_texts(root_element.element)

    setter_ref[0](20)
    time.sleep(0.05)

    assert render_log[-1] == 20
    assert "Count: 20" in collect_texts(root_element.element)


def test_component_with_create_effect(wyb, root_element):
    """@component works with create_effect."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    log = []

    @comp_mod.component
    def EffectComp():
        reactivity.create_effect(lambda: log.append("effect"))

        def render():
            return vdom.h("p", {}, "hello")

        return render

    vdom.render(vdom.h(EffectComp, {}), root_element)

    assert "effect" in log


def test_component_with_memo(wyb, root_element):
    """@component works when wrapped with memo()."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    child_renders = [0]
    parent_setter = [None]
    stable_label = "stable"

    @comp_mod.component
    def Child(label: str = ""):
        child_renders[0] += 1
        return vdom.h("span", {}, f"child:{label}")

    MemoChild = vdom.memo(Child)

    def Parent(props):
        count, set_count = reactivity.create_signal(0)
        parent_setter[0] = set_count

        def render():
            _ = count()
            return vdom.h("div", {}, vdom.h("p", {}, str(count())), vdom.h(MemoChild, {"label": stable_label}))

        return render

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
    def Inner(value: str = "inner"):
        return vdom.h("span", {}, value)

    @comp_mod.component
    def Outer(label: str = "outer"):
        return vdom.h("div", {}, vdom.h("p", {}, label), vdom.h(Inner, {"value": "nested"}))

    vdom.render(vdom.h(Outer, {"label": "parent"}), root_element)

    texts = collect_texts(root_element.element)
    assert "parent" in texts
    assert "nested" in texts


def test_component_re_renders_on_prop_change(wyb, root_element):
    """Stateless @component re-renders when parent passes new props."""
    vdom, reactivity, comp_mod = wyb["vdom"], wyb["reactivity"], wyb["component"]

    child_renders = [0]
    parent_setter = [None]

    @comp_mod.component
    def Child(count: int = 0):
        child_renders[0] += 1
        return vdom.h("span", {}, f"count={count}")

    def Parent(props):
        val, set_val = reactivity.create_signal(0)
        parent_setter[0] = set_val

        def render():
            return vdom.h("div", {}, vdom.h(Child, {"count": val()}))

        return render

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_renders[0] == 1
    assert "count=0" in collect_texts(root_element.element)

    parent_setter[0](5)
    time.sleep(0.05)

    assert child_renders[0] == 2
    assert "count=5" in collect_texts(root_element.element)


def test_component_exported_from_package():
    """The component decorator is accessible from the top-level package."""
    from wybthon.component import component

    assert callable(component)

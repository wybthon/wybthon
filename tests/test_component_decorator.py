"""Tests for the @component decorator."""

import importlib
import sys
import time
from types import ModuleType

import wybthon as _wybthon_pkg  # noqa: F401

# ---------------------------------------------------------------------------
# DOM stubs (same pattern as other test files)
# ---------------------------------------------------------------------------


class _ClassList:
    def __init__(self):
        self._set = set()

    def add(self, name):
        self._set.add(name)

    def remove(self, name):
        self._set.discard(name)

    def contains(self, name):
        return name in self._set


class _Style:
    def __init__(self):
        self._props = {}

    def setProperty(self, name, value):
        self._props[name] = str(value)

    def removeProperty(self, name):
        self._props.pop(name, None)


class _Node:
    def __init__(self, tag=None, text=None):
        self.tag = tag
        self.nodeValue = text
        self._is_text = text is not None
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = _ClassList()
        self.style = _Style()
        self.value = ""
        self.checked = False

    @property
    def nextSibling(self):
        if self.parentNode is None:
            return None
        try:
            idx = self.parentNode.childNodes.index(self)
        except ValueError:
            return None
        return self.parentNode.childNodes[idx + 1] if idx + 1 < len(self.parentNode.childNodes) else None

    def appendChild(self, node):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        if anchor is None:
            self.childNodes.append(node)
            return node
        try:
            idx = self.childNodes.index(anchor)
        except ValueError:
            self.childNodes.append(node)
            return node
        self.childNodes.insert(idx, node)
        return node

    def removeChild(self, node):
        try:
            self.childNodes.remove(node)
            node.parentNode = None
        except ValueError:
            pass
        return node

    def setAttribute(self, name, value):
        self.attributes[name] = str(value)

    def getAttribute(self, name):
        return self.attributes.get(name)

    def removeAttribute(self, name):
        self.attributes.pop(name, None)


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return _Node(tag=tag)

    def createTextNode(self, text):
        return _Node(text=str(text))

    def addEventListener(self, event_type, proxy):
        self._listeners.setdefault(event_type, set()).add(proxy)

    def removeEventListener(self, event_type, proxy):
        s = self._listeners.get(event_type)
        if s is not None and proxy in s:
            s.remove(proxy)

    def querySelector(self, sel):
        return _Node(tag="div")

    def querySelectorAll(self, sel):
        return []


def _install_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide
    sys.modules["pyodide.ffi"] = ffi
    setattr(pyodide, "ffi", ffi)
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _reload_modules():
    dom = importlib.import_module("wybthon.dom")
    importlib.reload(dom)
    events = importlib.import_module("wybthon.events")
    importlib.reload(events)
    comp_mod = importlib.import_module("wybthon.component")
    importlib.reload(comp_mod)
    context = importlib.import_module("wybthon.context")
    importlib.reload(context)
    reactivity = importlib.import_module("wybthon.reactivity")
    importlib.reload(reactivity)
    hooks = importlib.import_module("wybthon.hooks")
    importlib.reload(hooks)
    vdom = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom)
    return vdom, hooks, dom, comp_mod


def _collect_texts(node):
    out = []
    if getattr(node, "_is_text", False):
        out.append(node.nodeValue)
    for ch in getattr(node, "childNodes", []):
        out.extend(_collect_texts(ch))
    return out


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


def test_component_renders_via_h():
    """@component function renders correctly when used with h()."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Greet(name: str = "world"):
            return vdom.h("p", {}, f"Hello, {name}!")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Greet, {"name": "Alice"}), root)

        texts = _collect_texts(root.element)
        assert "Hello, Alice!" in texts
    finally:
        _restore(saved)


def test_component_renders_with_defaults():
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Greet(name: str = "world"):
            return vdom.h("p", {}, f"Hello, {name}!")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Greet, {}), root)

        texts = _collect_texts(root.element)
        assert "Hello, world!" in texts
    finally:
        _restore(saved)


def test_component_direct_call_returns_vnode():
    """Calling a @component with kwargs directly returns a VNode."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Greet(name: str = "world"):
            return vdom.h("p", {}, f"Hello, {name}!")

        result = Greet(name="Direct")
        assert isinstance(result, vdom.VNode)
        assert result.props.get("name") == "Direct"
    finally:
        _restore(saved)


def test_component_direct_call_renders():
    """A VNode from a direct call renders correctly."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Greet(name: str = "world"):
            return vdom.h("p", {}, f"Hello, {name}!")

        root = dom.Element(node=_Node(tag="div"))
        vnode = Greet(name="Direct")
        vdom.render(vnode, root)

        texts = _collect_texts(root.element)
        assert "Hello, Direct!" in texts
    finally:
        _restore(saved)


def test_component_direct_call_no_args():
    """Calling @component() with no args uses all defaults."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Greet(name: str = "world"):
            return vdom.h("p", {}, f"Hello, {name}!")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(Greet(), root)

        texts = _collect_texts(root.element)
        assert "Hello, world!" in texts
    finally:
        _restore(saved)


def test_component_direct_call_with_children():
    """Positional args in direct calls become children."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Wrapper(title: str = "", children=None):
            kids = children if children else []
            return vdom.h("div", {}, vdom.h("h3", {}, title), *kids)

        child1 = vdom.h("p", {}, "child one")
        child2 = vdom.h("p", {}, "child two")
        root = dom.Element(node=_Node(tag="div"))
        vdom.render(Wrapper(child1, child2, title="Card"), root)

        texts = _collect_texts(root.element)
        assert "Card" in texts
        assert "child one" in texts
        assert "child two" in texts
    finally:
        _restore(saved)


def test_component_with_use_state():
    """@component works with use_state hooks."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        setter_ref = [None]
        render_log = []

        @comp_mod.component
        def Counter(initial: int = 0):
            count, set_count = hooks.use_state(initial)
            setter_ref[0] = set_count
            render_log.append(count)
            return vdom.h("p", {}, f"Count: {count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {"initial": 10}), root)

        assert render_log == [10]
        assert "Count: 10" in _collect_texts(root.element)

        setter_ref[0](20)
        time.sleep(0.05)

        assert render_log[-1] == 20
        assert "Count: 20" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_component_with_use_effect():
    """@component works with use_effect hooks."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        log = []

        @comp_mod.component
        def EffectComp():
            hooks.use_effect(lambda: log.append("mounted"), [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(EffectComp, {}), root)

        assert "mounted" in log
    finally:
        _restore(saved)


def test_component_with_memo():
    """@component works when wrapped with memo()."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        child_renders = [0]
        parent_setter = [None]
        stable_label = "stable"

        @comp_mod.component
        def Child(label: str = ""):
            child_renders[0] += 1
            return vdom.h("span", {}, f"child:{label}")

        MemoChild = vdom.memo(Child)

        def Parent(props):
            count, set_count = hooks.use_state(0)
            parent_setter[0] = set_count
            return vdom.h("div", {}, vdom.h("p", {}, str(count)), vdom.h(MemoChild, {"label": stable_label}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        assert child_renders[0] == 1

        parent_setter[0](1)
        time.sleep(0.05)

        assert child_renders[0] == 1
    finally:
        _restore(saved)


def test_component_no_params():
    """@component with no parameters works correctly."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Divider():
            return vdom.h("hr", {})

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Divider, {}), root)

        assert root.element.childNodes[0].tag == "hr"
    finally:
        _restore(saved)


def test_component_nested():
    """Nested @component functions work correctly."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        @comp_mod.component
        def Inner(value: str = "inner"):
            return vdom.h("span", {}, value)

        @comp_mod.component
        def Outer(label: str = "outer"):
            return vdom.h("div", {}, vdom.h("p", {}, label), vdom.h(Inner, {"value": "nested"}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Outer, {"label": "parent"}), root)

        texts = _collect_texts(root.element)
        assert "parent" in texts
        assert "nested" in texts
    finally:
        _restore(saved)


def test_component_re_renders_on_prop_change():
    """@component re-renders when parent passes new props."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom, comp_mod = _reload_modules()

        child_renders = [0]
        parent_setter = [None]

        @comp_mod.component
        def Child(count: int = 0):
            child_renders[0] += 1
            return vdom.h("span", {}, f"count={count}")

        def Parent(props):
            val, set_val = hooks.use_state(0)
            parent_setter[0] = set_val
            return vdom.h("div", {}, vdom.h(Child, {"count": val}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        assert child_renders[0] == 1
        assert "count=0" in _collect_texts(root.element)

        parent_setter[0](5)
        time.sleep(0.05)

        assert child_renders[0] == 2
        assert "count=5" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_component_exported_from_package():
    """The component decorator is accessible from the top-level package."""
    from wybthon.component import component

    assert callable(component)

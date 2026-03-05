"""Tests for memo() – memoized function components."""

import importlib
import sys
import time
from types import ModuleType

import wybthon as _wybthon_pkg  # noqa: F401


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
    component = importlib.import_module("wybthon.component")
    importlib.reload(component)
    context = importlib.import_module("wybthon.context")
    importlib.reload(context)
    reactivity = importlib.import_module("wybthon.reactivity")
    importlib.reload(reactivity)
    hooks = importlib.import_module("wybthon.hooks")
    importlib.reload(hooks)
    vdom = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom)
    return vdom, hooks, dom


def _collect_texts(node):
    out = []
    if getattr(node, "_is_text", False):
        out.append(node.nodeValue)
    for ch in getattr(node, "childNodes", []):
        out.extend(_collect_texts(ch))
    return out


def test_memo_renders_initially():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        render_count = [0]

        def Display(props):
            render_count[0] += 1
            return vdom.h("p", {}, f"value={props.get('value')}")

        MemoDisplay = vdom.memo(Display)

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MemoDisplay, {"value": "A"}), root)

        assert render_count[0] == 1
        assert "value=A" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_memo_skips_rerender_same_props():
    """When parent re-renders but passes the same prop references, memo skips."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        child_renders = [0]
        parent_setter = [None]
        stable_value = "stable"

        def Child(props):
            child_renders[0] += 1
            return vdom.h("span", {}, f"child:{props.get('label')}")

        MemoChild = vdom.memo(Child)

        def Parent(props):
            count, set_count = hooks.use_state(0)
            parent_setter[0] = set_count
            return vdom.h("div", {}, vdom.h("p", {}, str(count)), vdom.h(MemoChild, {"label": stable_value}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        assert child_renders[0] == 1

        parent_setter[0](1)
        time.sleep(0.05)

        # Parent re-rendered but memo child should NOT have re-rendered
        assert child_renders[0] == 1
    finally:
        _restore(saved)


def test_memo_rerenders_on_changed_props():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        child_renders = [0]
        parent_setter = [None]

        def Child(props):
            child_renders[0] += 1
            return vdom.h("span", {}, f"count={props.get('count')}")

        MemoChild = vdom.memo(Child)

        def Parent(props):
            count, set_count = hooks.use_state(0)
            parent_setter[0] = set_count
            return vdom.h("div", {}, vdom.h(MemoChild, {"count": count}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        assert child_renders[0] == 1
        assert "count=0" in _collect_texts(root.element)

        parent_setter[0](1)
        time.sleep(0.05)

        # Props changed, memo child SHOULD re-render
        assert child_renders[0] == 2
        assert "count=1" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_memo_custom_comparison():
    """Custom are_props_equal can control when re-renders happen."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        child_renders = [0]
        parent_setter = [None]

        def Child(props):
            child_renders[0] += 1
            return vdom.h("span", {}, f"v={props.get('value')}")

        # Custom comparator ignores all differences
        MemoChild = vdom.memo(Child, are_props_equal=lambda old, new: True)

        def Parent(props):
            count, set_count = hooks.use_state(0)
            parent_setter[0] = set_count
            return vdom.h("div", {}, vdom.h(MemoChild, {"value": count}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        assert child_renders[0] == 1

        parent_setter[0](1)
        time.sleep(0.05)

        # Custom comparator always returns True, so child should NOT re-render
        assert child_renders[0] == 1
    finally:
        _restore(saved)


def test_memo_with_hooks():
    """Memo components should still work with hooks when they do re-render."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        child_setter = [None]

        def Child(props):
            local, set_local = hooks.use_state(0)
            child_setter[0] = set_local
            return vdom.h("span", {}, f"local={local}")

        MemoChild = vdom.memo(Child)

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MemoChild, {}), root)
        assert "local=0" in _collect_texts(root.element)

        child_setter[0](5)
        time.sleep(0.05)

        assert "local=5" in _collect_texts(root.element)
    finally:
        _restore(saved)

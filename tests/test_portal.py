"""Tests for create_portal – rendering children into a different container."""

import importlib
import sys
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


def test_portal_renders_into_target_container():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        root = dom.Element(node=_Node(tag="div"))
        portal_target = dom.Element(node=_Node(tag="div"))

        def App(props):
            return vdom.h(
                "div",
                {},
                vdom.h("p", {}, "In parent"),
                vdom.create_portal(vdom.h("p", {}, "In portal"), portal_target),
            )

        vdom.render(vdom.h(App, {}), root)

        parent_texts = _collect_texts(root.element)
        portal_texts = _collect_texts(portal_target.element)

        assert "In parent" in parent_texts
        assert "In portal" not in parent_texts
        assert "In portal" in portal_texts
    finally:
        _restore(saved)


def test_portal_renders_list_of_children():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        root = dom.Element(node=_Node(tag="div"))
        portal_target = dom.Element(node=_Node(tag="div"))

        children = [
            vdom.h("p", {}, "Child A"),
            vdom.h("p", {}, "Child B"),
        ]

        def App(props):
            return vdom.h(
                "div",
                {},
                vdom.create_portal(children, portal_target),
            )

        vdom.render(vdom.h(App, {}), root)

        portal_texts = _collect_texts(portal_target.element)
        assert "Child A" in portal_texts
        assert "Child B" in portal_texts
    finally:
        _restore(saved)


def test_portal_unmount_cleans_up():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        root = dom.Element(node=_Node(tag="div"))
        portal_target = dom.Element(node=_Node(tag="div"))

        def App(props):
            return vdom.h(
                "div",
                {},
                vdom.create_portal(vdom.h("span", {}, "Portal content"), portal_target),
            )

        tree = vdom.h(App, {})
        vdom.render(tree, root)

        assert "Portal content" in _collect_texts(portal_target.element)

        vdom._unmount(tree)
        assert "Portal content" not in _collect_texts(portal_target.element)
    finally:
        _restore(saved)


def test_portal_placeholder_in_parent():
    """Portal should leave an empty text placeholder in the parent container."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        root = dom.Element(node=_Node(tag="div"))
        portal_target = dom.Element(node=_Node(tag="div"))

        def App(props):
            return vdom.h(
                "div",
                {},
                vdom.h("p", {}, "Before"),
                vdom.create_portal(vdom.h("p", {}, "Modal"), portal_target),
                vdom.h("p", {}, "After"),
            )

        vdom.render(vdom.h(App, {}), root)

        parent_texts = _collect_texts(root.element)
        assert "Before" in parent_texts
        assert "After" in parent_texts
        assert "Modal" not in parent_texts
        assert "Modal" in _collect_texts(portal_target.element)
    finally:
        _restore(saved)

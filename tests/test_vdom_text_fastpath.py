import importlib
import sys
from types import ModuleType


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
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = _ClassList()
        self.style = _Style()

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
        # DOM semantics: moving an existing node removes it from its current parent first
        if getattr(node, "parentNode", None) is not None:
            try:
                p = node.parentNode
                p.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
        # DOM semantics: moving an existing node removes it from its current parent first
        if getattr(node, "parentNode", None) is not None:
            try:
                p = node.parentNode
                p.childNodes.remove(node)
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
            return node
        except ValueError:
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
        # Not needed for these tests
        return _Node(tag="div")

    def querySelectorAll(self, sel):
        return []


def _install_js_and_pyodide_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")

    def create_proxy(fn):
        return fn

    ffi.create_proxy = create_proxy
    sys.modules["pyodide"] = pyodide
    sys.modules["pyodide.ffi"] = ffi
    setattr(pyodide, "ffi", ffi)
    return saved, js_mod.document


def _restore_modules(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _texts_of_children(node):
    return [child.nodeValue for child in node.childNodes]


def test_text_node_fast_path_identity_and_update():
    saved, _doc = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        view1 = vdom_mod.h("div", {}, "hello")
        vdom_mod.render(view1, root)
        div1 = root.element.childNodes[0]
        assert len(div1.childNodes) == 1
        t1 = div1.childNodes[0]
        assert t1.nodeValue == "hello"

        view2 = vdom_mod.h("div", {}, "world")
        vdom_mod.render(view2, root)
        div2 = root.element.childNodes[0]
        t2 = div2.childNodes[0]
        assert t2 is t1
        assert t2.nodeValue == "world"
    finally:
        _restore_modules(saved)


def test_unkeyed_text_children_reorder_content_and_identity_reuse():
    saved, _doc = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        initial = ["A", "B", "C", "D"]
        view1 = vdom_mod.h("div", {}, *initial)
        vdom_mod.render(view1, root)
        div1 = root.element.childNodes[0]
        before_nodes = list(div1.childNodes)
        assert _texts_of_children(div1) == initial

        target = ["C", "A", "D", "B"]
        view2 = vdom_mod.h("div", {}, *target)
        vdom_mod.render(view2, root)
        div2 = root.element.childNodes[0]
        after_nodes = list(div2.childNodes)
        assert _texts_of_children(div2) == target

        # Ensure nodes were reused (no replacements), even if positions/content changed
        assert set(before_nodes) == set(after_nodes)
    finally:
        _restore_modules(saved)

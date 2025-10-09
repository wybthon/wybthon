import importlib
import sys
import time
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
    out = []
    for child in node.childNodes:
        # child may be <li> which contains a text node
        if child.childNodes:
            t = child.childNodes[0].nodeValue
        else:
            t = child.nodeValue
        out.append(t)
    return out


def test_keyed_reorder_reverse():
    saved, _doc = _install_js_and_pyodide_stubs()
    try:
        # Reload modules to pick up stubs
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        def make_view(order):
            return vdom_mod.h(
                "ul",
                {},
                *[vdom_mod.h("li", {"key": k}, k) for k in order],
            )

        initial = ["A", "B", "C", "D"]
        view1 = make_view(initial)
        vdom_mod.render(view1, root)
        ul = root.element.childNodes[0]
        assert _texts_of_children(ul) == initial

        # Capture identity of nodes by their text content
        initial_nodes = {t: ul.childNodes[i] for i, t in enumerate(initial)}

        # Reverse order
        reversed_order = list(reversed(initial))
        view2 = make_view(reversed_order)
        vdom_mod.render(view2, root)
        ul2 = root.element.childNodes[0]
        assert _texts_of_children(ul2) == reversed_order

        # Verify node identity reused for each key
        for t in reversed_order:
            assert ul2.childNodes[reversed_order.index(t)] is initial_nodes[t]
    finally:
        _restore_modules(saved)


def test_keyed_reorder_move_middle_to_front_and_insert_remove():
    saved, _doc = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        def make_view(order):
            return vdom_mod.h(
                "ul",
                {},
                *[vdom_mod.h("li", {"key": k}, k) for k in order],
            )

        initial = ["A", "B", "C", "D", "E"]
        vdom_mod.render(make_view(initial), root)
        ul = root.element.childNodes[0]
        assert _texts_of_children(ul) == initial
        initial_nodes = {t: ul.childNodes[i] for i, t in enumerate(initial)}

        # New order: move C to front, drop B, add F at end, swap D/E
        target = ["C", "A", "E", "D", "F"]
        vdom_mod.render(make_view(target), root)
        ul2 = root.element.childNodes[0]
        assert _texts_of_children(ul2) == target

        # Identity preserved for existing keys A,C,D,E
        for t in ["A", "C", "D", "E"]:
            idx = target.index(t)
            assert ul2.childNodes[idx] is initial_nodes[t]

        # F is new
        assert target[-1] == "F"
        assert ul2.childNodes[-1] is not initial_nodes.get("F")
    finally:
        _restore_modules(saved)


def test_keyed_reorder_micro_time_smoke():
    # A tiny smoke micro-benchmark asserting it runs fast enough in our stubbed env
    saved, _doc = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))
        N = 200
        keys = [f"k{i}" for i in range(N)]

        def make_view(order):
            return vdom_mod.h("ul", {}, *[vdom_mod.h("li", {"key": k}, k) for k in order])

        vdom_mod.render(make_view(keys), root)
        start = time.time()
        vdom_mod.render(make_view(list(reversed(keys))), root)
        elapsed = time.time() - start
        # This threshold is generous and only meant to catch pathological regressions
        assert elapsed < 0.3
    finally:
        _restore_modules(saved)

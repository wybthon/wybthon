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
        # Input-like properties for tests
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
                p = node.parentNode
                p.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
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
    return saved


def _restore_modules(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _first_child(container):
    return container.element.childNodes[0]


def test_style_set_update_and_clear():
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        # Initial styles
        view1 = vdom_mod.h("div", {"style": {"backgroundColor": "red", "fontSize": 14}})
        vdom_mod.render(view1, root)
        node = _first_child(root)
        assert node.style._props == {"background-color": "red", "font-size": "14"}

        # Update: remove backgroundColor, change fontSize, add marginTop
        view2 = vdom_mod.h("div", {"style": {"fontSize": 16, "marginTop": 2}})
        vdom_mod.render(view2, root)
        node = _first_child(root)
        assert node.style._props == {"font-size": "16", "margin-top": "2"}
        assert "background-color" not in node.style._props

        # Clear styles by setting style to None
        view3 = vdom_mod.h("div", {"style": None})
        vdom_mod.render(view3, root)
        node = _first_child(root)
        assert node.style._props == {}
    finally:
        _restore_modules(saved)


def test_dataset_set_update_and_clear():
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        # Initial dataset
        view1 = vdom_mod.h("div", {"dataset": {"id": "x", "role": "button"}})
        vdom_mod.render(view1, root)
        node = _first_child(root)
        assert node.getAttribute("data-id") == "x"
        assert node.getAttribute("data-role") == "button"

        # Update: change id, remove role
        view2 = vdom_mod.h("div", {"dataset": {"id": "y"}})
        vdom_mod.render(view2, root)
        node = _first_child(root)
        assert node.getAttribute("data-id") == "y"
        assert node.getAttribute("data-role") is None

        # Clear dataset with non-dict
        view3 = vdom_mod.h("div", {"dataset": "oops"})
        vdom_mod.render(view3, root)
        node = _first_child(root)
        assert node.getAttribute("data-id") is None
    finally:
        _restore_modules(saved)


def test_value_property_update_and_removal():
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        # Initial value
        view1 = vdom_mod.h("input", {"value": "abc"})
        vdom_mod.render(view1, root)
        node = _first_child(root)
        assert node.value == "abc"

        # Update value (number becomes string)
        view2 = vdom_mod.h("input", {"value": 42})
        vdom_mod.render(view2, root)
        node = _first_child(root)
        assert node.value == "42"

        # Remove value prop → should clear to empty string
        view3 = vdom_mod.h("input", {})
        vdom_mod.render(view3, root)
        node = _first_child(root)
        assert node.value == ""
    finally:
        _restore_modules(saved)


def test_checked_property_toggle_and_removal():
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))

        # Initially checked
        view1 = vdom_mod.h("input", {"checked": True})
        vdom_mod.render(view1, root)
        node = _first_child(root)
        assert node.checked is True

        # Toggle to False
        view2 = vdom_mod.h("input", {"checked": False})
        vdom_mod.render(view2, root)
        node = _first_child(root)
        assert node.checked is False

        # Remove checked prop → should clear to False
        view3 = vdom_mod.h("input", {})
        vdom_mod.render(view3, root)
        node = _first_child(root)
        assert node.checked is False
    finally:
        _restore_modules(saved)

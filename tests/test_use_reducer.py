"""Tests for use_reducer hook."""

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


def _counter_reducer(state, action):
    if action == "increment":
        return state + 1
    if action == "decrement":
        return state - 1
    if action == "reset":
        return 0
    return state


def test_use_reducer_initial_render():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        render_log = []

        def Counter(props):
            count, dispatch = hooks.use_reducer(_counter_reducer, 0)
            render_log.append(count)
            return vdom.h("p", {}, f"Count: {count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {}), root)

        assert render_log == [0]
        assert "Count: 0" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_use_reducer_dispatch():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        dispatch_ref = [None]
        render_log = []

        def Counter(props):
            count, dispatch = hooks.use_reducer(_counter_reducer, 0)
            dispatch_ref[0] = dispatch
            render_log.append(count)
            return vdom.h("p", {}, f"Count: {count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {}), root)
        assert render_log == [0]

        dispatch_ref[0]("increment")
        time.sleep(0.05)
        assert render_log[-1] == 1

        dispatch_ref[0]("increment")
        time.sleep(0.05)
        assert render_log[-1] == 2

        dispatch_ref[0]("decrement")
        time.sleep(0.05)
        assert render_log[-1] == 1

        dispatch_ref[0]("reset")
        time.sleep(0.05)
        assert render_log[-1] == 0
    finally:
        _restore(saved)


def test_use_reducer_with_init():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        init_calls = [0]

        def init_fn(arg):
            init_calls[0] += 1
            return {"count": arg, "step": 1}

        def reducer(state, action):
            if action == "step":
                return {**state, "count": state["count"] + state["step"]}
            return state

        dispatch_ref = [None]
        state_log = []

        def StepCounter(props):
            state, dispatch = hooks.use_reducer(reducer, 10, init=init_fn)
            dispatch_ref[0] = dispatch
            state_log.append(state)
            return vdom.h("p", {}, f"count={state['count']}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(StepCounter, {}), root)

        assert init_calls[0] == 1
        assert state_log[0] == {"count": 10, "step": 1}
        assert "count=10" in _collect_texts(root.element)

        dispatch_ref[0]("step")
        time.sleep(0.05)
        assert state_log[-1] == {"count": 11, "step": 1}
    finally:
        _restore(saved)


def test_use_reducer_dispatch_stable_identity():
    """The dispatch function should be the same reference across renders."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        dispatch_ids = []
        setter_ref = [None]

        def MyComp(props):
            _count, dispatch = hooks.use_reducer(_counter_reducer, 0)
            # Also have a useState to trigger re-renders independently
            val, setter = hooks.use_state(0)
            setter_ref[0] = setter
            dispatch_ids.append(id(dispatch))
            return vdom.h("p", {}, "ok")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)

        setter_ref[0](1)
        time.sleep(0.05)

        assert len(dispatch_ids) == 2
        assert dispatch_ids[0] == dispatch_ids[1]
    finally:
        _restore(saved)

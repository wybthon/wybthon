import importlib
import random
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
        # Emulate browser: moving an existing node removes it from its current parent first
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
        # Emulate browser: moving an existing node removes it from its current parent first
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
        return _Node(tag="div")

    def querySelectorAll(self, sel):
        return []


def _install_js_and_pyodide_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None

    # Minimal window and related APIs used by router
    class _History:
        def __init__(self, win):
            self._win = win

        def pushState(self, _a, _b, path):
            self._win.location.pathname = str(path)

        def replaceState(self, _a, _b, path):
            self._win.location.pathname = str(path)

    class _Location:
        def __init__(self):
            self.pathname = "/"
            self.search = ""

    class _Window:
        def __init__(self):
            self._listeners = {}
            self.location = _Location()
            self.history = _History(self)

        def addEventListener(self, event_type, proxy):
            self._listeners.setdefault(event_type, set()).add(proxy)

    js_mod.window = _Window()
    try:
        from urllib.parse import unquote as _unquote

        js_mod.decodeURIComponent = lambda s: _unquote(s)
    except Exception:
        js_mod.decodeURIComponent = lambda s: s
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


def _prepare(root, vdom_mod, dom_mod, keys):
    def make_view(order):
        return vdom_mod.h("ul", {}, *[vdom_mod.h("li", {"key": k}, k) for k in order])

    vdom_mod.render(make_view(keys), root)
    return make_view


def bench_reverse(N: int, rounds: int = 3):
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))
        keys = [f"k{i}" for i in range(N)]
        make_view = _prepare(root, vdom_mod, dom_mod, keys)

        # Warmup
        vdom_mod.render(make_view(list(reversed(keys))), root)
        vdom_mod.render(make_view(keys), root)

        times = []
        for _ in range(rounds):
            start = time.time()
            vdom_mod.render(make_view(list(reversed(keys))), root)
            times.append(time.time() - start)
            # flip back
            vdom_mod.render(make_view(keys), root)
        return sum(times) / len(times)
    finally:
        _restore_modules(saved)


def bench_shuffle(N: int, rounds: int = 3):
    saved = _install_js_and_pyodide_stubs()
    try:
        dom_mod = importlib.import_module("wybthon.dom")
        importlib.reload(dom_mod)
        vdom_mod = importlib.import_module("wybthon.vdom")
        importlib.reload(vdom_mod)

        root = dom_mod.Element(node=_Node(tag="div"))
        base = [f"k{i}" for i in range(N)]
        make_view = _prepare(root, vdom_mod, dom_mod, base)

        times = []
        for _ in range(rounds):
            order = base[:]
            random.shuffle(order)
            start = time.time()
            vdom_mod.render(make_view(order), root)
            times.append(time.time() - start)
        return sum(times) / len(times)
    finally:
        _restore_modules(saved)


def main():
    sizes = [200, 500]
    print("Keyed reorder micro-benchmarks (stubbed DOM)")
    for n in sizes:
        t_rev = bench_reverse(n)
        t_shuf = bench_shuffle(n)
        print(f"N={n:4d}: reverse avg {t_rev*1000:.1f} ms | shuffle avg {t_shuf*1000:.1f} ms")


if __name__ == "__main__":
    main()

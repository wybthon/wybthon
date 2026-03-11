"""Shared test fixtures for Wybthon browser/VDOM tests.

Provides in-memory DOM stub classes and pytest fixtures that install fake
``js`` / ``pyodide`` modules into ``sys.modules``, making it possible to
test the VDOM reconciler, signals, components, and other browser-dependent
modules without a real browser environment.
"""

import importlib
import sys
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# DOM stub classes
# ---------------------------------------------------------------------------


class StubClassList:
    def __init__(self):
        self._set = set()

    def add(self, name):
        self._set.add(name)

    def remove(self, name):
        self._set.discard(name)

    def contains(self, name):
        return name in self._set


class StubStyle:
    def __init__(self):
        self._props = {}

    def setProperty(self, name, value):
        self._props[name] = str(value)

    def removeProperty(self, name):
        self._props.pop(name, None)


class StubNode:
    """In-memory stub for a browser DOM node."""

    def __init__(self, tag=None, text=None):
        self.tag = tag
        self.nodeValue = text
        self._is_text = text is not None
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = StubClassList()
        self.style = StubStyle()
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


class StubDocument:
    """In-memory stub for the browser ``document`` object."""

    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return StubNode(tag=tag)

    def createTextNode(self, text):
        return StubNode(text=str(text))

    def addEventListener(self, event_type, proxy):
        self._listeners.setdefault(event_type, set()).add(proxy)

    def removeEventListener(self, event_type, proxy):
        s = self._listeners.get(event_type)
        if s is not None and proxy in s:
            s.remove(proxy)

    def querySelector(self, sel):
        return StubNode(tag="div")

    def querySelectorAll(self, sel):
        return []


# ---------------------------------------------------------------------------
# Module stub management
# ---------------------------------------------------------------------------

_STUB_MODULE_NAMES = ("js", "pyodide", "pyodide.ffi")


def install_browser_stubs():
    """Install fake ``js`` and ``pyodide`` modules into ``sys.modules``.

    Returns ``(saved_modules_dict, stub_document)`` so callers can restore
    later via :func:`restore_modules`.
    """
    saved = {name: sys.modules.get(name) for name in _STUB_MODULE_NAMES}

    js_mod = ModuleType("js")
    doc = StubDocument()
    js_mod.document = doc
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide_mod = ModuleType("pyodide")
    ffi_mod = ModuleType("pyodide.ffi")
    ffi_mod.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide_mod
    sys.modules["pyodide.ffi"] = ffi_mod
    setattr(pyodide_mod, "ffi", ffi_mod)

    return saved, doc


def restore_modules(saved):
    """Restore original ``sys.modules`` entries from a saved dict."""
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def reload_wybthon_modules():
    """Reload all browser-dependent wybthon submodules against current stubs.

    Returns a dict with keys ``vdom``, ``dom``, ``component``, ``events``,
    ``context``, ``reactivity`` pointing to the freshly reloaded module objects.
    """
    mods = {}
    # Only reload modules that import from ``js`` at the top level.
    # Other modules are loaded once and shared, which keeps ``isinstance``
    # checks consistent (e.g. _PortalComponent inherits the same Component
    # class that the reconciler imports).
    for name in ("dom", "events", "reconciler", "vdom"):
        mod = importlib.import_module(f"wybthon.{name}")
        importlib.reload(mod)
        mods[name] = mod
    # Also expose non-reloaded modules so tests can access them.
    for name in ("component", "context", "reactivity", "props", "vnode"):
        mods[name] = importlib.import_module(f"wybthon.{name}")
    return mods


# ---------------------------------------------------------------------------
# Tree traversal helpers
# ---------------------------------------------------------------------------


def collect_texts(node):
    """Recursively collect all text-node values from a :class:`StubNode` tree."""
    out = []
    if getattr(node, "_is_text", False):
        out.append(node.nodeValue)
    for ch in getattr(node, "childNodes", []):
        out.extend(collect_texts(ch))
    return out


def texts_of_children(node):
    """Return the text content of each direct child of *node*.

    Handles both plain text nodes and element nodes whose first child is text.
    """
    out = []
    for child in node.childNodes:
        if child.childNodes:
            t = child.childNodes[0].nodeValue
        else:
            t = child.nodeValue
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def browser_stubs():
    """Install fake browser modules and tear them down after the test.

    Yields ``(saved_modules, stub_document)``.
    """
    saved, doc = install_browser_stubs()
    try:
        yield saved, doc
    finally:
        restore_modules(saved)


@pytest.fixture()
def wyb(browser_stubs):
    """Install browser stubs, reload wybthon modules, and yield a namespace.

    The yielded dict has keys: ``vdom``, ``dom``, ``component``, ``events``,
    ``context``, ``reactivity``, ``props``, ``reconciler``.
    """
    return reload_wybthon_modules()


@pytest.fixture()
def root_element(wyb):
    """Create a fresh :class:`StubNode` container wrapped in ``wybthon.dom.Element``."""
    return wyb["dom"].Element(node=StubNode(tag="div"))

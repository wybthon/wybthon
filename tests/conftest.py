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

from wybthon.testing import TestDocument, TestNode, _Parser, _Template

# ---------------------------------------------------------------------------
# DOM stubs: the in-memory DOM `wybthon.testing` ships, under the names the
# suite has always used.
# ---------------------------------------------------------------------------

StubNode = TestNode
StubTemplate = _Template
_StubHTMLParser = _Parser


class StubDocument(TestDocument):
    """The shipped test document, with a forgiving `querySelector` for unit tests."""

    __test__ = False

    def querySelector(self, selector):
        return super().querySelector(selector) or TestNode(tag="div")

    def querySelectorAll(self, selector):
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


def reload_wybthon_modules(doc=None):
    """Reload all browser-dependent wybthon submodules against current stubs.

    Reloading ``kernel`` resets the op buffer, id counter, and backend;
    when `doc` is provided a fresh :class:`wybthon.kernel.PythonBackend`
    is installed so ops apply to the current stub document.

    Returns a dict with keys ``kernel``, ``dom``, ``reconciler``,
    ``component``, ``events``, ``context``, ``reactivity`` (and more)
    pointing to the freshly reloaded module objects.
    """
    mods = {}
    for name in ("kernel", "dom", "events", "reconciler", "_shapes"):
        mod = importlib.import_module(f"wybthon.{name}")
        importlib.reload(mod)
        mods[name] = mod
    for name in (
        "component",
        "context",
        "reactivity",
        "_dom_props",
        "vnode",
        "flow",
        "loading",
        "error_boundary",
        "store",
        "portal",
        "lazy",
        "router",
        "forms",
        "elements",
        "templates",
        "svg",
    ):
        mods[name] = importlib.import_module(f"wybthon.{name}")
    if doc is not None:
        kernel = mods["kernel"]
        kernel.set_backend(kernel.PythonBackend(doc))
    # Reloading ``kernel`` rebinds its module-level ``commit``; point the
    # reactivity scheduler's cached reference at the fresh one and drop
    # any effect queues left over from a previous test.
    core = importlib.import_module("wybthon.reactivity._core")
    core._reset_scheduler_for_tests()
    core._kernel_commit = mods["kernel"].commit
    mods["core"] = core
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

    The yielded dict has keys: ``kernel``, ``dom``, ``component``,
    ``events``, ``context``, ``reactivity``, ``props``, ``reconciler``.
    A fresh ``PythonBackend`` over the stub document is installed so
    batched DOM ops apply to the in-memory tree.
    """
    _saved, doc = browser_stubs
    return reload_wybthon_modules(doc)


@pytest.fixture()
def root_element(wyb):
    """Create a fresh :class:`StubNode` container wrapped in ``wybthon.dom.Element``."""
    return wyb["dom"].Element(node=StubNode(tag="div"))

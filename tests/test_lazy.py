"""Tests for ``load_component`` and ``lazy`` helpers.

These cover:

* The pre-existing smoke checks (importable via Pyodide-only paths).
* A regression for a bug where ``lazy()`` and ``load_component()`` returned
  a render function as the *value* of an outer reactive hole, so the hole
  coerced the callable to text and the user saw a Python ``<function ...>``
  repr in the DOM instead of the actual page.  See git history for the
  full story; the fix is to have the inner ``render`` return
  ``h(comp, props)`` so the reconciler mounts the resolved component
  through the normal function-component path.
"""

import importlib
import sys
from types import ModuleType

import pytest
from conftest import collect_texts

try:
    importlib.import_module("js")
    HAS_JS = True
except Exception:
    HAS_JS = False


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_load_component_imports(monkeypatch):
    """Smoke test: ``load_component`` returns a callable for a real module."""
    wyb = importlib.import_module("wybthon")
    load_component = getattr(wyb, "load_component")

    comp = load_component("examples.demo.app.about.page", "Page")
    vnode = comp({})
    assert vnode is not None


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_preload_component_no_throw():
    """Preloading a known-importable module must never raise."""
    wyb = importlib.import_module("wybthon")
    preload = getattr(wyb, "preload_component")
    preload("examples.demo.app.about.page", "Page")


def _install_fake_module(monkeypatch, module_name: str, page_factory) -> None:
    """Create a synthetic module with a ``Page`` attribute and register it.

    ``page_factory`` is a zero-arg callable returning a (decorated) component
    function.  We defer construction so the @component decorator can run
    against the freshly-reloaded wybthon under the test fixture.
    """
    mod = ModuleType(module_name)
    setattr(mod, "Page", page_factory())
    monkeypatch.setitem(sys.modules, module_name, mod)


def test_load_component_mounts_resolved_module(wyb, monkeypatch, root_element):
    """``load_component`` must actually render the resolved component's tree.

    Regression: previously the inner ``render`` returned ``comp_fn(props)``
    where ``comp_fn`` was itself another function component, so the outer
    reactive hole stringified the callable and rendered ``<function ... at
    0x...>`` as text.
    """
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("p", {"class": "loaded-page"}, "hello from loaded page")

    _install_fake_module(monkeypatch, "_wyb_test_loaded_page", lambda: Page)

    load_component = wyb["lazy"].load_component if "lazy" in wyb else None
    if load_component is None:
        load_component = importlib.import_module("wybthon.lazy").load_component

    comp = load_component("_wyb_test_loaded_page", "Page")
    wyb["vdom"].render(h(comp, {}), root_element)

    texts = collect_texts(root_element.element)
    assert "hello from loaded page" in texts
    assert not any(
        "<function" in (t or "") for t in texts
    ), f"Reactive hole stringified a callable instead of mounting it: {texts!r}"


def test_lazy_mounts_resolved_module(wyb, monkeypatch, root_element):
    """Same regression coverage for the ``lazy()`` wrapper."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("section", {}, h("h2", {}, "Our Team"))

    _install_fake_module(monkeypatch, "_wyb_test_team_page", lambda: Page)

    lazy = importlib.import_module("wybthon.lazy").lazy

    def _Loader():
        return ("_wyb_test_team_page", "Page")

    LazyComp = lazy(_Loader)
    wyb["vdom"].render(h(LazyComp, {}), root_element)

    texts = collect_texts(root_element.element)
    assert "Our Team" in texts
    assert not any("<function" in (t or "") for t in texts), f"Lazy reactive hole stringified a callable: {texts!r}"


def test_lazy_renders_error_state_on_import_failure(wyb, root_element):
    """When the loader points at a missing module, render the error fallback."""
    h = wyb["vnode"].h
    lazy = importlib.import_module("wybthon.lazy").lazy

    def _BrokenLoader():
        return ("__definitely_not_a_real_module__", "Page")

    LazyComp = lazy(_BrokenLoader)
    wyb["vdom"].render(h(LazyComp, {}), root_element)

    texts = collect_texts(root_element.element)
    assert any("Failed to load" in (t or "") for t in texts), f"Expected lazy error fallback, got: {texts!r}"

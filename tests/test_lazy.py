"""Tests for the async, Suspense-integrated ``lazy`` helper.

``lazy(loader)`` wraps a sync or async loader that returns a component,
a module, a module-path string, or a ``(module_path, attr)`` tuple. The
load is backed by a Resource, so pending loads register with the nearest
Suspense boundary and failures raise into the nearest ErrorBoundary.
"""

import asyncio
import importlib
import sys
from types import ModuleType

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.error_boundary import ErrorBoundary
from wybthon.suspense import Suspense


def _install_fake_module(monkeypatch, module_name: str, page_factory) -> None:
    """Create a synthetic module with a ``Page`` attribute and register it.

    ``page_factory`` is a zero-arg callable returning a (decorated) component
    function.  We defer construction so the @component decorator can run
    against the freshly-reloaded wybthon under the test fixture.
    """
    mod = ModuleType(module_name)
    setattr(mod, "Page", page_factory())
    monkeypatch.setitem(sys.modules, module_name, mod)


def test_lazy_mounts_resolved_module(wyb, monkeypatch, root_element):
    """A tuple loader resolves through importlib and mounts the component."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("section", {}, h("h2", {}, "Our Team"))

    _install_fake_module(monkeypatch, "_wyb_test_team_page", lambda: Page)

    lazy = importlib.import_module("wybthon.lazy").lazy

    LazyComp = lazy(lambda: ("_wyb_test_team_page", "Page"))

    async def run() -> None:
        wyb["reconciler"].render(h(LazyComp, {}), root_element)
        await asyncio.sleep(0.01)

    asyncio.run(run())

    texts = collect_texts(root_element.element)
    assert "Our Team" in texts
    assert not any("<function" in (t or "") for t in texts), f"Lazy reactive hole stringified a callable: {texts!r}"


def test_lazy_accepts_direct_component(wyb, root_element):
    """A loader may return the component callable directly."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("p", {}, "direct component")

    lazy = importlib.import_module("wybthon.lazy").lazy
    LazyComp = lazy(lambda: Page)

    async def run() -> None:
        wyb["reconciler"].render(h(LazyComp, {}), root_element)
        await asyncio.sleep(0.01)

    asyncio.run(run())

    assert "direct component" in collect_texts(root_element.element)


def test_lazy_async_loader(wyb, monkeypatch, root_element):
    """Async loaders may await work before returning the component."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("p", {}, "async loaded")

    _install_fake_module(monkeypatch, "_wyb_test_async_page", lambda: Page)

    lazy = importlib.import_module("wybthon.lazy").lazy

    async def loader():
        await asyncio.sleep(0)
        return ("_wyb_test_async_page", "Page")

    LazyComp = lazy(loader)

    async def run() -> None:
        wyb["reconciler"].render(h(LazyComp, {}), root_element)
        await asyncio.sleep(0.01)

    asyncio.run(run())

    assert "async loaded" in collect_texts(root_element.element)


def test_lazy_shows_suspense_fallback_while_loading(wyb, monkeypatch, root_element):
    """A pending lazy load triggers the nearest Suspense fallback."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    @component
    def Page():
        return h("p", {}, "lazy page ready")

    _install_fake_module(monkeypatch, "_wyb_test_slow_page", lambda: Page)

    lazy = importlib.import_module("wybthon.lazy").lazy

    release = None

    async def loader():
        await release.wait()
        return ("_wyb_test_slow_page", "Page")

    LazyComp = lazy(loader)

    async def run() -> None:
        nonlocal release
        release = asyncio.Event()
        wyb["reconciler"].render(
            Suspense(fallback="Loading...", children=[h(LazyComp, {})]),
            root_element,
        )
        await asyncio.sleep(0)
        assert "Loading..." in collect_texts(root_element.element)

        release.set()
        await asyncio.sleep(0.01)
        texts = collect_texts(root_element.element)
        assert "lazy page ready" in texts
        assert "Loading..." not in texts

    asyncio.run(run())


def test_lazy_raises_into_error_boundary_on_import_failure(wyb, root_element):
    """When the loader points at a missing module, the error boundary catches it."""
    h = wyb["vnode"].h

    lazy = importlib.import_module("wybthon.lazy").lazy
    LazyComp = lazy(lambda: ("__definitely_not_a_real_module__", "Page"))

    async def run() -> None:
        wyb["reconciler"].render(
            h(
                ErrorBoundary,
                {
                    "fallback": lambda err, reset: h("p", {}, "Failed to load"),
                    "children": [h(LazyComp, {})],
                },
            ),
            root_element,
        )
        await asyncio.sleep(0.01)

    asyncio.run(run())

    texts = collect_texts(root_element.element)
    assert any("Failed to load" in (t or "") for t in texts), f"Expected error fallback, got: {texts!r}"


def test_lazy_preload_starts_load_early(wyb, monkeypatch, root_element):
    """preload() kicks off the loader before the first mount."""
    component = wyb["component"].component
    h = wyb["vnode"].h

    calls = []

    @component
    def Page():
        return h("p", {}, "preloaded page")

    _install_fake_module(monkeypatch, "_wyb_test_preload_page", lambda: Page)

    lazy = importlib.import_module("wybthon.lazy").lazy

    def loader():
        calls.append(1)
        return ("_wyb_test_preload_page", "Page")

    LazyComp = lazy(loader)

    async def run() -> None:
        LazyComp.preload()
        await asyncio.sleep(0.01)
        assert calls == [1]

        wyb["reconciler"].render(h(LazyComp, {}), root_element)
        await asyncio.sleep(0.01)

    asyncio.run(run())

    assert "preloaded page" in collect_texts(root_element.element)
    assert calls == [1], "loader must run exactly once"

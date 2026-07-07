"""Unit tests for Suspense with automatic resource registration.

These tests exercise the Suspense component through the reconciler using
browser stubs. Resources self-register with the nearest boundary when
they're read while still in their initial `"pending"` state.
"""

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.suspense import Suspense
from wybthon.vnode import h, to_text_vnode


class FakeResource:
    """Minimal stand-in matching the Resource read/registration protocol."""

    def __init__(self, is_loading: bool = False, value=None):
        from wybthon.reactivity import Signal

        self._loading = Signal(is_loading)
        self._state = Signal("pending" if is_loading else "ready")
        self._data = Signal(value)

    def __call__(self):
        from wybthon import reactivity as _rx

        if self._state.peek() == "pending":
            owner = _rx._current_owner
            if owner is not None:
                collector = owner._lookup_context(_rx.SUSPENSE_CONTEXT_KEY, None)
                if collector is not None:
                    collector.register(self)
        return self._data.get()

    def resolve(self, value):
        from wybthon.reactivity import _Batch

        with _Batch():
            self._data.set(value)
            self._loading.set(False)
            self._state.set("ready")


def test_suspense_renders_children_when_no_resources(wyb, root_element):
    vdom = wyb["reconciler"]
    vdom.render(
        Suspense(children=[h("p", {}, "content")]),
        root_element,
    )
    assert "content" in collect_texts(root_element.element)


def test_suspense_shows_fallback_while_pending(wyb, root_element):
    vdom = wyb["reconciler"]
    res = FakeResource(is_loading=True)
    vdom.render(
        Suspense(fallback="Loading...", children=[h("p", {}, res)]),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "Loading..." in texts


def test_suspense_swaps_to_children_after_resolve(wyb, root_element):
    vdom = wyb["reconciler"]
    res = FakeResource(is_loading=True)
    vdom.render(
        Suspense(fallback="Loading...", children=[h("p", {}, res)]),
        root_element,
    )
    assert "Loading..." in collect_texts(root_element.element)

    res.resolve("data!")
    texts = collect_texts(root_element.element)
    assert "data!" in texts
    assert "Loading..." not in texts


def test_suspense_renders_children_when_already_resolved(wyb, root_element):
    vdom = wyb["reconciler"]
    res = FakeResource(is_loading=False, value="ready-data")
    vdom.render(
        Suspense(fallback="Loading...", children=[h("p", {}, res)]),
        root_element,
    )
    texts = collect_texts(root_element.element)
    assert "ready-data" in texts
    assert "Loading..." not in texts


def test_suspense_multiple_resources_wait_for_all(wyb, root_element):
    vdom = wyb["reconciler"]
    res1 = FakeResource(is_loading=True)
    res2 = FakeResource(is_loading=True)
    vdom.render(
        Suspense(fallback="Wait...", children=[h("p", {}, res1), h("p", {}, res2)]),
        root_element,
    )
    assert "Wait..." in collect_texts(root_element.element)

    res1.resolve("one")
    assert "Wait..." in collect_texts(root_element.element)

    res2.resolve("two")
    texts = collect_texts(root_element.element)
    assert "one" in texts and "two" in texts
    assert "Wait..." not in texts


def test_suspense_callable_fallback(wyb, root_element):
    vdom = wyb["reconciler"]
    res = FakeResource(is_loading=True)
    vdom.render(
        Suspense(fallback=lambda: to_text_vnode("custom loading"), children=[h("p", {}, res)]),
        root_element,
    )
    assert "custom loading" in collect_texts(root_element.element)


def test_suspense_normalize_single_child(wyb, root_element):
    vdom = wyb["reconciler"]
    vdom.render(
        Suspense(children=to_text_vnode("single")),
        root_element,
    )
    assert "single" in collect_texts(root_element.element)


def test_real_resource_registers_with_suspense(wyb, root_element):
    """An actual Resource read under Suspense triggers the fallback and resolves."""
    import asyncio

    reactivity = wyb["reactivity"]
    vdom = wyb["reconciler"]

    async def run() -> None:
        release = asyncio.Event()

        async def fetcher():
            await release.wait()
            return "fetched"

        res = reactivity.create_resource(fetcher)

        vdom.render(
            Suspense(fallback="Loading...", children=[h("p", {}, res)]),
            root_element,
        )
        # Let the fetch task start.
        await asyncio.sleep(0)
        assert "Loading..." in collect_texts(root_element.element)

        release.set()
        await asyncio.sleep(0.01)
        texts = collect_texts(root_element.element)
        assert "fetched" in texts
        assert "Loading..." not in texts

    asyncio.run(run())

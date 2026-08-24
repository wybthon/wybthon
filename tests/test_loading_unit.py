"""Unit tests for the Loading boundary with async memos.

These tests exercise the Loading component through the reconciler using
browser stubs. Async computations self-register with the nearest
boundary when a read raises `NotReadyError`.
"""

import asyncio
import importlib

from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.vnode import h, to_text_vnode


def _loading(wyb):
    return importlib.import_module("wybthon.loading").Loading


def _gated_memo(reactivity):
    """Return `(memo, resolve)` where the memo stays pending until resolved."""
    release = asyncio.Event()
    box = {"value": None}

    async def load():
        await release.wait()
        return box["value"]

    memo = reactivity.create_memo(load)

    def resolve(value):
        box["value"] = value
        release.set()

    return memo, resolve


def test_loading_renders_children_when_no_async(wyb, root_element):
    Loading = _loading(wyb)
    wyb["reconciler"].render(
        Loading(children=[h("p", {}, "content")]),
        root_element,
    )
    assert "content" in collect_texts(root_element.element)


def test_loading_shows_fallback_while_pending(wyb, root_element):
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo, _resolve = _gated_memo(reactivity)
        wyb["reconciler"].render(
            Loading(fallback="Loading...", children=[h("p", {}, memo)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "Loading..." in collect_texts(root_element.element)

    asyncio.run(run())


def test_loading_swaps_to_children_after_resolve(wyb, root_element):
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo, resolve = _gated_memo(reactivity)
        wyb["reconciler"].render(
            Loading(fallback="Loading...", children=[h("p", {}, memo)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "Loading..." in collect_texts(root_element.element)

        resolve("data!")
        await asyncio.sleep(0.01)
        reactivity.flush()
        texts = collect_texts(root_element.element)
        assert "data!" in texts
        assert "Loading..." not in texts

    asyncio.run(run())


def test_loading_renders_children_when_already_resolved(wyb, root_element):
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo, resolve = _gated_memo(reactivity)
        resolve("ready-data")
        await asyncio.sleep(0.01)

        wyb["reconciler"].render(
            Loading(fallback="Loading...", children=[h("p", {}, memo)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        texts = collect_texts(root_element.element)
        assert "ready-data" in texts
        assert "Loading..." not in texts

    asyncio.run(run())


def test_loading_multiple_memos_wait_for_all(wyb, root_element):
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo1, resolve1 = _gated_memo(reactivity)
        memo2, resolve2 = _gated_memo(reactivity)
        wyb["reconciler"].render(
            Loading(fallback="Wait...", children=[h("p", {}, memo1), h("p", {}, memo2)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "Wait..." in collect_texts(root_element.element)

        resolve1("one")
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "Wait..." in collect_texts(root_element.element)

        resolve2("two")
        await asyncio.sleep(0.01)
        reactivity.flush()
        texts = collect_texts(root_element.element)
        assert "one" in texts and "two" in texts
        assert "Wait..." not in texts

    asyncio.run(run())


def test_loading_callable_fallback(wyb, root_element):
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo, _resolve = _gated_memo(reactivity)
        wyb["reconciler"].render(
            Loading(fallback=lambda: to_text_vnode("custom loading"), children=[h("p", {}, memo)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "custom loading" in collect_texts(root_element.element)

    asyncio.run(run())


def test_loading_normalize_single_child(wyb, root_element):
    Loading = _loading(wyb)
    wyb["reconciler"].render(
        Loading(children=to_text_vnode("single")),
        root_element,
    )
    assert "single" in collect_texts(root_element.element)


def test_loading_revalidation_keeps_content(wyb, root_element):
    """A revalidating memo serves its stale value; the fallback must not return."""
    Loading = _loading(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        source, set_source = reactivity.create_signal(1)
        gate = asyncio.Event()
        gate.set()

        async def load():
            n = source()
            await gate.wait()
            return f"value-{n}"

        memo = reactivity.create_memo(load)
        wyb["reconciler"].render(
            Loading(fallback="Loading...", children=[h("p", {}, memo)]),
            root_element,
        )
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "value-1" in collect_texts(root_element.element)

        # Block the reload; stale content stays, fallback stays away.
        gate.clear()
        set_source(2)
        await asyncio.sleep(0.01)
        reactivity.flush()
        texts = collect_texts(root_element.element)
        assert "value-1" in texts
        assert "Loading..." not in texts

        gate.set()
        await asyncio.sleep(0.01)
        reactivity.flush()
        assert "value-2" in collect_texts(root_element.element)

    asyncio.run(run())

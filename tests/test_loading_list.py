"""Unit tests for LoadingList: coordinated reveal order across boundaries."""

import asyncio
import importlib

import pytest
from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.vnode import h


def _loading_mod(wyb):
    return importlib.import_module("wybthon.loading")


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


def _two_boundary_list(mod, memo_a, memo_b, **list_kwargs):
    return mod.LoadingList(
        children=[
            mod.Loading(fallback="Fallback A", children=[h("p", {}, memo_a)]),
            mod.Loading(fallback="Fallback B", children=[h("p", {}, memo_b)]),
        ],
        **list_kwargs,
    )


async def _settle(reactivity):
    await asyncio.sleep(0.01)
    reactivity.flush()


def test_forwards_blocks_later_boundary_until_earlier_resolves(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, resolve_b = _gated_memo(reactivity)

        wyb["reconciler"].render(_two_boundary_list(mod, memo_a, memo_b), root_element)
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Fallback A" in texts
        assert "Fallback B" in texts

        # B resolves first, but must wait for A in forwards order.
        resolve_b("Content B")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Fallback A" in texts
        assert "Content B" not in texts

        resolve_a("Content A")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Content B" in texts
        assert "Fallback A" not in texts
        assert "Fallback B" not in texts

    asyncio.run(run())


def test_backwards_reveals_bottom_up(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, resolve_b = _gated_memo(reactivity)

        wyb["reconciler"].render(
            _two_boundary_list(mod, memo_a, memo_b, reveal_order="backwards"),
            root_element,
        )
        await _settle(reactivity)

        # A resolves first, but must wait for B in backwards order.
        resolve_a("Content A")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" not in texts

        resolve_b("Content B")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Content B" in texts

    asyncio.run(run())


def test_together_reveals_all_at_once(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, resolve_b = _gated_memo(reactivity)

        wyb["reconciler"].render(
            _two_boundary_list(mod, memo_a, memo_b, reveal_order="together"),
            root_element,
        )
        await _settle(reactivity)

        resolve_a("Content A")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" not in texts

        resolve_b("Content B")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Content B" in texts

    asyncio.run(run())


def test_tail_collapsed_shows_only_next_fallback(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, _resolve_b = _gated_memo(reactivity)

        wyb["reconciler"].render(
            _two_boundary_list(mod, memo_a, memo_b, tail="collapsed"),
            root_element,
        )
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Fallback A" in texts
        assert "Fallback B" not in texts

        resolve_a("Content A")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Fallback B" in texts

    asyncio.run(run())


def test_tail_hidden_shows_no_fallbacks(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, resolve_b = _gated_memo(reactivity)

        wyb["reconciler"].render(
            _two_boundary_list(mod, memo_a, memo_b, tail="hidden"),
            root_element,
        )
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Fallback A" not in texts
        assert "Fallback B" not in texts

        resolve_a("Content A")
        resolve_b("Content B")
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Content B" in texts

    asyncio.run(run())


def test_resolved_boundaries_render_immediately(wyb, root_element):
    mod = _loading_mod(wyb)
    reactivity = wyb["reactivity"]

    async def run():
        memo_a, resolve_a = _gated_memo(reactivity)
        memo_b, resolve_b = _gated_memo(reactivity)
        resolve_a("Content A")
        resolve_b("Content B")
        await asyncio.sleep(0.01)

        wyb["reconciler"].render(_two_boundary_list(mod, memo_a, memo_b), root_element)
        await _settle(reactivity)
        texts = collect_texts(root_element.element)
        assert "Content A" in texts
        assert "Content B" in texts

    asyncio.run(run())


def test_loading_list_validates_arguments(wyb):
    mod = _loading_mod(wyb)
    with pytest.raises(ValueError):
        mod.LoadingList(children=[], reveal_order="sideways")
    with pytest.raises(ValueError):
        mod.LoadingList(children=[], tail="folded")

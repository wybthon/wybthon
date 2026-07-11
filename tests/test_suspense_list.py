"""Unit tests for SuspenseList: coordinated reveal order across boundaries."""

import pytest
from conftest import collect_texts

import wybthon as _wybthon_pkg  # noqa: F401
from wybthon.suspense import Suspense, SuspenseList
from wybthon.vnode import h


class FakeResource:
    """Minimal stand-in matching the Resource read/registration protocol."""

    def __init__(self, is_loading: bool = True, value=None):
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


def _two_boundary_list(res_a, res_b, **list_kwargs):
    return SuspenseList(
        children=[
            Suspense(fallback="Fallback A", children=[h("p", {}, res_a)]),
            Suspense(fallback="Fallback B", children=[h("p", {}, res_b)]),
        ],
        **list_kwargs,
    )


def test_forwards_blocks_later_boundary_until_earlier_resolves(wyb, root_element):
    res_a = FakeResource()
    res_b = FakeResource()

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b), root_element)
    texts = collect_texts(root_element.element)
    assert "Fallback A" in texts
    assert "Fallback B" in texts

    # B resolves first, but must wait for A in forwards order.
    res_b.resolve("Content B")
    texts = collect_texts(root_element.element)
    assert "Fallback A" in texts
    assert "Content B" not in texts

    res_a.resolve("Content A")
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Content B" in texts
    assert "Fallback A" not in texts
    assert "Fallback B" not in texts


def test_backwards_reveals_bottom_up(wyb, root_element):
    res_a = FakeResource()
    res_b = FakeResource()

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b, reveal_order="backwards"), root_element)

    # A resolves first, but must wait for B in backwards order.
    res_a.resolve("Content A")
    texts = collect_texts(root_element.element)
    assert "Content A" not in texts

    res_b.resolve("Content B")
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Content B" in texts


def test_together_reveals_all_at_once(wyb, root_element):
    res_a = FakeResource()
    res_b = FakeResource()

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b, reveal_order="together"), root_element)

    res_a.resolve("Content A")
    texts = collect_texts(root_element.element)
    assert "Content A" not in texts

    res_b.resolve("Content B")
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Content B" in texts


def test_tail_collapsed_shows_only_next_fallback(wyb, root_element):
    res_a = FakeResource()
    res_b = FakeResource()

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b, tail="collapsed"), root_element)
    texts = collect_texts(root_element.element)
    assert "Fallback A" in texts
    assert "Fallback B" not in texts

    res_a.resolve("Content A")
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Fallback B" in texts


def test_tail_hidden_shows_no_fallbacks(wyb, root_element):
    res_a = FakeResource()
    res_b = FakeResource()

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b, tail="hidden"), root_element)
    texts = collect_texts(root_element.element)
    assert "Fallback A" not in texts
    assert "Fallback B" not in texts

    res_a.resolve("Content A")
    res_b.resolve("Content B")
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Content B" in texts


def test_resolved_boundaries_render_immediately(wyb, root_element):
    res_a = FakeResource(is_loading=False, value="Content A")
    res_b = FakeResource(is_loading=False, value="Content B")

    wyb["reconciler"].render(_two_boundary_list(res_a, res_b), root_element)
    texts = collect_texts(root_element.element)
    assert "Content A" in texts
    assert "Content B" in texts


def test_suspense_list_validates_arguments():
    with pytest.raises(ValueError):
        SuspenseList(children=[], reveal_order="sideways")
    with pytest.raises(ValueError):
        SuspenseList(children=[], tail="folded")

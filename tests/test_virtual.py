"""Tests for fixed-height list virtualization (create_virtualizer, VirtualFor)."""

from __future__ import annotations

import pytest

from wybthon.reactivity import create_root, create_signal, flush
from wybthon.virtual import VirtualFor, create_virtualizer

# ---------------------------------------------------------------------------
# create_virtualizer — input validation
# ---------------------------------------------------------------------------


def test_create_virtualizer_rejects_non_positive_item_size():
    with pytest.raises(ValueError, match="item_size must be positive"):
        create_virtualizer(10, item_size=0, viewport_size=100, scroll_offset=0)

    with pytest.raises(ValueError, match="item_size must be positive"):
        create_virtualizer(10, item_size=-5, viewport_size=100, scroll_offset=0)


def test_create_virtualizer_rejects_negative_overscan():
    with pytest.raises(ValueError, match="overscan must be nonnegative"):
        create_virtualizer(10, item_size=20, viewport_size=100, scroll_offset=0, overscan=-1)


# ---------------------------------------------------------------------------
# create_virtualizer — static values
# ---------------------------------------------------------------------------


def test_create_virtualizer_empty_collection():
    def test_logic():
        virt = create_virtualizer(0, item_size=20, viewport_size=100, scroll_offset=0)
        assert virt.start() == 0
        assert virt.stop() == 0
        assert virt.offset() == 0.0
        assert virt.total() == 0.0

    create_root(lambda dispose: test_logic())


def test_create_virtualizer_static_bounds():
    def test_logic():
        # 100 items × 20px = 2000px total.  Viewport 100px ⇒ 5 visible.
        # Scroll 0, overscan 2 → first = 0, last = min(100, ceil(100/20)+2) = 7.
        virt = create_virtualizer(100, item_size=20, viewport_size=100, scroll_offset=0, overscan=2)
        assert virt.start() == 0
        assert virt.stop() == 7
        assert virt.offset() == 0.0
        assert virt.total() == 2000.0

    create_root(lambda dispose: test_logic())


def test_create_virtualizer_zero_overscan():
    def test_logic():
        # 50 items × 40px, viewport 120px, scroll 0, overscan 0
        # first = 0, last = min(50, ceil(120/40)) = 3
        virt = create_virtualizer(50, item_size=40, viewport_size=120, scroll_offset=0, overscan=0)
        assert virt.start() == 0
        assert virt.stop() == 3

    create_root(lambda dispose: test_logic())


def test_create_virtualizer_scrolled_past_end_clamps():
    def test_logic():
        # 10 items × 20px = 200px.  Viewport 100px.  Scroll 9999px → clamped.
        virt = create_virtualizer(10, item_size=20, viewport_size=100, scroll_offset=9999, overscan=0)
        assert virt.stop() <= 10

    create_root(lambda dispose: test_logic())


# ---------------------------------------------------------------------------
# create_virtualizer — reactive updates
# ---------------------------------------------------------------------------


def test_create_virtualizer_reacts_to_scroll_signal():
    def test_logic():
        scroll, set_scroll = create_signal(0.0)
        virt = create_virtualizer(100, item_size=20, viewport_size=100, scroll_offset=scroll, overscan=2)
        assert virt.start() == 0

        # Scroll to 200px → row 10 is top
        # first = max(0, 200//20 − 2) = 8
        # last  = min(100, ceil((200+100)/20) + 2) = 17
        set_scroll(200.0)
        flush()
        assert virt.start() == 8
        assert virt.stop() == 17
        assert virt.offset() == 160.0  # start × item_size

    create_root(lambda dispose: test_logic())


def test_create_virtualizer_reacts_to_count_signal():
    def test_logic():
        count, set_count = create_signal(100)
        virt = create_virtualizer(count, item_size=20, viewport_size=100, scroll_offset=0, overscan=0)
        assert virt.total() == 2000.0

        set_count(5)
        flush()
        assert virt.total() == 100.0
        assert virt.stop() <= 5

    create_root(lambda dispose: test_logic())


def test_create_virtualizer_reacts_to_viewport_signal():
    def test_logic():
        viewport, set_viewport = create_signal(100.0)
        virt = create_virtualizer(100, item_size=20, viewport_size=viewport, scroll_offset=0, overscan=0)
        # Viewport 100px ⇒ ceil(100/20) = 5 visible rows
        assert virt.stop() == 5

        set_viewport(200.0)
        flush()
        # Viewport 200px ⇒ ceil(200/20) = 10 visible rows
        assert virt.stop() == 10

    create_root(lambda dispose: test_logic())


# ---------------------------------------------------------------------------
# VirtualFor — input validation
# ---------------------------------------------------------------------------


def test_virtual_for_rejects_non_positive_height():
    with pytest.raises(ValueError, match="height must be positive"):
        VirtualFor(lambda: [1, 2, 3], lambda item, i: None, height=0, row_height=20)

    with pytest.raises(ValueError, match="height must be positive"):
        VirtualFor(lambda: [1, 2, 3], lambda item, i: None, height=-10, row_height=20)


# ---------------------------------------------------------------------------
# VirtualFor — rendering smoke test
# ---------------------------------------------------------------------------


def test_virtual_for_returns_a_vnode(wyb, root_element):
    """VirtualFor produces a DOM tree rooted at a scrolling div container."""
    from conftest import collect_texts

    items = [f"Item {i}" for i in range(50)]
    root = wyb["reconciler"].render(
        VirtualFor(
            lambda: items,
            lambda item, index: item,
            height=100,
            row_height=20,
            overscan=1,
        ),
        root_element,
    )
    # The outermost element is the scroll container div.
    container = root_element.element.childNodes[0]
    assert container.tag == "div"

    # At least some items were rendered into the DOM.
    all_text = collect_texts(root_element.element)
    assert any("Item" in t for t in all_text)

    root.dispose()

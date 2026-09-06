"""Fixed-height list virtualization built on owned virtual DOM list regions."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from .flow import For
from .html import div
from .reactivity import Accessor, create_memo, create_signal
from .reactivity._props import Props
from .vnode import VNode, h


@dataclass(frozen=True, slots=True)
class Virtualizer:
    """Reactive visible bounds and layout dimensions, all in CSS pixels."""

    start: Accessor[int]
    stop: Accessor[int]
    offset: Accessor[float]
    total: Accessor[float]


def create_virtualizer(
    count: Any, *, item_size: float, viewport_size: Any, scroll_offset: Any, overscan: int = 3
) -> Virtualizer:
    """Calculate a fixed-size visible range without visiting collection items."""
    if item_size <= 0 or overscan < 0:
        raise ValueError("item_size must be positive and overscan must be nonnegative")

    def read(value: Any) -> Any:
        return value() if callable(value) else value

    n = create_memo(lambda: max(0, int(read(count))))
    size = create_memo(lambda: max(0, float(read(viewport_size))))

    def bounds() -> tuple[int, int]:
        top = max(0, min(float(read(scroll_offset)), max(0, n() * item_size - size())))
        first = max(0, int(top // item_size) - overscan)
        last = min(n(), ceil((top + size()) / item_size) + overscan)
        return first, last

    visible = create_memo(bounds)
    start = create_memo(lambda: visible()[0])
    stop = create_memo(lambda: visible()[1])
    return Virtualizer(start, stop, create_memo(lambda: start() * item_size), create_memo(lambda: n() * item_size))


def VirtualFor(
    each: Any, children: Any, *, height: float, row_height: float, overscan: int = 3, keyed: Any = True, **props: Any
) -> VNode:
    """Render only visible fixed-height rows inside a scrolling container.

    Offscreen rows are disposed. Keep durable item state in the source store.
    Callback index accessors refer to the full collection, not the window.
    """
    if height <= 0:
        raise ValueError("height must be positive")
    return h(
        _VirtualFor,
        {
            "each": each,
            "children": children,
            "height": height,
            "row_height": row_height,
            "overscan": overscan,
            "keyed": keyed,
            **props,
        },
    )


def _VirtualFor(props: Props) -> Any:
    each = props.each
    scroll, set_scroll = create_signal(0.0)
    row_height = float(props.raw("row_height"))
    height = float(props.raw("height"))
    virtualizer = create_virtualizer(
        lambda: len(each()),
        item_size=row_height,
        viewport_size=height,
        scroll_offset=scroll,
        overscan=int(props.raw("overscan")),
    )
    children = props.raw("children")
    keyed = props.raw("keyed")
    forwarded = {
        key: props.raw(key)
        for key in props
        if key not in {"each", "children", "height", "row_height", "overscan", "keyed", "style", "on_scroll"}
    }

    def row(item: Any, index: Any) -> Any:
        absolute = create_memo(lambda: virtualizer.start() + (index() if callable(index) else index))
        return div(
            children(item, absolute),
            style={"height": f"{row_height}px"},
            role="listitem",
            aria_posinset=lambda: absolute() + 1,
            aria_setsize=lambda: len(each()),
        )

    user_scroll = props.raw("on_scroll")

    def changed(event: Any) -> Any:
        set_scroll(float(event.target.scroll_top))
        return user_scroll(event) if callable(user_scroll) else None

    styles = dict(props.raw("style") or {})
    styles.update({"height": f"{height}px", "overflow_y": "auto", "position": "relative"})
    return div(
        div(
            div(
                For(lambda: each()[virtualizer.start() : virtualizer.stop()], row, keyed=keyed),
                style={"transform": lambda: f"translateY({virtualizer.offset()}px)"},
            ),
            style={"height": lambda: f"{virtualizer.total()}px"},
        ),
        style=styles,
        role="list",
        on_scroll=changed,
        **forwarded,
    )

"""`Loading` and `Reveal`: fallback UI for async computations.

[`Loading`][wybthon.Loading] is the async boundary (SolidJS 2.0's
`Loading`, the successor to `Suspense`). Any read of an async
computation under the boundary that raises
[`NotReadyError`][wybthon.NotReadyError] registers the computation with
the boundary, and the boundary shows its fallback until every
registered computation has produced its first value.

Revalidations don't re-trigger the boundary: an async memo that already
has a value keeps serving it (stale-while-revalidate) while the
recompute is in flight, so content stays visible during reloads. Use
[`is_pending`][wybthon.is_pending] to render inline refresh hints.

Pass `on=` to have the boundary wait for specific accessors as well,
even if the children never read them; this is how you keep a layout
from partially rendering while a critical query is still in flight.

[`Reveal`][wybthon.Reveal] coordinates multiple `Loading` boundaries
beneath it, controlling the order their contents reveal (`order`) and
how many fallbacks show at once (`tail`).

Example:
    ```python
    async def load_user():
        return await fetch_json("/api/user")

    user = create_memo(load_user)

    Loading(
        lambda: div(lambda: user()["name"]),
        fallback=lambda: p("Loading..."),
    )
    ```

See Also:
    - [Async and loading guide](../concepts/async-loading.md)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from .reactivity import _core
from .reactivity._core import LOADING_CONTEXT_KEY, Computation, NotReadyError, Signal
from .reactivity._primitives import create_effect, create_signal, on_cleanup
from .reactivity._props import Props
from .vnode import Fragment, VNode, h, hole, to_text_vnode

__all__ = ["Loading", "Reveal"]

# Owner-context key under which ``Reveal`` stores its coordinator.
REVEAL_CONTEXT_KEY = "__wyb_reveal__"


class _LoadingCollector:
    """Tracks not-ready async computations read under one Loading boundary."""

    __slots__ = ("_version", "_pending")

    def __init__(self) -> None:
        self._version: Signal[int] = Signal(0)
        self._pending: set[Computation] = set()

    def register(self, comp: Computation) -> None:
        """Called by the reactive core when a read raises `NotReadyError`."""
        if comp in self._pending:
            return
        self._pending.add(comp)
        self._version._set_now(self._version.peek() + 1)

    def is_loading(self) -> bool:
        """Tracked read: True while any registered computation has no value.

        Computations that have produced a first value are pruned, so a
        later revalidation (which serves the stale value instead of
        raising) can't re-trigger the boundary.
        """
        self._version()
        done = []
        for comp in self._pending:
            a = comp._async
            still_loading = a is not None and a.pending and not a.has_value and not comp._disposed
            if still_loading:
                # Subscribe to the transition out of the pending state.
                comp._pending_sig()()
            else:
                done.append(comp)
        for comp in done:
            self._pending.discard(comp)
        return bool(self._pending)


def Loading(
    children: Any = None,
    *,
    fallback: Any = None,
    on: Any = None,
) -> VNode:
    """Show a fallback while async reads under the boundary aren't ready.

    Args:
        children: Content rendered when nothing is loading: a VNode, a
            zero-arg callable, or a list of either. Async computations
            read anywhere in this subtree self-register with the
            boundary when a read raises
            [`NotReadyError`][wybthon.NotReadyError].
        fallback: VNode, string, or callable returning one of those,
            shown while any registered async computation has no value.
        on: An accessor or list of accessors the boundary also waits
            for, regardless of whether the children read them.

    Returns:
        A component [`VNode`][wybthon.VNode] that toggles between
        fallback and children.

    Example:
        ```python
        Loading(
            lambda: Fragment(Header(), Body()),
            fallback=Spinner(),
            on=[user, settings],
        )
        ```
    """
    return h(_Loading, {"fallback": fallback, "children": children, "on": on})


def _render_content(value: Any) -> VNode:
    if isinstance(value, VNode):
        return value
    if value is None:
        return Fragment()
    if isinstance(value, list):
        items = [v() if callable(v) and not isinstance(v, VNode) else v for v in value]
        return Fragment(*items)
    if callable(value):
        return _render_content(value())
    return to_text_vnode(value)


def _render_fallback(fb: Any) -> VNode:
    if callable(fb) and not isinstance(fb, VNode):
        fb = fb()
    if isinstance(fb, VNode):
        return fb
    if isinstance(fb, list):
        return Fragment(*fb)
    return to_text_vnode("" if fb is None else str(fb))


def _Loading(props: Props) -> Any:
    from . import reconciler

    collector = _LoadingCollector()
    owner = _core._current_owner
    reveal: _RevealState | None = None
    reveal_index = -1
    if owner is not None:
        owner._set_context(LOADING_CONTEXT_KEY, collector)
        reveal = owner._lookup_context(REVEAL_CONTEXT_KEY, None)
        if reveal is not None:
            reveal_index = reveal.register(collector.is_loading)
            # Boundaries nested inside this one coordinate with this
            # boundary, not with the outer Reveal.
            owner._set_context(REVEAL_CONTEXT_KEY, None)

    children = props.raw("children")
    fallback = props.raw("fallback")
    on = props.raw("on")
    waits: list[Callable[[], Any]] = []
    if on is not None:
        waits = list(on) if isinstance(on, (list, tuple)) else [on]

    def wait_for_on() -> None:
        # Reads register with our collector (via the owner context) and
        # raise NotReadyError when a source has no value yet; the raise
        # is swallowed because the collector now tracks the source.
        for acc in waits:
            try:
                acc()
            except NotReadyError:
                pass

    def mode() -> str:
        wait_for_on()
        if reveal is not None:
            return reveal.display_mode(reveal_index)
        return "fallback" if collector.is_loading() else "content"

    # The content stays mounted the whole time, so async computations
    # created inside it keep running while the fallback shows. While
    # pending, its DOM nodes are parked in a detached element and moved
    # back in front of the fallback hole once everything has resolved.
    shown, set_shown = create_signal("content")
    content = hole(lambda: _render_content(children))
    fallback_hole = hole(lambda: _render_fallback(fallback) if shown() == "fallback" else None)
    lot = reconciler._create_lot()
    on_cleanup(lambda: reconciler._release_lot(lot))
    parked = False

    def apply(current: str) -> None:
        nonlocal parked
        hide = current != "content"
        if hide and not parked:
            reconciler._park(content, lot)
            parked = True
        elif not hide and parked:
            anchor = reconciler._first_dom_id(fallback_hole)
            if anchor is not None:
                reconciler._unpark(content, anchor)
            parked = False
        set_shown(current)

    # A user effect: its first run happens after the initial mount has
    # committed, when the content's DOM nodes exist to be parked.
    create_effect(mode, apply)

    return Fragment(content, fallback_hole)


_Loading.__name__ = "Loading"


# ---------------------------------------------------------------------------
# Reveal
# ---------------------------------------------------------------------------

RevealOrder = Literal["forwards", "backwards", "together"]
RevealTail = Literal["visible", "collapsed", "hidden"]


class _RevealState:
    """Coordinates reveal order across the boundaries under one Reveal."""

    __slots__ = ("_order", "_tail", "_getters", "_version")

    def __init__(self, order: str, tail: str) -> None:
        self._order = order
        self._tail = tail
        self._getters: list[Callable[[], bool]] = []
        # Bumped when a boundary registers so already-rendered siblings
        # re-evaluate their display mode.
        self._version: Signal[int] = Signal(0)

    def register(self, loading_getter: Callable[[], bool]) -> int:
        """Add a boundary's tracked loading getter; returns its position."""
        self._getters.append(loading_getter)
        self._version._set_now(self._version.peek() + 1)
        return len(self._getters) - 1

    def display_mode(self, idx: int) -> str:
        """Tracked read: what boundary `idx` should render.

        Returns:
            `"content"`, `"fallback"`, or `"hidden"`.
        """
        self._version()
        getters = self._getters
        order = self._order
        tail = self._tail

        if order == "together":
            if not any(g() for g in getters):
                return "content"
            return self._pending_mode(idx, tail, getters, range(len(getters)))

        if order == "backwards":
            indices = range(len(getters) - 1, -1, -1)
            blocked = any(getters[j]() for j in range(len(getters) - 1, idx, -1))
        else:  # forwards
            indices = range(len(getters))
            blocked = any(getters[j]() for j in range(idx))

        if not blocked and not getters[idx]():
            return "content"
        return self._pending_mode(idx, tail, getters, indices)

    @staticmethod
    def _pending_mode(idx: int, tail: str, getters: list[Callable[[], bool]], indices: Any) -> str:
        if tail == "visible":
            return "fallback"
        if tail == "hidden":
            return "hidden"
        # tail="collapsed": only the first still-loading boundary (in
        # reveal order) shows its fallback.
        for j in indices:
            if getters[j]():
                return "fallback" if j == idx else "hidden"
        return "hidden"


def Reveal(
    children: Any = None,
    *,
    order: RevealOrder = "forwards",
    tail: RevealTail = "visible",
) -> VNode:
    """Coordinate the reveal order of multiple [`Loading`][wybthon.Loading] boundaries.

    Each `Loading` boundary mounted underneath (that isn't nested
    inside another boundary) registers with the `Reveal` in mount
    order, and the `Reveal` decides when each may show its content and
    whether it shows its fallback.

    Args:
        children: Content containing one or more `Loading` boundaries.
        order: `"forwards"` (default; contents reveal top-to-bottom,
            each waiting for the ones before it), `"backwards"`
            (bottom-to-top), or `"together"` (all reveal at once when
            every boundary has loaded).
        tail: Fallback policy for still-pending boundaries.
            `"visible"` (default) shows every pending boundary's
            fallback, `"collapsed"` shows only the next fallback in
            reveal order, and `"hidden"` shows none.

    Returns:
        A component [`VNode`][wybthon.VNode].

    Example:
        ```python
        Reveal(
            [
                Loading(PanelA(), fallback=p("Loading A...")),
                Loading(PanelB(), fallback=p("Loading B...")),
            ],
            order="forwards",
            tail="collapsed",
        )
        ```

    Note:
        Every boundary's content mounts immediately (parked
        off-document while pending), so all of them load in parallel;
        `order` only controls when each is revealed.
    """
    if order not in ("forwards", "backwards", "together"):
        raise ValueError('order must be "forwards", "backwards", or "together"')
    if tail not in ("visible", "collapsed", "hidden"):
        raise ValueError('tail must be "visible", "collapsed", or "hidden"')
    return h(_Reveal, {"children": children, "order": order, "tail": tail})


def _Reveal(props: Props) -> Any:
    state = _RevealState(props.raw("order"), props.raw("tail"))
    owner = _core._current_owner
    if owner is not None:
        owner._set_context(REVEAL_CONTEXT_KEY, state)
    return _render_content(props.raw("children"))


_Reveal.__name__ = "Reveal"

"""`Loading` and `Reveal`: fallback UI for async computations.

[`Loading`][wybthon.Loading] is the async boundary (SolidJS 2.0's
`Loading`, the successor to `Suspense`). It covers **initial
readiness**: any read of an async computation under the boundary that
raises [`NotReadyError`][wybthon.NotReadyError] registers the
computation with the boundary, and the boundary shows its fallback
until every registered computation has produced its first value.

Once content is on screen the boundary gets out of the way. A recompute
of an async memo that already has a value is a *transition*: the parts
of the UI that depend on the changed input hold their previous state
until the new value lands, and the boundary never shows its fallback
again. Use [`is_pending`][wybthon.is_pending] to render inline refresh
hints. Pass `on=` to opt back into the fallback for specific changes
(swapping the record being shown rather than refreshing it).

[`Reveal`][wybthon.Reveal] coordinates multiple `Loading` boundaries
beneath it, controlling the order their contents reveal (`order`) and
whether every pending boundary shows its own fallback (`collapsed`).

Example:
    ```python
    async def load_user():
        return await fetch_json(f"/api/users/{user_id()}")

    user = create_memo(load_user)

    Loading(
        lambda: div(lambda: user()["name"]),
        fallback=lambda: p("Loading..."),
        on=user_id,
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
from .reactivity._primitives import create_effect, on_cleanup
from .reactivity._props import Props
from .vnode import Fragment, VNode, h, hole, to_text_vnode

__all__ = ["Loading", "Reveal"]

# Owner-context key under which ``Reveal`` stores its coordinator.
REVEAL_CONTEXT_KEY = "__wyb_reveal__"

_NOT_READY = object()


class _LoadingCollector:
    """Tracks not-ready async computations read under one Loading boundary."""

    __slots__ = ("_version", "_pending", "_forced", "_on_round")

    def __init__(self) -> None:
        self._version: Signal[int] = Signal(0)
        self._pending: set[Computation] = set()
        # Computations that already had a value when they went pending
        # but should show the fallback anyway because the boundary's
        # ``on`` inputs changed in the same round.
        self._forced: set[Computation] = set()
        # The flush round in which an ``on`` value last changed.
        self._on_round: int = -1

    def _bump(self) -> None:
        self._version._commit_now(self._version._value + 1, _core._O_REVEAL)

    def register(self, comp: Computation) -> None:
        """Called by the reactive core when a read raises `NotReadyError`."""
        if comp in self._pending:
            return
        self._pending.add(comp)
        self._bump()

    def note_on_changed(self) -> None:
        """Called by the boundary's ``on`` tracker when one of its values changed."""
        self._on_round = _core._round

    def wants_fallback(self, comp: Computation) -> bool:
        """Called by the scheduler when `comp`, which has a value, went pending.

        Returns True to show the fallback (and not hold a transition)
        because an ``on`` input of this boundary changed this round.
        """
        if self._on_round != _core._round:
            return False
        self._forced.add(comp)
        self._pending.add(comp)
        self._bump()
        return True

    def is_loading(self) -> bool:
        """Tracked read: True while any registered computation is still loading.

        Computations that have produced a first value are pruned (unless
        forced by ``on``), so a later revalidation can't re-trigger the
        boundary.
        """
        self._version()
        done = []
        forced = self._forced
        for comp in self._pending:
            a = comp._async
            still_loading = a is not None and a.pending and not comp._disposed and (not a.has_value or comp in forced)
            if still_loading:
                # Subscribe to the transition out of the pending state.
                _core._track_source(comp)
            else:
                done.append(comp)
        for comp in done:
            self._pending.discard(comp)
            forced.discard(comp)
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
        on: An accessor, or list of accessors, naming the boundary's
            inputs. The boundary waits for them initially even if the
            children never read them, and when one of them **changes**
            while data under the boundary is pending, the fallback
            shows again instead of the old content being held. Use it
            for "new record, fresh boundary" (a route's `id`), not for
            refreshes.

    Returns:
        A component [`VNode`][wybthon.VNode] that toggles between
        fallback and children.

    Example:
        ```python
        Loading(
            lambda: Fragment(Header(), Body()),
            fallback=Spinner(),
            on=user_id,
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

    if waits:
        last: list[Any] = []

        def track_on() -> None:
            # Reads register with our collector (via the owner context) and
            # raise NotReadyError when a source has no value yet; the raise
            # is swallowed because the collector now tracks the source.
            values: list[Any] = []
            for acc in waits:
                try:
                    values.append(acc())
                except NotReadyError:
                    values.append(_NOT_READY)
            if last and values != last:
                collector.note_on_changed()
            last[:] = values

        # A render effect so the change is recorded before the round decides
        # whether the pending data it caused holds a transition.
        tracker = Computation(track_on, kind=_core._K_RENDER, pass_prev=False)
        if owner is not None:
            owner._add_child(tracker)
        tracker._update_if_necessary()

    def mode() -> str:
        if reveal is not None:
            return reveal.display_mode(reveal_index)
        return "fallback" if collector.is_loading() else "content"

    # The content stays mounted the whole time, so async computations
    # created inside it keep running while the fallback shows. While
    # pending, its DOM nodes are parked in a detached element and moved
    # back in front of the fallback hole once everything has resolved.
    shown: Signal[str] = Signal("content")
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
        # Framework UI state: reveals even while a transition holds data.
        shown._set(current, _core._O_REVEAL)

    # A user effect: its first run happens after the initial mount has
    # committed, when the content's DOM nodes exist to be parked.
    create_effect(mode, apply)

    return Fragment(content, fallback_hole)


_Loading.__name__ = "Loading"


# ---------------------------------------------------------------------------
# Reveal
# ---------------------------------------------------------------------------

RevealOrder = Literal["sequential", "together", "natural"]


class _RevealState:
    """Coordinates reveal order across the boundaries under one Reveal."""

    __slots__ = ("_order", "_collapsed", "_getters", "_version", "_parent", "_parent_index")

    def __init__(self, order: str, collapsed: bool, parent: _RevealState | None) -> None:
        self._order = order
        self._collapsed = collapsed
        self._getters: list[Callable[[], bool]] = []
        # Bumped when a boundary registers so already-rendered siblings
        # re-evaluate their display mode.
        self._version: Signal[int] = Signal(0)
        # A nested Reveal is one composite slot in its parent's order.
        self._parent = parent
        self._parent_index = parent.register(self.is_loading) if parent is not None else -1

    def register(self, loading_getter: Callable[[], bool]) -> int:
        """Add a slot's tracked loading getter; returns its position."""
        self._getters.append(loading_getter)
        self._version._commit_now(self._version._value + 1, _core._O_REVEAL)
        return len(self._getters) - 1

    def is_loading(self) -> bool:
        """Tracked read: True while any slot of this group is still loading."""
        self._version()
        return any(g() for g in self._getters)

    def gate(self, idx: int) -> str | None:
        """Tracked read: `None` once the group's order has released slot `idx`.

        Otherwise the mode a not-yet-released slot shows (`"fallback"`
        or `"hidden"`). A nested group asks its parent first: its slot
        must be released before its own order applies.
        """
        parent = self._parent
        if parent is not None:
            blocked = parent.gate(self._parent_index)
            if blocked is not None:
                return blocked
        self._version()
        order = self._order
        if order == "natural":
            return None
        loading = [g() for g in self._getters]
        if order == "together":
            return "fallback" if any(loading) else None
        # sequential: released once every earlier slot has resolved.
        if not any(loading[:idx]):
            return None
        if not self._collapsed:
            return "fallback"
        # Only the frontier (the first still-loading slot) shows its fallback.
        for j, is_loading in enumerate(loading):
            if is_loading:
                return "fallback" if j == idx else "hidden"
        return "hidden"

    def display_mode(self, idx: int) -> str:
        """Tracked read: what the leaf boundary in slot `idx` should render.

        Returns:
            `"content"`, `"fallback"`, or `"hidden"`.
        """
        blocked = self.gate(idx)
        if blocked is not None:
            return blocked
        return "fallback" if self._getters[idx]() else "content"


def Reveal(
    children: Any = None,
    *,
    order: RevealOrder = "sequential",
    collapsed: bool = False,
) -> VNode:
    """Coordinate the reveal order of multiple [`Loading`][wybthon.Loading] boundaries.

    Each `Loading` boundary mounted underneath (that isn't nested
    inside another boundary) registers with the `Reveal` in mount
    order, and the `Reveal` decides when each may show its content and
    whether it shows its fallback. A `Reveal` nested inside another is
    one composite slot in the parent's order: its boundaries stay on
    their fallbacks until the parent releases the slot, then follow the
    inner `order`.

    Args:
        children: Content containing one or more `Loading` boundaries.
        order: `"sequential"` (default; contents reveal in DOM order,
            each waiting for the ones before it), `"together"` (the
            whole group reveals at once when every boundary has
            loaded), or `"natural"` (each boundary reveals on its own
            data; useful for a nested group that should count as one
            slot in the parent without coordinating internally).
        collapsed: Only consulted with `order="sequential"`. When
            `True`, boundaries past the current frontier render nothing
            instead of their own fallback, so only one fallback shows.

    Returns:
        A component [`VNode`][wybthon.VNode].

    Example:
        ```python
        Reveal(
            [
                Loading(PanelA(), fallback=p("Loading A...")),
                Loading(PanelB(), fallback=p("Loading B...")),
            ],
            collapsed=True,
        )
        ```

    Note:
        Every boundary's content mounts immediately (parked
        off-document while pending), so all of them load in parallel;
        `order` only controls when each is revealed.
    """
    if order not in ("sequential", "together", "natural"):
        raise ValueError('order must be "sequential", "together", or "natural"')
    if not isinstance(collapsed, bool):
        raise ValueError("collapsed must be a bool")
    return h(_Reveal, {"children": children, "order": order, "collapsed": collapsed})


def _Reveal(props: Props) -> Any:
    owner = _core._current_owner
    parent = owner._lookup_context(REVEAL_CONTEXT_KEY, None) if owner is not None else None
    state = _RevealState(props.raw("order"), props.raw("collapsed"), parent)
    if owner is not None:
        owner._set_context(REVEAL_CONTEXT_KEY, state)
    return _render_content(props.raw("children"))


_Reveal.__name__ = "Reveal"

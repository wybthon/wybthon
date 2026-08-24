"""`Loading` and `LoadingList`: fallback UI for async computations.

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

[`LoadingList`][wybthon.LoadingList] coordinates multiple `Loading`
boundaries beneath it, controlling the order their contents reveal
(`reveal_order`) and how many fallbacks show at once (`tail`).

Example:
    ```python
    async def load_user():
        return await fetch_json("/api/user")

    user = create_memo(load_user)

    Loading(
        fallback=lambda: p("Loading..."),
        children=[div(lambda: user()["name"])],
    )
    ```

See Also:
    - [Async and loading guide](../concepts/async-loading.md)
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Set

from .reactivity import LOADING_CONTEXT_KEY, Signal, _get_component_ctx
from .vnode import Fragment, VNode, dynamic, h, to_text_vnode

__all__ = ["Loading", "LoadingList"]

# Owner-context key under which ``LoadingList`` stores its coordinator.
LOADING_LIST_CONTEXT_KEY = "__wyb_loading_list__"


class _LoadingCollector:
    """Tracks not-ready async computations read under one Loading boundary."""

    __slots__ = ("_version", "_pending")

    def __init__(self) -> None:
        self._version: Signal[int] = Signal(0)
        self._pending: Set[Any] = set()

    def register(self, comp: Any) -> None:
        """Called by the reactive core when a read raises `NotReadyError`."""
        if comp in self._pending:
            return
        self._pending.add(comp)
        self._version.set(self._version.peek() + 1)

    def is_loading(self) -> bool:
        """Tracked read: True while any registered computation has no value.

        Computations that have produced a first value are pruned, so a
        later revalidation (which serves the stale value instead of
        raising) can't re-trigger the boundary.
        """
        self._version.get()
        done = []
        for comp in self._pending:
            a = comp._async
            still_loading = a is not None and a.pending and not a.has_value
            if still_loading:
                # Subscribe to the transition out of the pending state.
                comp._pending_sig().get()
            else:
                done.append(comp)
        for comp in done:
            self._pending.discard(comp)
        return bool(self._pending)


def Loading(fallback: Any = None, children: Any = None) -> VNode:
    """Show a fallback while async reads under the boundary aren't ready.

    Args:
        fallback: `VNode`, string, or callable returning one of those.
            Shown while any registered async computation has no value
            yet.
        children: Children rendered when nothing is loading. Async
            computations read anywhere in this subtree self-register
            with the boundary when a read raises
            [`NotReadyError`][wybthon.NotReadyError].

    Returns:
        A component [`VNode`][wybthon.VNode] that toggles between
        fallback and children.
    """
    return h(_LoadingComponent, {"fallback": fallback, "children": children})


def _LoadingComponent(props: Any) -> Any:
    """Internal component backing [`Loading`][wybthon.Loading]."""
    collector = _LoadingCollector()
    ctx = _get_component_ctx()
    list_state: Optional[_LoadingListState] = None
    list_index = -1
    if ctx is not None:
        ctx._set_context(LOADING_CONTEXT_KEY, collector)
        list_state = ctx._lookup_context(LOADING_LIST_CONTEXT_KEY, None)
        if list_state is not None:
            list_index = list_state.register(collector.is_loading)
            # Boundaries nested inside this one coordinate with this
            # boundary, not with the outer list.
            ctx._set_context(LOADING_LIST_CONTEXT_KEY, None)

    def _render_children() -> VNode:
        children = props.value("children")
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    def _render_fallback() -> VNode:
        fb = props.value("fallback")
        vnode: Any
        if callable(fb) and not isinstance(fb, VNode):
            try:
                vnode = fb()
            except Exception:
                vnode = to_text_vnode("Loading...")
        else:
            vnode = fb if isinstance(fb, VNode) else to_text_vnode("" if fb is None else str(fb))
        if not isinstance(vnode, VNode):
            vnode = to_text_vnode(vnode)
        return vnode

    def render() -> VNode:
        if list_state is not None:
            mode = list_state.display_mode(list_index)
            if mode == "content":
                return _render_children()
            if mode == "fallback":
                return _render_fallback()
            return to_text_vnode("")
        if collector.is_loading():
            return _render_fallback()
        return _render_children()

    return dynamic(render)


_LoadingComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LoadingList
# ---------------------------------------------------------------------------


class _LoadingListState:
    """Coordinates reveal order across the boundaries under one list."""

    __slots__ = ("_reveal_order", "_tail", "_getters", "_version")

    def __init__(self, reveal_order: str, tail: Optional[str]) -> None:
        self._reveal_order = reveal_order
        self._tail = tail
        self._getters: List[Callable[[], bool]] = []
        # Bumped when a boundary registers so already-rendered siblings
        # re-evaluate their display mode.
        self._version: Signal[int] = Signal(0)

    def register(self, loading_getter: Callable[[], bool]) -> int:
        """Add a boundary's tracked loading getter; returns its position."""
        self._getters.append(loading_getter)
        self._version.set(self._version.peek() + 1)
        return len(self._getters) - 1

    def display_mode(self, idx: int) -> str:
        """Tracked read: what boundary `idx` should render.

        Returns:
            `"content"`, `"fallback"`, or `"hidden"`.
        """
        self._version.get()
        getters = self._getters
        order = self._reveal_order
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
    def _pending_mode(idx: int, tail: Optional[str], getters: List[Callable[[], bool]], indices: Any) -> str:
        if tail is None:
            return "fallback"
        if tail == "hidden":
            return "hidden"
        # tail="collapsed": only the first still-loading boundary (in
        # reveal order) shows its fallback.
        for j in indices:
            if getters[j]():
                return "fallback" if j == idx else "hidden"
        return "hidden"


def LoadingList(children: Any = None, reveal_order: str = "forwards", tail: Optional[str] = None) -> VNode:
    """Coordinate the reveal order of multiple [`Loading`][wybthon.Loading] boundaries.

    Each `Loading` boundary mounted underneath (that isn't nested
    inside another boundary) registers with the list in mount order,
    and the list decides when each may reveal its content and whether
    it shows its fallback.

    Args:
        children: Children containing one or more `Loading`
            boundaries.
        reveal_order: One of `"forwards"` (default; contents reveal
            top-to-bottom, each waiting for the ones before it),
            `"backwards"` (bottom-to-top), or `"together"` (all reveal
            at once when every boundary has loaded).
        tail: Fallback policy for still-pending boundaries. `None`
            (default) shows every pending boundary's fallback,
            `"collapsed"` shows only the next fallback in reveal order,
            and `"hidden"` shows none.

    Returns:
        A component [`VNode`][wybthon.VNode].

    Example:
        ```python
        LoadingList(
            reveal_order="forwards",
            tail="collapsed",
            children=[
                Loading(fallback=p("Loading A..."), children=[PanelA()]),
                Loading(fallback=p("Loading B..."), children=[PanelB()]),
            ],
        )
        ```

    Note:
        A boundary whose content hasn't mounted yet doesn't start its
        async computations, so `"forwards"` reveals sequentially-loading
        content as a cascade rather than loading everything in
        parallel. Start the memos outside the boundaries (or pass them
        down as props) when parallel loading matters.
    """
    if reveal_order not in ("forwards", "backwards", "together"):
        raise ValueError('reveal_order must be "forwards", "backwards", or "together"')
    if tail not in (None, "collapsed", "hidden"):
        raise ValueError('tail must be None, "collapsed", or "hidden"')
    return h(
        _LoadingListComponent,
        {"children": children, "reveal_order": reveal_order, "tail": tail},
    )


def _LoadingListComponent(props: Any) -> Any:
    """Internal component backing [`LoadingList`][wybthon.LoadingList]."""
    state = _LoadingListState(props.value("reveal_order"), props.value("tail"))
    ctx = _get_component_ctx()
    if ctx is not None:
        ctx._set_context(LOADING_LIST_CONTEXT_KEY, state)

    children = props.value("children")
    if children is None:
        children = []
    if not isinstance(children, list):
        children = [children]
    return Fragment(*children)


_LoadingListComponent._wyb_component = True  # type: ignore[attr-defined]

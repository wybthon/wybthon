"""SolidJS-style reactive flow control components.

These components create **isolated reactive scopes** so that only the
relevant subtree re-renders when the tracked condition or list changes.

Each flow control is a factory function returning a component VNode;
conditions, sources, children, and fallbacks are accepted as **getters**
(zero-arg callables) so that reads happen inside the flow control's own
reactive effect, not the parent's.

API rules:

- `when` / `each`: pass a *getter* (the signal accessor itself) or a raw
  value. Getters are called inside the flow control's own scope.
- `children`: may be a `VNode`, a callable returning a `VNode`, or
  (for `For` / `Repeat`) the per-item mapping callback.
- `fallback`: same flexibility as `children`.

List rendering (unified, matching SolidJS 2.0):

- [`For`][wybthon.For] renders a list with **stable per-item subtrees**
  and three keying modes selected by the `key` argument: reference
  identity (default), a key-extractor callable, or `"index"` for
  per-position slots. The mapping callback runs exactly once per unique
  item; on list changes, existing rows keep their DOM and are only
  *moved*, never re-diffed.
- [`Repeat`][wybthon.Repeat] renders by count, with no list diffing at
  all: changing the count mounts or disposes tail slots only.

Example:
    ```python
    Show(when=is_logged_in,
         children=lambda: p("Welcome!"),
         fallback=lambda: p("Please log in"))

    For(each=todos,
        key=lambda t: t["id"],
        children=lambda item, idx: li(lambda: item()["title"]))

    Repeat(times=count, children=lambda i: span(f"#{i}"))
    ```
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ._warnings import warn_each_plain_list
from .reactivity import ReactiveProps
from .vnode import Fragment, VNode, dynamic, h, is_getter, to_text_vnode

__all__ = ["Show", "For", "Repeat", "Switch", "Match", "Dynamic"]


def _eval(v: Any) -> Any:
    """If `v` is a zero-arg getter, call it; otherwise return as-is."""
    return v() if is_getter(v) else v


def _to_vnode(v: Any) -> VNode:
    """Coerce an arbitrary value to a `VNode`, defaulting to text content."""
    if isinstance(v, VNode):
        return v
    return to_text_vnode("" if v is None else str(v))


def _render_slot(slot: Any, *args: Any) -> VNode:
    """Render a `children` / `fallback` slot.

    Per-slot handling:

    - If `slot` is a `VNode`, return it directly.
    - If `slot` is callable, call it (forwarding positional args when
      the signature accepts them) and coerce the result to a `VNode`.
    - Otherwise, coerce to a text `VNode`.
    """
    if isinstance(slot, VNode):
        return slot
    if callable(slot):
        if args:
            from .vnode import _signature_has_required_positional

            if _signature_has_required_positional(slot):
                result = slot(*args)
            else:
                result = slot()
        else:
            result = slot()
        return _to_vnode(result)
    return _to_vnode(slot)


def _raw_prop(props: ReactiveProps, name: str) -> Any:
    """Return the raw (un-unwrapped) prop value for `name`."""
    raw = object.__getattribute__(props, "_raw")
    defaults = object.__getattribute__(props, "_defaults")
    return raw.get(name, defaults.get(name))


def _maybe_warn_plain_each(component: Any, props: ReactiveProps) -> None:
    """Warn (dev mode) when `each=` is a plain list rather than a getter."""
    if isinstance(_raw_prop(props, "each"), (list, tuple)):
        warn_each_plain_list(component)


def _normalize_children_callback(value: Any) -> Any:
    """Unwrap a single-callable `children` list into the raw callable.

    `h(...)` wraps children in a list; the direct-call form passes the
    bare callable. Both must resolve to the mapping function.
    """
    if isinstance(value, list) and len(value) == 1 and callable(value[0]):
        return value[0]
    return value


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def Show(when: Any = None, children: Any = None, fallback: Any = None) -> VNode:
    """Conditionally render `children` when `when` is truthy.

    ```python
    Show(when=count, children=lambda: p("Count: ", count),
         fallback=lambda: p("Empty"))
    ```

    Behavior:

    - `when` may be a zero-arg getter or a plain value.
    - `children` / `fallback` may be a `VNode`, a callable, or a plain
      value. When `children` is callable and `when` is truthy, the
      truthy value is passed as the first argument (matching SolidJS
      `<Show>`).

    The component creates a **keyed conditional scope**: when the
    truthiness of `when` changes, the previous branch's scope is
    disposed and a new scope is created. This ensures that effects and
    cleanups registered inside a branch are properly torn down on
    transitions.

    Args:
        when: Condition value or zero-arg getter.
        children: Slot rendered when the condition is truthy.
        fallback: Slot rendered when the condition is falsy.

    Returns:
        A component [`VNode`][wybthon.VNode] that re-renders when the
        condition's truthiness changes.
    """
    return h(_ShowComponent, {"when": when, "children": children, "fallback": fallback})


def _ShowComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`Show`][wybthon.Show]."""
    import wybthon.reactivity as _rx

    comp_ctx = _rx._get_component_ctx()

    _branch: List[Optional[str]] = [None]
    _branch_owner: List[Optional[_rx.Owner]] = [None]

    def render() -> VNode:
        condition = _eval(props.value("when"))
        new_branch = "truthy" if condition else "falsy"

        if _branch[0] != new_branch:
            if _branch_owner[0] is not None:
                _branch_owner[0].dispose()
            owner = _rx.Owner()
            if comp_ctx is not None:
                comp_ctx._add_child(owner)
            _branch_owner[0] = owner
            _branch[0] = new_branch

        if condition:
            children = props.value("children")
            if children is None:
                return to_text_vnode("")
            return _render_slot(children, condition)

        fb = props.value("fallback")
        if fb is None:
            return to_text_vnode("")
        return _render_slot(fb)

    return dynamic(render)


_ShowComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def For(each: Any = None, children: Any = None, fallback: Any = None, key: Any = None) -> VNode:
    """Render a list of items using a per-item mapping function.

    ```python
    For(each=items,
        children=lambda item, index: li(item()))
    ```

    Inside the callback, `item` is a **signal-backed getter** returning
    the current item value, and `index` is a signal-backed getter
    returning the current integer index. The mapping callback runs
    **exactly once per unique item**, and the rendered subtree is
    cached. When the list changes, unchanged rows keep their DOM
    untouched; the reconciler only mounts additions, unmounts removals,
    and moves reordered rows. When an item leaves the list, its
    reactive scope (including any effects or cleanups created inside
    the callback) is disposed.

    **Keying modes** (matching SolidJS 2.0's unified list component):

    - `key=None` (default): rows match by **reference identity**. The
      same object keeps its row; a replacement object makes a new row.
    - `key=callable`: rows match by `key(item)`. A fresh object with
      the same key **updates the existing row in place** through the
      `item` getter; ideal for data refreshed from a server.
    - `key="index"`: rows match by **position**. The row at each index
      renders once and its `item` getter updates when the value at
      that position changes (the old `Index` component).

    Args:
        each: List getter (typically a signal accessor) or plain list.
        children: A `(item_getter, index_getter) -> VNode` callable.
        fallback: Slot rendered when the list is empty.
        key: Keying mode: `None`, a key-extractor callable, or the
            string `"index"`.

    Returns:
        A component [`VNode`][wybthon.VNode].
    """
    return h(_ForComponent, {"each": each, "children": children, "fallback": fallback, "key_mode": key})


def _ForComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`For`][wybthon.For] with cached per-item rows."""
    import wybthon.reactivity as _rx

    _maybe_warn_plain_each(_ForComponent, props)

    def source() -> Any:
        return _eval(props.value("each")) or None

    # The mapping callback and keying mode are fixed at setup (matching
    # SolidJS, where the <For> children function can't be swapped
    # reactively); resolving them once keeps the per-row path
    # allocation-free.
    children_fn = _normalize_children_callback(_rx.untrack(lambda: props.value("children")))
    key_mode = _rx.untrack(lambda: props.value("key_mode"))

    def map_row(item: Callable[[], Any], index: Callable[[], int]) -> VNode:
        if children_fn is None:
            return to_text_vnode("")
        vnode = _to_vnode(children_fn(item, index))
        # Mounting happens later, inside the list's re-running render
        # effect; pin it to the row's owner so row-local effects survive
        # subsequent list updates.
        vnode.owner_scope = _rx._current_owner
        return vnode

    if key_mode == "index":

        def map_slot(item: Callable[[], Any], index: int) -> VNode:
            return map_row(item, lambda: index)

        rows = _rx.index_array(source, map_slot)
    elif callable(key_mode):
        rows = _rx.map_array(source, map_row, key=key_mode)
    else:
        rows = _rx.map_array(source, map_row)

    def render() -> VNode:
        vnodes = rows()
        if not vnodes:
            fb = props.value("fallback")
            return _render_slot(fb) if fb is not None else to_text_vnode("")
        return Fragment(*vnodes)

    return dynamic(render)


_ForComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Repeat
# ---------------------------------------------------------------------------


def Repeat(times: Any = None, children: Any = None, fallback: Any = None) -> VNode:
    """Render `children(i)` for each index in `range(times)`, with no diffing.

    Matches SolidJS 2.0's `Repeat`: rendering is driven purely by the
    count. Growing the count mounts new tail slots; shrinking disposes
    excess tail slots; nothing else is touched. Use it for
    pagination dots, star ratings, skeleton rows, and other
    count-driven UI where list diffing is pure overhead.

    Args:
        times: Count value or zero-arg getter.
        children: A `(index: int) -> VNode` callable, rendered once per
            slot.
        fallback: Slot rendered when the count is zero.

    Returns:
        A component [`VNode`][wybthon.VNode].

    Example:
        ```python
        rating, set_rating = create_signal(3)
        Repeat(times=rating, children=lambda i: span("*"))
        ```
    """
    return h(_RepeatComponent, {"times": times, "children": children, "fallback": fallback})


def _RepeatComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`Repeat`][wybthon.Repeat] with per-index slots."""
    import wybthon.reactivity as _rx

    children_fn = _normalize_children_callback(_rx.untrack(lambda: props.value("children")))

    def source() -> Any:
        count = _eval(props.value("times"))
        try:
            n = int(count) if count else 0
        except (TypeError, ValueError):
            n = 0
        return list(range(n)) if n > 0 else None

    def map_slot(item: Callable[[], Any], index: int) -> VNode:
        if children_fn is None:
            return to_text_vnode("")
        vnode = _to_vnode(children_fn(index))
        vnode.owner_scope = _rx._current_owner
        return vnode

    slots = _rx.index_array(source, map_slot)

    def render() -> VNode:
        vnodes = slots()
        if not vnodes:
            fb = props.value("fallback")
            return _render_slot(fb) if fb is not None else to_text_vnode("")
        return Fragment(*vnodes)

    return dynamic(render)


_RepeatComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


class _MatchResult:
    """Sentinel returned by [`Match`][wybthon.Match] for a [`Switch`][wybthon.Switch] branch."""

    __slots__ = ("when", "children")

    def __init__(self, when: Any, children: Any) -> None:
        """Capture the branch's `when` predicate and `children` slot."""
        self.when = when
        self.children = children


def Match(when: Any = None, children: Any = None) -> _MatchResult:
    """Declare a branch inside a [`Switch`][wybthon.Switch].

    `when` may be a getter or a plain value:

    ```python
    Match(when=lambda: x() > 0, children=lambda: p("positive"))
    ```

    Must be used inside [`Switch()`][wybthon.Switch].

    Args:
        when: Predicate value or zero-arg getter.
        children: A `VNode`, a callable returning a `VNode`, or a plain
            value to coerce to text.

    Returns:
        An opaque branch descriptor consumed by `Switch`.
    """
    return _MatchResult(when=when, children=children)


def Switch(*branches: _MatchResult, fallback: Any = None) -> VNode:
    """Render the first matching [`Match`][wybthon.Match] branch, or `fallback`.

    ```python
    Switch(
        Match(when=lambda: status() == "loading",
              children=lambda: p("Loading...")),
        Match(when=lambda: status() == "ready",
              children=lambda: p("Ready")),
        fallback=lambda: p("Unknown"),
    )
    ```

    Each `Match` `when` is evaluated lazily inside the `Switch`
    component's reactive scope. Each branch renders inside its own
    ownership scope: switching branches disposes the previous branch's
    effects and cleanups before the next branch mounts, matching
    [`Show`][wybthon.Show].

    Args:
        *branches: One or more `Match` results, in priority order.
        fallback: Slot to render when no branch matches. May be a
            `VNode`, a callable, or a plain value.

    Returns:
        A component [`VNode`][wybthon.VNode] for the first matching
        branch, or the `fallback` slot.
    """
    match_branches = [b for b in branches if isinstance(b, _MatchResult)]
    return h(_SwitchComponent, {"branches": match_branches, "fallback": fallback})


def _SwitchComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`Switch`][wybthon.Switch]."""
    import wybthon.reactivity as _rx

    comp_ctx = _rx._get_component_ctx()

    _active: List[Optional[int]] = [None]
    _branch_owner: List[Optional[_rx.Owner]] = [None]

    def _enter_branch(index: Optional[int]) -> None:
        if _active[0] == index:
            return
        if _branch_owner[0] is not None:
            _branch_owner[0].dispose()
        owner = _rx.Owner()
        if comp_ctx is not None:
            comp_ctx._add_child(owner)
        _branch_owner[0] = owner
        _active[0] = index

    def render() -> VNode:
        branches: List[_MatchResult] = props.value("branches") or []
        for i, branch in enumerate(branches):
            condition = _eval(branch.when)
            if condition:
                _enter_branch(i)
                return _render_slot(branch.children)

        _enter_branch(-1)
        fb = props.value("fallback")
        if fb is None:
            return to_text_vnode("")
        return _render_slot(fb)

    return dynamic(render)


_SwitchComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


def Dynamic(
    component: Any = None,
    props: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> VNode:
    """Render a dynamically-chosen component.

    `component` may be a string tag name, a component function, or
    `None` (renders nothing). It can also be a getter for reactive
    switching.

    Args:
        component: Tag name, component callable, getter, or `None`.
        props: Optional dict of props forwarded to the resolved
            component.
        **kwargs: Additional props (merged on top of `props`).

    Returns:
        A component [`VNode`][wybthon.VNode] that re-mounts whenever
        the resolved component identity changes.

    Example:
        ```python
        Dynamic(component=lambda: heading_level(),
                children=[f"Section {idx}"])
        ```
    """
    merged: Dict[str, Any] = {"component": component}
    if props:
        merged.update(props)
    merged.update(kwargs)
    return h(_DynamicComponent, merged)


def _DynamicComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`Dynamic`][wybthon.Dynamic]."""

    def render() -> VNode:
        comp = _eval(props.value("component"))
        if comp is None:
            return to_text_vnode("")
        inner_props: Dict[str, Any] = {k: props.value(k) for k in props if k != "component"}
        children = inner_props.pop("children", [])
        if not isinstance(children, list):
            children = [children]
        return h(comp, inner_props, *children)

    return dynamic(render)


_DynamicComponent._wyb_component = True  # type: ignore[attr-defined]

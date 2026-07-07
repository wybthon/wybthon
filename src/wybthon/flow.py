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
  (for `For` / `Index`) the per-item mapping callback.
- `fallback`: same flexibility as `children`.

Fine-grained list primitives:

- [`For`][wybthon.For] maintains **stable per-item rendered subtrees**
  (keyed by reference identity) on top of
  [`map_array`][wybthon.map_array]. The mapping callback runs exactly
  once per unique item; on list changes, existing rows keep their DOM
  and are only *moved*, never re-diffed.
- [`Index`][wybthon.Index] maintains **stable per-index subtrees** on
  top of [`index_array`][wybthon.index_array], with a reactive item
  signal that updates when the value at that position changes.

Example:
    ```python
    Show(when=is_logged_in,
         children=lambda: p("Welcome!"),
         fallback=lambda: p("Please log in"))

    For(each=items,
        children=lambda item, idx: li(item()))
    ```
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ._warnings import warn_each_plain_list
from .reactivity import ReactiveProps
from .vnode import Fragment, VNode, dynamic, h, is_getter, to_text_vnode

__all__ = ["Show", "For", "Index", "Switch", "Match", "Dynamic"]


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


def For(each: Any = None, children: Any = None, fallback: Any = None) -> VNode:
    """Render a list of items using a per-item mapping function.

    ```python
    For(each=items,
        children=lambda item, index: li(item()))
    ```

    Inside the callback, `item` is a **signal-backed getter** returning
    the current item value, and `index` is a signal-backed getter
    returning the current integer index, matching SolidJS `<For>`.

    `For` is built on [`map_array`][wybthon.map_array]: the mapping
    callback runs **exactly once per unique item** (keyed by reference
    identity), and the rendered subtree is cached. When the list
    changes, unchanged rows keep their DOM untouched; the reconciler
    only mounts additions, unmounts removals, and moves reordered rows.
    When an item leaves the list, its reactive scope (including any
    effects or cleanups created inside the callback) is disposed.

    Args:
        each: List getter (typically a signal accessor) or plain list.
        children: A `(item_getter, index_getter) -> VNode` callable.
        fallback: Slot rendered when the list is empty.

    Returns:
        A component [`VNode`][wybthon.VNode].
    """
    return h(_ForComponent, {"each": each, "children": children, "fallback": fallback})


def _ForComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`For`][wybthon.For] with cached per-item rows."""
    import wybthon.reactivity as _rx

    _maybe_warn_plain_each(_ForComponent, props)

    def source() -> Any:
        return _eval(props.value("each")) or None

    def map_row(item: Callable[[], Any], index: Callable[[], int]) -> VNode:
        children_fn = _normalize_children_callback(_rx.untrack(lambda: props.value("children")))
        if children_fn is None:
            return to_text_vnode("")
        vnode = _to_vnode(children_fn(item, index))
        # Mounting happens later, inside the list's re-running render
        # effect; pin it to the row's owner so row-local effects survive
        # subsequent list updates.
        vnode.owner_scope = _rx._current_owner
        return vnode

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
# Index
# ---------------------------------------------------------------------------


def Index(each: Any = None, children: Any = None, fallback: Any = None) -> VNode:
    """Render a list by index with a stable item getter.

    Unlike [`For`][wybthon.For], the `children` callback receives
    `(item_getter, index)` so that the DOM subtree for each index is
    reused even when the underlying data changes.

    `Index` is built on [`index_array`][wybthon.index_array]: each slot
    renders **once** and owns a signal-backed `item_getter` that updates
    when the value at that position changes. Growing the list creates
    and mounts new slots; shrinking disposes and unmounts excess slots.

    Args:
        each: List getter (typically a signal accessor) or plain list.
        children: A `(item_getter, index: int) -> VNode` callable.
        fallback: Slot rendered when the list is empty.

    Returns:
        A component [`VNode`][wybthon.VNode].
    """
    return h(_IndexComponent, {"each": each, "children": children, "fallback": fallback})


def _IndexComponent(props: ReactiveProps) -> Any:
    """Internal component backing [`Index`][wybthon.Index] with per-index slots."""
    import wybthon.reactivity as _rx

    _maybe_warn_plain_each(_IndexComponent, props)

    def source() -> Any:
        return _eval(props.value("each")) or None

    def map_slot(item: Callable[[], Any], index: int) -> VNode:
        children_fn = _normalize_children_callback(_rx.untrack(lambda: props.value("children")))
        if children_fn is None:
            return to_text_vnode("")
        vnode = _to_vnode(children_fn(item, index))
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


_IndexComponent._wyb_component = True  # type: ignore[attr-defined]


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
    component's reactive scope.

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

    def render() -> VNode:
        branches: List[_MatchResult] = props.value("branches") or []
        for branch in branches:
            condition = _eval(branch.when)
            if condition:
                return _render_slot(branch.children)

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

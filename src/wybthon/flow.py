"""SolidJS-style reactive flow control components.

These components create **isolated reactive scopes** so that only the
relevant subtree re-renders when the tracked condition or list changes.

Each flow control is implemented as a proper function component
(returning `dynamic(...)`) rather than a plain helper. Conditions,
sources, children, and fallbacks are accepted as **getters** (zero-arg
callables) so that reads happen inside the flow control's own reactive
effect — not the parent's.

API rules:

- `when` / `each`: pass a *getter* (the signal accessor itself) or a raw
  value. Getters are called inside the flow control's own scope.
- `children`: may be a `VNode`, a callable returning a `VNode`, or
  (for `For` / `Index`) the per-item mapping callback.
- `fallback`: same flexibility as `children`.

Fine-grained list primitives:

- [`For`][wybthon.For] maintains **stable per-item reactive scopes**
  (keyed by reference identity); the mapping callback runs only once
  per unique item.
- [`Index`][wybthon.Index] maintains **stable per-index scopes** with a
  reactive item signal that updates when the value at that position
  changes.

Example:
    ```python
    Show(when=is_logged_in,
         children=lambda: p("Welcome!"),
         fallback=lambda: p("Please log in"))

    For(each=items,
        children=lambda item, idx: li(item(), key=idx()))
    ```
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._warnings import warn_each_plain_list
from .reactivity import ReactiveProps, read_prop
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


def _is_static_list_prop(props: Any, name: str) -> bool:
    """Return True when the *raw* prop value at `name` is a plain list/tuple.

    Bypasses the auto-unwrap that
    [`ReactiveProps.value`][wybthon.ReactiveProps.value] would perform,
    so `For` and `Index` can correctly warn when the user passes
    `each=[1, 2, 3]` instead of a signal accessor.
    """
    if isinstance(props, ReactiveProps):
        raw = object.__getattribute__(props, "_raw")
        defaults = object.__getattribute__(props, "_defaults")
        val = raw.get(name, defaults.get(name))
    elif hasattr(props, "get"):
        val = props.get(name)
    else:
        val = None
    return isinstance(val, (list, tuple))


def _maybe_warn_plain_each(component: Any, props: Any) -> None:
    """Warn (dev mode) when `each=` is a plain list rather than a getter."""
    if _is_static_list_prop(props, "each"):
        warn_each_plain_list(component)


def _normalize_children_callback(value: Any) -> Any:
    """Unwrap a single-callable `children` list into the raw callable.

    `h(For, props, lambda...)` wraps the callback in a one-element list
    (since children is always a list). The direct-call form
    `For(children=...)` passes the bare callable. Both must work.
    """
    if isinstance(value, list) and len(value) == 1 and callable(value[0]):
        return value[0]
    return value


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def Show(props_or_when: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Conditionally render `children` when `when` is truthy.

    Can be called in two styles:

    Component style (reactive — recommended for dynamic conditions):
        ```python
        Show(when=count, children=lambda: p("Count: ", count),
             fallback=lambda: p("Empty"))
        ```

    Direct call (evaluated once — fine inside an explicit hole):
        ```python
        Show(when=lambda: count() > 0,
             children=lambda: p("Positive"),
             fallback=lambda: p("Not positive"))
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
        props_or_when: A props dict (component style) or the `when`
            value (direct call form).
        children_pos: Positional `children` slot (direct call form).
        **kwargs: `when`, `children`, and optional `fallback`.

    Returns:
        A reactive [`VNode`][wybthon.VNode] tree that re-renders when
        the condition's truthiness changes.
    """
    if isinstance(props_or_when, dict) and not kwargs and children_pos is None:
        return _ShowComponent(props_or_when)

    when = kwargs.pop("when", props_or_when)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"when": when, "children": children, "fallback": fallback}
    return h(_ShowComponent, props)


def _ShowComponent(props: Any) -> Any:
    """Internal component backing [`Show`][wybthon.Show]."""
    import wybthon.reactivity as _rx

    comp_ctx = _rx._get_component_ctx()

    _branch: List[Optional[str]] = [None]
    _branch_owner: List[Optional[_rx.Owner]] = [None]

    def render() -> VNode:
        condition = _eval(read_prop(props, "when"))
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
            children = read_prop(props, "children")
            if children is None:
                return to_text_vnode("")
            return _render_slot(children, condition)

        fb = read_prop(props, "fallback")
        if fb is None:
            return to_text_vnode("")
        return _render_slot(fb)

    return dynamic(render)


_ShowComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def For(props_or_each: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Render a list of items using a keyed mapping function.

    Component style (reactive):
        ```python
        For(each=items,
            children=lambda item, index: li(item, key=index()))
        ```

    Inside the callback, `item` is a **signal-backed getter** returning
    the current item value, and `index` is a signal-backed getter
    returning the current integer index — matching SolidJS `<For>`.

    `For` maintains **stable per-item reactive scopes** keyed by
    reference identity. The mapping callback runs only once per unique
    item. When an item leaves the list, its scope (including any
    effects or cleanups created inside the callback) is disposed.

    Args:
        props_or_each: A props dict (component style) or the `each`
            getter / list (direct call form).
        children_pos: Positional `children` callback (direct call form).
        **kwargs: `each`, `children` (a `(item, index_getter) -> VNode`
            callable), and optional `fallback`.

    Returns:
        A reactive [`VNode`][wybthon.VNode] tree that diffs the list by
        item identity.
    """
    if isinstance(props_or_each, (dict, ReactiveProps)) and not kwargs and children_pos is None:
        return _ForComponent(props_or_each)

    each = kwargs.pop("each", props_or_each)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"each": each, "children": children, "fallback": fallback}
    return h(_ForComponent, props)


For._wyb_component = True  # type: ignore[attr-defined]


def _ForComponent(props: Any) -> Any:
    """Internal component backing [`For`][wybthon.For] with per-item scopes."""
    import wybthon.reactivity as _rx

    comp_ctx = _rx._get_component_ctx()

    # (item_ref, owner, item_signal, index_signal)
    _cache: List[Any] = []
    _warned_plain_list: List[bool] = [False]

    def render() -> VNode:
        each_val = read_prop(props, "each")
        if not _warned_plain_list[0]:
            _maybe_warn_plain_each(_ForComponent, props)
            _warned_plain_list[0] = True
        items_val = _eval(each_val)
        children_fn = _normalize_children_callback(read_prop(props, "children"))

        if not items_val:
            for entry in _cache:
                entry[1].dispose()
            _cache.clear()
            fb = read_prop(props, "fallback")
            return _render_slot(fb) if fb is not None else to_text_vnode("")

        if children_fn is None:
            return to_text_vnode("")

        new_cache: List[Any] = []
        used = [False] * len(_cache)

        for idx, item in enumerate(items_val):
            found_ci = -1
            for ci in range(len(_cache)):
                if not used[ci] and item is _cache[ci][0]:
                    found_ci = ci
                    break

            if found_ci >= 0:
                used[found_ci] = True
                _item_ref, owner, item_sig, idx_sig = _cache[found_ci]
                idx_sig.set(idx)
                new_cache.append((_item_ref, owner, item_sig, idx_sig))
            else:
                owner = _rx.Owner()
                if comp_ctx is not None:
                    comp_ctx._add_child(owner)

                item_sig = _rx.Signal(item)
                idx_sig = _rx.Signal(idx)

                new_cache.append((item, owner, item_sig, idx_sig))

        for ci in range(len(_cache)):
            if not used[ci]:
                _cache[ci][1].dispose()

        _cache.clear()
        _cache.extend(new_cache)

        vnodes: List[VNode] = []
        for entry in new_cache:
            _, _, item_sig, idx_sig = entry
            result = children_fn(item_sig.get, idx_sig.get)
            vnodes.append(_to_vnode(result))

        return Fragment(*vnodes)

    return dynamic(render)


_ForComponent._wyb_component = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def Index(props_or_each: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Render a list by index with a stable item getter.

    Unlike [`For`][wybthon.For], the `children` callback receives
    `(item_getter, index)` so that the DOM node for each index is reused
    even when the underlying data changes.

    `Index` maintains **stable per-index reactive scopes**. Each slot
    has a signal-backed `item_getter` that updates when the value at
    that position changes. Growing the list creates new scopes;
    shrinking disposes excess scopes.

    Args:
        props_or_each: A props dict (component style) or the `each`
            getter / list (direct call form).
        children_pos: Positional `children` callback (direct call form).
        **kwargs: `each`, `children` (a `(item_getter, index: int) ->
            VNode` callable), and optional `fallback`.

    Returns:
        A reactive [`VNode`][wybthon.VNode] tree that diffs the list by
        index.
    """
    if isinstance(props_or_each, (dict, ReactiveProps)) and not kwargs and children_pos is None:
        return _IndexComponent(props_or_each)

    each = kwargs.pop("each", props_or_each)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"each": each, "children": children, "fallback": fallback}
    return h(_IndexComponent, props)


Index._wyb_component = True  # type: ignore[attr-defined]


def _IndexComponent(props: Any) -> Any:
    """Internal component backing [`Index`][wybthon.Index] with per-index scopes."""
    import wybthon.reactivity as _rx

    comp_ctx = _rx._get_component_ctx()

    # (owner, item_signal)
    _slots: List[Any] = []
    _warned_plain_list: List[bool] = [False]

    def render() -> VNode:
        each_val = read_prop(props, "each")
        if not _warned_plain_list[0]:
            _maybe_warn_plain_each(_IndexComponent, props)
            _warned_plain_list[0] = True
        items_val = _eval(each_val)
        children_fn = _normalize_children_callback(read_prop(props, "children"))

        if not items_val:
            for slot in _slots:
                slot[0].dispose()
            _slots.clear()
            fb = read_prop(props, "fallback")
            return _render_slot(fb) if fb is not None else to_text_vnode("")

        if children_fn is None:
            return to_text_vnode("")

        items_list = list(items_val)
        new_len = len(items_list)
        old_len = len(_slots)

        for i in range(min(old_len, new_len)):
            _slots[i][1].set(items_list[i])

        if new_len > old_len:
            for i in range(old_len, new_len):
                owner = _rx.Owner()
                if comp_ctx is not None:
                    comp_ctx._add_child(owner)

                item_sig = _rx.Signal(items_list[i])
                _slots.append((owner, item_sig))

        elif new_len < old_len:
            for slot in _slots[new_len:]:
                slot[0].dispose()
            del _slots[new_len:]

        vnodes: List[VNode] = []
        for i in range(new_len):
            item_sig = _slots[i][1]
            result = children_fn(item_sig.get, i)
            vnodes.append(_to_vnode(result))

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


def Match(when: Any = None, children: Any = None, **kwargs: Any) -> _MatchResult:
    """Declare a branch inside a [`Switch`][wybthon.Switch].

    `when` may be a getter or a plain value. Supports both positional
    and keyword calling styles:

    ```python
    Match(True, h("p", {}, "yes"))                                # positional
    Match(when=lambda: x() > 0, children=lambda: p("positive"))   # keyword
    ```

    Must be used inside [`Switch()`][wybthon.Switch].

    Args:
        when: Predicate value or zero-arg getter.
        children: A `VNode`, a callable returning a `VNode`, or a plain
            value to coerce to text.
        **kwargs: Same keys as the explicit parameters; takes priority
            over positional values when provided.

    Returns:
        An opaque branch descriptor consumed by `Switch`.
    """
    w = kwargs.pop("when", when)
    c = kwargs.pop("children", children)
    return _MatchResult(when=w, children=c)


def Switch(*branches: Any, fallback: Any = None, **kwargs: Any) -> Any:
    """Render the first matching [`Match`][wybthon.Match] branch, or `fallback`.

    Component style (reactive):
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
        **kwargs: Optional `fallback` override.

    Returns:
        A reactive [`VNode`][wybthon.VNode] for the first matching
        branch, or the `fallback` slot.
    """
    match_branches = [b for b in branches if isinstance(b, _MatchResult)]
    non_match = [b for b in branches if not isinstance(b, _MatchResult)]

    if non_match and isinstance(non_match[0], dict) and not match_branches:
        return _SwitchComponent(non_match[0])

    fb = kwargs.pop("fallback", fallback)
    props: Dict[str, Any] = {"branches": match_branches, "fallback": fb}
    return h(_SwitchComponent, props)


def _SwitchComponent(props: Any) -> Any:
    """Internal component backing [`Switch`][wybthon.Switch]."""

    def render() -> VNode:
        branches: List[_MatchResult] = read_prop(props, "branches", [])
        for branch in branches:
            condition = _eval(branch.when)
            if condition:
                return _render_slot(branch.children)

        fb = read_prop(props, "fallback")
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
) -> Any:
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
        A reactive [`VNode`][wybthon.VNode] that re-mounts whenever
        the resolved component identity changes.

    Example:
        ```python
        Dynamic(component=lambda: heading_level(),
                children=[f"Section {idx}"])
        ```
    """
    if isinstance(component, dict) and props is None and not kwargs:
        return _DynamicComponent(component)

    merged: Dict[str, Any] = {"component": component}
    if props:
        merged.update(props)
    merged.update(kwargs)
    return h(_DynamicComponent, merged)


def _DynamicComponent(props: Any) -> Any:
    """Internal component backing [`Dynamic`][wybthon.Dynamic]."""

    def render() -> VNode:
        comp = _eval(read_prop(props, "component"))
        if comp is None:
            return to_text_vnode("")
        if isinstance(props, ReactiveProps):
            inner_props: Dict[str, Any] = {k: props.value(k) for k in props if k != "component"}
        else:
            inner_props = {k: v for k, v in props.items() if k != "component"}
        children = inner_props.pop("children", [])
        if not isinstance(children, list):
            children = [children]
        return h(comp, inner_props, *children)

    return dynamic(render)


_DynamicComponent._wyb_component = True  # type: ignore[attr-defined]

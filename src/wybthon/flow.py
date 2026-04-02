"""SolidJS-style reactive flow control components.

These components create **isolated reactive scopes** so that only the
relevant subtree re-renders when the tracked condition or list changes.

Each flow control is a proper function component (returning a render
function) rather than a plain helper.  Conditions, sources, children,
and fallbacks are accepted as **getters** (zero-arg callables) so that
reads happen inside the component's own reactive effect — not the
parent's.

Key API rules
-------------
* ``when`` / ``each`` — pass a *getter* (the signal accessor itself) or
  a raw value.  Getters are called inside the flow control's own scope.
* ``children`` — may be a ``VNode``, a callable returning a ``VNode``,
  or (for ``For`` / ``Index``) the per-item mapping callback.
* ``fallback`` — same flexibility as ``children``.

Fine-grained list primitives
----------------------------
``For`` maintains **stable per-item reactive scopes** (keyed by
reference identity), so the mapping callback runs only once per unique
item.  ``Index`` maintains **stable per-index scopes** with a reactive
item signal that updates when the value at that position changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["Show", "For", "Index", "Switch", "Match", "Dynamic"]


def _is_getter(v: Any) -> bool:
    """Return True if *v* looks like a zero-arg getter (not a component)."""
    if not callable(v):
        return False
    if isinstance(v, type):
        return False
    if getattr(v, "_wyb_component", False):
        return False
    if getattr(v, "_wyb_provider", False):
        return False
    import inspect

    try:
        sig = inspect.signature(v)
        required = [
            p
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
        ]
        return len(required) == 0
    except (ValueError, TypeError):
        return False


def _eval(v: Any) -> Any:
    """If *v* is a zero-arg getter, call it; otherwise return as-is."""
    return v() if _is_getter(v) else v


def _to_vnode(v: Any) -> VNode:
    """Coerce an arbitrary value to a ``VNode``."""
    if isinstance(v, VNode):
        return v
    return to_text_vnode("" if v is None else str(v))


def _render_slot(slot: Any, *args: Any) -> VNode:
    """Render a *children* / *fallback* slot.

    * If *slot* is a ``VNode``, return it directly.
    * If *slot* is callable, call it (with optional positional args
      if the callable accepts them) and coerce the result to a ``VNode``.
    * Otherwise, coerce to a text ``VNode``.
    """
    if isinstance(slot, VNode):
        return slot
    if callable(slot):
        if args:
            import inspect

            try:
                sig = inspect.signature(slot)
                positional = [
                    p
                    for p in sig.parameters.values()
                    if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                    and p.default is inspect.Parameter.empty
                ]
                if positional:
                    result = slot(*args)
                else:
                    result = slot()
            except (ValueError, TypeError):
                result = slot()
        else:
            result = slot()
        return _to_vnode(result)
    return _to_vnode(slot)


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def Show(props_or_when: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Conditionally render *children* when *when* is truthy.

    Can be called in two styles:

    **Component style** (reactive — recommended for dynamic conditions)::

        Show(when=count, children=lambda: p(f"Count: {count()}"),
             fallback=lambda: p("Empty"))

    **Direct call** (evaluated once — fine inside a render function)::

        Show(when=lambda: count() > 0,
             children=lambda: p("Positive"),
             fallback=lambda: p("Not positive"))

    *when* may be a zero-arg getter or a plain value.
    *children* / *fallback* may be a ``VNode``, a callable, or a plain value.
    When *children* is callable and *when* is truthy, the truthy value is
    passed as the first argument (matching SolidJS ``<Show>``).

    The component creates a **keyed conditional scope**: when the
    truthiness of *when* changes, the previous branch's scope is
    disposed and a new scope is created.  This ensures that effects
    and cleanups registered inside a branch are properly torn down
    on transitions.
    """
    if isinstance(props_or_when, dict) and not kwargs and children_pos is None:
        return _ShowComponent(props_or_when)

    when = kwargs.pop("when", props_or_when)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"when": when, "children": children, "fallback": fallback}
    return h(_ShowComponent, props)


def _ShowComponent(props: Dict[str, Any]) -> Any:
    """Internal component backing ``Show``."""
    import wybthon.reactivity as _rx

    props_getter = _rx.get_props()
    comp_ctx = _rx._get_component_ctx()

    _branch: List[Optional[str]] = [None]
    _branch_owner: List[Optional[_rx.Owner]] = [None]

    def render() -> VNode:
        p = props_getter()
        condition = _eval(p.get("when"))
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
            children = p.get("children")
            if children is None:
                return to_text_vnode("")
            return _render_slot(children, condition)

        fb = p.get("fallback")
        if fb is None:
            return to_text_vnode("")
        return _render_slot(fb)

    return render


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def For(props_or_each: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Render a list of items using a keyed mapping function.

    **Component style** (reactive)::

        For(each=items,
            children=lambda item, index: li(item(), key=index()))

    **Direct call**::

        For(each=items,
            children=lambda item, index: li(item(), key=index()))

    *each* is a getter (or list).  *children* is ``(item, index_getter) -> VNode``.

    Inside the callback, ``item`` is a **signal-backed getter** returning
    the current item value, and ``index`` is a signal-backed getter
    returning the current integer index — matching SolidJS ``<For>``.

    ``For`` maintains **stable per-item reactive scopes** keyed by
    reference identity.  The mapping callback runs only once per unique
    item.  When an item leaves the list its scope (including any
    effects or cleanups created inside the callback) is disposed.
    """
    if isinstance(props_or_each, dict) and not kwargs and children_pos is None:
        return _ForComponent(props_or_each)

    each = kwargs.pop("each", props_or_each)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"each": each, "children": children, "fallback": fallback}
    return h(_ForComponent, props)


def _ForComponent(props: Dict[str, Any]) -> Any:
    """Internal component backing ``For`` with per-item reactive scopes."""
    import wybthon.reactivity as _rx

    props_getter = _rx.get_props()
    comp_ctx = _rx._get_component_ctx()

    # (item_ref, owner, item_signal, index_signal)
    _cache: List[Any] = []

    def render() -> VNode:
        p = props_getter()
        items_val = _eval(p.get("each"))
        children_fn = p.get("children")

        if not items_val:
            for entry in _cache:
                entry[1].dispose()
            _cache.clear()
            fb = p.get("fallback")
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

    return render


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def Index(props_or_each: Any = None, children_pos: Any = None, /, **kwargs: Any) -> Any:
    """Render a list by index with a stable item getter.

    Unlike :func:`For`, the *children* callback receives
    ``(item_getter, index)`` so that the DOM node for each index is
    reused even when the underlying data changes.

    *each* is a getter (or list).  *children* is
    ``(item_getter, index: int) -> VNode``.

    ``Index`` maintains **stable per-index reactive scopes**.  Each
    slot has a signal-backed ``item_getter`` that updates when the
    value at that position changes.  Growing the list creates new
    scopes; shrinking disposes excess scopes.

    Example::

        Index(each=items,
              children=lambda item, i: li(item()))
    """
    if isinstance(props_or_each, dict) and not kwargs and children_pos is None:
        return _IndexComponent(props_or_each)

    each = kwargs.pop("each", props_or_each)
    children = kwargs.pop("children", children_pos)
    fallback = kwargs.pop("fallback", None)

    props: Dict[str, Any] = {"each": each, "children": children, "fallback": fallback}
    return h(_IndexComponent, props)


def _IndexComponent(props: Dict[str, Any]) -> Any:
    """Internal component backing ``Index`` with per-index reactive scopes."""
    import wybthon.reactivity as _rx

    props_getter = _rx.get_props()
    comp_ctx = _rx._get_component_ctx()

    # (owner, item_signal)
    _slots: List[Any] = []

    def render() -> VNode:
        p = props_getter()
        items_val = _eval(p.get("each"))
        children_fn = p.get("children")

        if not items_val:
            for slot in _slots:
                slot[0].dispose()
            _slots.clear()
            fb = p.get("fallback")
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

    return render


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


class _MatchResult:
    """Sentinel returned by :func:`Match` to carry its config to :func:`Switch`."""

    __slots__ = ("when", "children")

    def __init__(self, when: Any, children: Any) -> None:
        self.when = when
        self.children = children


def Match(when: Any = None, children: Any = None, **kwargs: Any) -> _MatchResult:
    """Declare a branch inside a :func:`Switch`.

    *when* may be a getter or a plain value.

    Supports both positional and keyword calling styles::

        Match(True, h("p", {}, "yes"))       # positional
        Match(when=lambda: x() > 0, children=lambda: p("positive"))  # keyword

    Must be used inside ``Switch()``.
    """
    w = kwargs.pop("when", when)
    c = kwargs.pop("children", children)
    return _MatchResult(when=w, children=c)


def Switch(*branches: Any, fallback: Any = None, **kwargs: Any) -> Any:
    """Render the first matching :func:`Match` branch, or *fallback*.

    **Component style** (reactive)::

        Switch(
            Match(when=lambda: status() == "loading",
                  children=lambda: p("Loading...")),
            Match(when=lambda: status() == "ready",
                  children=lambda: p("Ready")),
            fallback=lambda: p("Unknown"),
        )

    Each ``Match`` *when* is evaluated lazily inside the ``Switch``
    component's reactive scope.
    """
    match_branches = [b for b in branches if isinstance(b, _MatchResult)]
    non_match = [b for b in branches if not isinstance(b, _MatchResult)]

    if non_match and isinstance(non_match[0], dict) and not match_branches:
        return _SwitchComponent(non_match[0])

    fb = kwargs.pop("fallback", fallback)
    props: Dict[str, Any] = {"branches": match_branches, "fallback": fb}
    return h(_SwitchComponent, props)


def _SwitchComponent(props: Dict[str, Any]) -> Any:
    """Internal component backing ``Switch``."""
    from .reactivity import get_props

    props_getter = get_props()

    def render() -> VNode:
        p = props_getter()
        branches: List[_MatchResult] = p.get("branches", [])
        for branch in branches:
            condition = _eval(branch.when)
            if condition:
                return _render_slot(branch.children)

        fb = p.get("fallback")
        if fb is None:
            return to_text_vnode("")
        return _render_slot(fb)

    return render


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


def Dynamic(
    component: Any = None,
    props: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Render a dynamically-chosen component.

    *component* may be a string tag name, a component function, or ``None``
    (renders nothing).  Can also be a getter for reactive switching.

    Example::

        Dynamic(component=lambda: heading_level(),
                children=[f"Section {idx}"])
    """
    if isinstance(component, dict) and props is None and not kwargs:
        return _DynamicComponent(component)

    merged: Dict[str, Any] = {"component": component}
    if props:
        merged.update(props)
    merged.update(kwargs)
    return h(_DynamicComponent, merged)


def _DynamicComponent(props: Dict[str, Any]) -> Any:
    """Internal component backing ``Dynamic``."""
    from .reactivity import get_props

    props_getter = get_props()

    def render() -> VNode:
        p = props_getter()
        comp = _eval(p.get("component"))
        if comp is None:
            return to_text_vnode("")
        inner_props: Dict[str, Any] = {k: v for k, v in p.items() if k != "component"}
        children = inner_props.pop("children", [])
        if not isinstance(children, list):
            children = [children]
        return h(comp, inner_props, *children)

    return render

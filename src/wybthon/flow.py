"""Control flow: `Show`, `For`, `Repeat`, `Switch`/`Match`, and `Dynamic`.

These primitives create **isolated reactive scopes** so only the
relevant subtree updates when a condition or list changes. Each is a
function returning a component `VNode`; conditions and sources are
accessors (or plain values), and `children`/`fallback` slots are VNodes
or callables evaluated inside the primitive's own scope.

Callback shapes follow SolidJS 2.0:

- `Show(when, children)`: a callable `children` receives an
  `Accessor` for the truthy value (or the value itself with
  `keyed=True`).
- `For(each, children, keyed=True)`: `children(item, index)` where the
  shapes depend on `keyed` (see [`For`][wybthon.For]).
- `Repeat(count, children)`: `children(index: int)`.
- `Switch(Match(when, children), ..., fallback=...)`.
- `Dynamic(component, **props)`.

Example:
    ```python
    Show(is_logged_in, lambda: p("Welcome!"), fallback=lambda: p("Please log in"))

    For(todos, lambda todo, i: li(todo["title"]))

    Repeat(rating, lambda i: span("*"))
    ```
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._warnings import warn_each_plain_list
from .reactivity import _core
from .reactivity._core import Accessor, _positional_count, is_accessor
from .reactivity._list import map_array
from .reactivity._primitives import create_memo
from .reactivity._props import Props
from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["Show", "For", "Repeat", "Switch", "Match", "Dynamic"]


def _render_slot(slot: Any, *args: Any) -> Any:
    """Evaluate a `children`/`fallback` slot.

    A callable slot is invoked with `args` when it declares positional
    parameters and with none otherwise. Anything else (a VNode, string,
    list, or `None`) is returned as is for the hole to coerce.
    """
    if slot is None or isinstance(slot, VNode):
        return slot
    if isinstance(slot, list) and len(slot) == 1 and callable(slot[0]) and not isinstance(slot[0], VNode):
        slot = slot[0]
    if callable(slot):
        if args and _positional_count(slot) != 0:
            return slot(*args)
        return slot()
    return slot


def _callback(value: Any) -> Any:
    """Unwrap the single-callable `children` list `h()` produces."""
    if isinstance(value, list) and len(value) == 1 and callable(value[0]):
        return value[0]
    return value


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def Show(
    when: Any,
    children: Any = None,
    fallback: Any = None,
    *,
    keyed: bool = False,
) -> VNode:
    """Render `children` while `when` is truthy, else `fallback`.

    Only the **truthiness** of `when` is tracked by default: the branch
    re-renders when the condition flips, not on every value change. A
    callable `children` may accept one argument, an
    [`Accessor`][wybthon.Accessor] for the (truthy) value, so inner
    holes can read it reactively.

    With `keyed=True`, `children` re-renders whenever the value itself
    changes and receives the raw value.

    Args:
        when: Condition accessor or plain value.
        children: VNode, zero-arg callable, or `(value) -> VNode`.
        fallback: Rendered when `when` is falsy.
        keyed: Re-create the branch on every value change.

    Example:
        ```python
        Show(user, lambda u: p("Hello, ", lambda: u().name), fallback=p("Sign in"))
        ```
    """
    return h(_Show, {"when": when, "children": children, "fallback": fallback, "keyed": keyed})


def _Show(props: Props) -> Any:
    when = props.when
    keyed = props.raw("keyed")
    children = _callback(props.raw("children"))
    fallback = props.raw("fallback")

    if keyed:

        def render_keyed() -> Any:
            value = when()
            if value:
                return _render_slot(children, value)
            return _render_slot(fallback)

        return render_keyed

    truthy = create_memo(lambda: bool(when()))

    def render() -> Any:
        if truthy():
            return _render_slot(children, when)
        return _render_slot(fallback)

    return render


_Show.__name__ = "Show"


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------


def For(
    each: Any,
    children: Callable[..., Any],
    fallback: Any = None,
    *,
    keyed: bool | Callable[[Any], Any] = True,
) -> VNode:
    """Render a list with a stable subtree per row.

    The mapping callback runs **once per row**; when the list changes,
    existing rows keep their DOM and are only moved, never re-diffed.
    A row's reactive scope is disposed when it leaves the list.

    `keyed` selects how rows are matched, and with it the callback
    shape:

    - `True` (default): match by identity (scalars by value).
      `children(item, index)` receives the raw item and an
      `Accessor[int]` index.
    - `False`: match by position. `children(item, index)` receives an
      `Accessor` for the item at that position and an `int` index.
    - a callable `key(item)`: match by key, updating the row in place
      when a new object has the same key. `children(item, index)`
      receives accessors for both.

    Args:
        each: List accessor (or a plain list, which renders once).
        children: The row callback.
        fallback: Rendered when the list is empty.
        keyed: Matching strategy.

    Example:
        ```python
        # With a key function both arguments are accessors.
        For(todos, lambda todo, i: li(lambda: todo()["title"]), keyed=lambda t: t["id"])
        ```
    """
    return h(_For, {"each": each, "children": children, "fallback": fallback, "keyed": keyed})


def _wrap_row(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Pin each row's VNode to the row owner so its effects survive list updates."""

    def row(*args: Any) -> Any:
        result = fn(*args)
        node = result if isinstance(result, VNode) else _to_vnode(result)
        node.owner_scope = _core._current_owner
        return node

    return row


def _to_vnode(value: Any) -> VNode:
    if isinstance(value, VNode):
        return value
    if isinstance(value, (list, tuple)):
        return Fragment(*value)
    if is_accessor(value):
        from .vnode import hole

        return hole(value)
    return to_text_vnode(value)


def _For(props: Props) -> Any:
    raw_each = props.raw("each")
    if isinstance(raw_each, (list, tuple)):
        warn_each_plain_list(_For)
    each = props.each
    keyed = props.raw("keyed")
    fallback = props.raw("fallback")
    children = _callback(props.raw("children"))
    if children is None:
        return None

    rows = map_array(lambda: each() or None, _wrap_row(children), keyed=keyed)

    def render() -> Any:
        vnodes = rows()
        if not vnodes:
            return _render_slot(fallback)
        return Fragment(*vnodes)

    return render


_For.__name__ = "For"


# ---------------------------------------------------------------------------
# Repeat
# ---------------------------------------------------------------------------


def Repeat(count: Any, children: Callable[[int], Any], fallback: Any = None, *, start: int | Any = 0) -> VNode:
    """Render `children(i)` for `i` in `range(start, start + count)` with no diffing.

    Rendering is driven purely by the count: growing mounts new tail
    slots, shrinking disposes them, and nothing else is touched. Use it
    for pagination dots, ratings, skeletons, and other count-driven UI.

    Args:
        count: Count accessor or plain integer.
        children: `(index: int) -> VNode`, rendered once per slot.
        fallback: Rendered when the count is zero.
        start: First index (accessor or int).

    Example:
        ```python
        Repeat(rating, lambda i: span("*"))
        ```
    """
    return h(_Repeat, {"count": count, "children": children, "fallback": fallback, "start": start})


def _Repeat(props: Props) -> Any:
    children = _callback(props.raw("children"))
    fallback = props.raw("fallback")
    count = props.count
    start = props.start

    def source() -> list[int] | None:
        try:
            n = int(count() or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            return None
        s = int(start() or 0)
        return list(range(s, s + n))

    def row(item: Accessor[int], index: int) -> Any:
        return children(item.peek())

    slots = map_array(source, _wrap_row(row), keyed=False)

    def render() -> Any:
        vnodes = slots()
        if not vnodes:
            return _render_slot(fallback)
        return Fragment(*vnodes)

    return render


_Repeat.__name__ = "Repeat"


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


class Match:
    """A branch of a [`Switch`][wybthon.Switch].

    Args:
        when: Condition accessor or plain value.
        children: VNode, zero-arg callable, or `(value) -> VNode`
            receiving an `Accessor` (or the raw value with `keyed=True`).
        keyed: Re-create the branch on every value change.
    """

    __slots__ = ("when", "children", "keyed")

    def __init__(self, when: Any, children: Any = None, *, keyed: bool = False) -> None:
        self.when = when
        self.children = children
        self.keyed = keyed


def Switch(*matches: Match, fallback: Any = None) -> VNode:
    """Render the first [`Match`][wybthon.Match] whose condition is truthy.

    Conditions are evaluated in order inside the switch's own scope;
    only a change in *which* branch matches re-renders, so unrelated
    value changes are ignored (unless a branch is `keyed`).

    ```python
    Switch(
        Match(lambda: status() == "loading", lambda: p("Loading...")),
        Match(lambda: status() == "ready", lambda: p("Ready")),
        fallback=lambda: p("Unknown"),
    )
    ```
    """
    return h(_Switch, {"matches": [m for m in matches if isinstance(m, Match)], "fallback": fallback})


def _constant(value: Any) -> Callable[[], Any]:
    return lambda: value


def _Switch(props: Props) -> Any:
    matches: list[Match] = props.raw("matches") or []
    fallback = props.raw("fallback")
    accessors: list[Callable[[], Any]] = []
    for m in matches:
        w = m.when
        if callable(w) and _positional_count(w) == 0:
            accessors.append(w)
        else:
            accessors.append(_constant(w))

    def active() -> int:
        for i, acc in enumerate(accessors):
            if acc():
                return i
        return -1

    index = create_memo(active)

    def render() -> Any:
        i = index()
        if i < 0:
            return _render_slot(fallback)
        m = matches[i]
        acc = accessors[i]
        # A keyed branch reads the value here, so it re-renders on change.
        return _render_slot(_callback(m.children), acc() if m.keyed else acc)

    return render


_Switch.__name__ = "Switch"


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


def Dynamic(component: Any, **props: Any) -> VNode:
    """Render a component or tag chosen at runtime.

    `component` may be a tag name, a component, `None` (renders
    nothing), or an accessor returning any of those; the subtree
    re-mounts when the resolved component changes. Remaining keyword
    props are forwarded.

    Example:
        ```python
        Dynamic(lambda: components[kind()], title="Hello")
        Dynamic("h2", "Heading text")
        ```
    """
    return h(_Dynamic, {"component": component, **props})


def _Dynamic(props: Props) -> Any:
    component = props.component
    forwarded = [k for k in props if k != "component"]

    def render() -> Any:
        comp = component()
        if comp is None:
            return None
        inner: dict[str, Any] = {k: props.raw(k) for k in forwarded}
        children = inner.pop("children", None)
        if children is None:
            return h(comp, inner)
        if not isinstance(children, list):
            children = [children]
        return h(comp, inner, *children)

    return render


_Dynamic.__name__ = "Dynamic"

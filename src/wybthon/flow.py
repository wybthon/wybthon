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
- `Dynamic(component, *children, **props)`, or `dynamic(source)` for a
  reusable component whose implementation is chosen reactively.

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
from .reactivity._core import _positional_count
from .reactivity._primitives import create_memo
from .reactivity._props import Props
from .vnode import VNode, h

__all__ = ["Show", "For", "Repeat", "Switch", "Match", "Dynamic", "DynamicComponent", "dynamic"]


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

    truthy = create_memo(lambda: bool(when()))

    def choose() -> Any:
        if keyed:
            value = when()
            return ((True, value), children, (value,)) if value else ((False,), fallback, ())
        return ((True,), children, (when,)) if truthy() else ((False,), fallback, ())

    return VNode("_branch", {"choose": choose})


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

    return VNode("_list", {"source": each, "children": children, "keyed": keyed, "fallback": fallback})


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

    def source() -> range:
        n = max(0, int(count() or 0))
        s = int(start() or 0)
        return range(s, s + n)

    return VNode("_list", {"source": source, "children": children, "fallback": fallback, "repeat": True})


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

    def choose() -> Any:
        i = index()
        if i < 0:
            return ((-1,), fallback, ())
        match = matches[i]
        acc = accessors[i]
        value = acc() if match.keyed else acc
        token = (i, value) if match.keyed else (i,)
        return token, _callback(match.children), (value,)

    return VNode("_branch", {"choose": choose})


_Switch.__name__ = "Switch"


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


def Dynamic(component: Any, *children: Any, **props: Any) -> VNode:
    """Render a component or tag chosen at runtime.

    `component` may be a tag name, a component, `None` (renders
    nothing), or an accessor returning any of those; the subtree
    re-mounts when the resolved component changes. Remaining children
    and keyword props are forwarded. To choose the component once and
    render it in several places, or to pass it around like a regular
    component, use [`dynamic`][wybthon.dynamic].

    Example:
        ```python
        Dynamic(lambda: components[kind()], title="Hello")
        Dynamic("h2", "Heading text")
        ```
    """
    return h(_Dynamic, {"component": component, **props}, *children)


class DynamicComponent:
    """A component whose implementation is chosen reactively; see [`dynamic`][wybthon.dynamic]."""

    __slots__ = ("_source", "__name__")

    def __init__(self, source: Any) -> None:
        self._source = source
        self.__name__ = "dynamic"

    def __call__(self, *children: Any, **props: Any) -> VNode:
        """Return a `VNode` that renders whatever the source currently selects."""
        return h(_Dynamic, {"component": self._source, **props}, *children)

    def __repr__(self) -> str:
        return "dynamic(...)"


def dynamic(source: Any) -> DynamicComponent:
    """Turn an accessor for a component (or tag) into a component you can call.

    The returned callable behaves like any component: call it with
    children and props to get a `VNode`. Each instance re-mounts when
    `source` resolves to a different component; while `source` is an
    async computation with no value yet, the instance keeps its current
    content and the nearest [`Loading`][wybthon.Loading] shows its
    fallback. Passing `None` renders nothing.

    This is the counterpart of SolidJS 2.0's `dynamic()`; the
    [`Dynamic`][wybthon.Dynamic] control-flow form is the inline
    shorthand.

    Args:
        source: An accessor returning a component, a tag name, or
            `None`; a plain component or tag is accepted too.

    Example:
        ```python
        Editor = dynamic(lambda: RichEditor if rich_mode() else PlainEditor)

        def Page():
            return div(Editor(value=draft, on_change=set_draft))
        ```
    """
    return DynamicComponent(source)


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

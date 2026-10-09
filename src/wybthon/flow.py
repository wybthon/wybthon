"""Control flow: `Show`, `For`, `Repeat`, `Switch`/`Match`, `dynamic`, and `client_only`.

`Show`, `For`, `Repeat`, and `Switch` mount as native *regions*: one
reactive computation that selects what to render, and an owned scope per
branch or row. There's no wrapper component. A condition or source is
an accessor (or a plain value); `children` and `fallback` are nodes or
callables evaluated inside the region's own scope.

When a reactive hole re-renders and returns the same kind of region at
the same place, the new condition or source is pushed into the mounted
region; branches and rows that are still selected survive.

Callback shapes follow SolidJS 2.0:

- `Show(when, children)`: a callable `children` receives an
  `Accessor` for the truthy value (or the value itself with
  `keyed=True`).
- `For(each, children, keyed=True)`: `children(item, index)` where the
  shapes depend on `keyed` (see [`For`][wybthon.For]).
- `Repeat(count, children)`: `children(index: int)`.
- `Switch(Match(when, children), ..., fallback=...)`.
- `dynamic(source)`: a component whose implementation is chosen
  reactively.
- `client_only(children, fallback=...)`: content that only renders in
  the browser, after hydration.

Example:
    ```python
    Show(is_logged_in, html(t"<p>Welcome!</p>"), fallback=html(t"<p>Please log in</p>"))

    For(todos, lambda todo, i: html(t"<li>{todo['title']}</li>"))

    Repeat(rating, lambda i: html(t"<span>*</span>"))
    ```
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal, overload

from ._warnings import warn_each_plain_list
from .component import component
from .reactivity._core import Accessor, Signal, _positional_count, is_accessor
from .reactivity._props import Prop, Props
from .vnode import Fragment, VNode, h

__all__ = [
    "Show",
    "For",
    "Repeat",
    "Switch",
    "Match",
    "dynamic",
    "client_only",
    "NoHydration",
    "Hydration",
    "is_hydrating",
]


def _render_slot(slot: Any, *args: Any) -> Any:
    """Evaluate a `children`/`fallback` slot.

    A callable slot is invoked with `args` when it declares positional
    parameters and with none otherwise. Anything else (a VNode, string,
    list, or `None`) is returned as is for the region to coerce.
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


def _constant(value: Any) -> Callable[[], Any]:
    return lambda: value


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


def _show(inputs: tuple[Any, Any, Any]) -> tuple[Any, Any, tuple[Any, ...]]:
    when, children, fallback = inputs
    if is_accessor(when):
        if when():
            return (True,), children, (when,)
        return (False,), fallback, ()
    if when:
        return (True,), children, (_constant(when),)
    return (False,), fallback, ()


def _show_keyed(inputs: tuple[Any, Any, Any]) -> tuple[Any, Any, tuple[Any, ...]]:
    when, children, fallback = inputs
    value = when() if is_accessor(when) else when
    if value:
        return (True, value), children, (value,)
    return (False,), fallback, ()


@overload
def Show[T](
    when: Callable[[], T | None],
    children: Callable[[Accessor[T]], object],
    fallback: Any = None,
    *,
    keyed: Literal[False] = False,
) -> VNode: ...
@overload
def Show[T](
    when: Callable[[], T | None],
    children: Callable[[T], object],
    fallback: Any = None,
    *,
    keyed: Literal[True],
) -> VNode: ...
@overload
def Show(
    when: object,
    children: Callable[[], object] | VNode | str | list[Any] | None = None,
    fallback: Any = None,
    *,
    keyed: bool = False,
) -> VNode: ...
def Show(when: Any, children: Any = None, fallback: Any = None, *, keyed: bool = False) -> VNode:
    """Render `children` while `when` is truthy, else `fallback`.

    Only the **truthiness** of `when` decides the branch: the branch
    re-renders when the condition flips, not on every value change. A
    callable `children` may accept one argument, an
    [`Accessor`][wybthon.Accessor] for the (truthy) value, so inner
    holes can read it reactively.

    With `keyed=True`, `children` re-renders whenever the value itself
    changes and receives the raw value.

    Args:
        when: Condition accessor or plain value.
        children: A node, a zero-arg callable, or `(value) -> node`.
        fallback: Rendered when `when` is falsy.
        keyed: Re-create the branch on every value change.

    Example:
        ```python
        Show(user, lambda u: html(t"<p>Hello, {u().name}</p>"), fallback=html(t"<p>Sign in</p>"))
        ```
    """
    return VNode(
        "_branch", {"select": _show_keyed if keyed else _show, "inputs": (when, _callback(children), fallback)}
    )


# ---------------------------------------------------------------------------
# For
# ---------------------------------------------------------------------------

type _Each[T] = Callable[[], Sequence[T]] | Sequence[T]


@overload
def For[T](
    each: _Each[T],
    children: Callable[[T, Accessor[int]], object],
    fallback: Any = None,
    *,
    keyed: Literal[True] = True,
) -> VNode: ...
@overload
def For[T](
    each: _Each[T],
    children: Callable[[Accessor[T], int], object],
    fallback: Any = None,
    *,
    keyed: Literal[False],
) -> VNode: ...
@overload
def For[T](
    each: _Each[T],
    children: Callable[[Accessor[T], Accessor[int]], object],
    fallback: Any = None,
    *,
    keyed: Callable[[T], object],
) -> VNode: ...
def For(each: Any, children: Any, fallback: Any = None, *, keyed: Any = True) -> VNode:
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
        For(todos, lambda todo, i: html(t"<li>{(lambda: todo()['title'])}</li>"), keyed=lambda t: t["id"])
        ```
    """
    if isinstance(each, (list, tuple)):
        warn_each_plain_list(For)
    return VNode("_list", {"source": each, "children": _callback(children), "keyed": keyed, "fallback": fallback})


# ---------------------------------------------------------------------------
# Repeat
# ---------------------------------------------------------------------------


def Repeat(
    count: int | Callable[[], int],
    children: Callable[[int], object],
    fallback: Any = None,
    *,
    start: int | Callable[[], int] = 0,
) -> VNode:
    """Render `children(i)` for `i` in `range(start, start + count)` with no diffing.

    Rendering is driven purely by the count: growing mounts new tail
    slots, shrinking disposes them, and nothing else is touched. Use it
    for pagination dots, ratings, skeletons, and other count-driven UI.

    Args:
        count: Count accessor or plain integer.
        children: `(index: int) -> node`, rendered once per slot.
        fallback: Rendered when the count is zero.
        start: First index (accessor or int).

    Example:
        ```python
        Repeat(rating, lambda i: html(t"<span>*</span>"))
        ```
    """
    return VNode(
        "_list",
        {"source": (count, start), "children": _callback(children), "fallback": fallback, "repeat": True},
    )


# ---------------------------------------------------------------------------
# Switch / Match
# ---------------------------------------------------------------------------


class Match:
    """A branch of a [`Switch`][wybthon.Switch].

    Args:
        when: Condition accessor or plain value.
        children: A node, zero-arg callable, or `(value) -> node`
            receiving an `Accessor` (or the raw value with `keyed=True`).
        keyed: Re-create the branch on every value change.
    """

    __slots__ = ("when", "children", "keyed")

    def __init__(self, when: Any, children: Any = None, *, keyed: bool = False) -> None:
        self.when = when
        self.children = _callback(children)
        self.keyed = keyed


def _switch(inputs: tuple[tuple[Match, ...], Any]) -> tuple[Any, Any, tuple[Any, ...]]:
    matches, fallback = inputs
    for index, match in enumerate(matches):
        when = match.when
        reactive = callable(when) and _positional_count(when) == 0
        value = when() if reactive else when
        if value:
            if match.keyed:
                return (index, value), match.children, (value,)
            return (index,), match.children, (when if reactive else _constant(when),)
    return (-1,), fallback, ()


def Switch(*matches: Match, fallback: Any = None) -> VNode:
    """Render the first [`Match`][wybthon.Match] whose condition is truthy.

    Conditions are evaluated in order; only a change in *which* branch
    matches re-renders, so unrelated value changes are ignored (unless a
    branch is `keyed`).

    ```python
    Switch(
        Match(lambda: status() == "loading", html(t"<p>Loading...</p>")),
        Match(lambda: status() == "ready", html(t"<p>Ready</p>")),
        fallback=html(t"<p>Unknown</p>"),
    )
    ```
    """
    return VNode(
        "_branch", {"select": _switch, "inputs": (tuple(m for m in matches if isinstance(m, Match)), fallback)}
    )


# ---------------------------------------------------------------------------
# Dynamic
# ---------------------------------------------------------------------------


class _DynamicProps(Props):
    _wyb_open = True
    component: Prop[Any]


@component
def _Dynamic(props: _DynamicProps) -> Any:
    source = props.component

    def render() -> Any:
        comp = source()
        if comp is None:
            return None
        inner = {k: v for k, v in props._raw.items() if k != "component"}
        children = inner.pop("children", None)
        if children is None:
            return h(comp, inner)
        if not isinstance(children, list):
            children = [children]
        return h(comp, inner, *children)

    return render


_Dynamic.__name__ = "Dynamic"


class _DynamicComponent:
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


def dynamic(source: Any) -> Callable[..., VNode]:
    """Turn an accessor for a component (or tag) into a component you can call.

    The returned callable behaves like any component: call it with
    children and props to get a `VNode`. Each instance re-mounts when
    `source` resolves to a different component; while `source` is an
    async computation with no value yet, the instance keeps its current
    content and the nearest [`Loading`][wybthon.Loading] shows its
    fallback. Passing `None` renders nothing.

    This is the counterpart of SolidJS 2.0's `dynamic()`. For a one-off
    use, call the result inline: `dynamic(lambda: views[kind()])(title="Hi")`.

    Args:
        source: An accessor returning a component, a tag name, or
            `None`; a plain component or tag is accepted too.

    Example:
        ```python
        Editor = dynamic(lambda: RichEditor if rich_mode() else PlainEditor)

        @component
        def Page():
            return html(t"<div>{Editor(value=draft, on_change=set_draft)}</div>")
        ```
    """
    return _DynamicComponent(source)


# ---------------------------------------------------------------------------
# client_only
# ---------------------------------------------------------------------------


class _ClientOnlyProps(Props):
    children: Any = None
    fallback: Any = None


@component
def _ClientOnly(props: _ClientOnlyProps) -> Any:
    from .reactivity import _core

    children = _callback(props.children)
    fallback = props.fallback
    session = _core._session
    hydrating = session is not None and session.mode == "hydrate"
    ready: Signal[bool] = Signal(not (_core._server_depth or hydrating))
    if hydrating:
        session.after_hydration.append(lambda: ready._set(True, _core._O_REVEAL))

    def select(_: Any) -> tuple[Any, Any, tuple[Any, ...]]:
        return ((True,), children, ()) if ready() else ((False,), fallback, ())

    return VNode("_branch", {"select": select, "inputs": None})


_ClientOnly.__name__ = "client_only"


def client_only(children: Any, *, fallback: Any = None) -> VNode:
    """Render `children` only in the browser, after hydration.

    During a server render, and while the browser hydrates that render,
    `fallback` shows instead; the children replace it as soon as
    hydration has committed. In a page that wasn't server-rendered,
    the children render immediately. Use it for widgets that need
    browser APIs or whose output depends on the browser (a map, a chart
    measured from the viewport, the user's local time).

    Args:
        children: A node or a zero-arg callable returning the content.
        fallback: What the server renders, and what shows until
            hydration finishes.

    Example:
        ```python
        client_only(lambda: Chart(data=data), fallback=html(t"<p>Loading chart...</p>"))
        ```
    """
    return h(_ClientOnly, {"children": children, "fallback": fallback})


# ---------------------------------------------------------------------------
# NoHydration / Hydration
# ---------------------------------------------------------------------------

_NO_HYDRATION_MARKER = "wyb:nh"


def is_hydrating() -> bool:
    """Whether the browser is adopting server-rendered DOM right now.

    True only during the synchronous mount of [`hydrate`][wybthon.hydrate]:
    render what the server rendered, then switch to client-only values
    from `on_settled`. Always false on the server and in pages that
    weren't server-rendered.
    """
    from . import kernel

    return bool(kernel.claiming)


class _NoHydrationProps(Props):
    children: Any = None


@component
def _NoHydration(props: _NoHydrationProps) -> Any:
    from . import kernel

    if kernel.claiming:
        return VNode("_static", {"marker": _NO_HYDRATION_MARKER})
    return VNode("_fragment", {"marker": _NO_HYDRATION_MARKER}, list(props.children or []))


_NoHydration.__name__ = "NoHydration"


def NoHydration(*children: Any) -> VNode:
    """Render `children` on the server as static HTML the browser won't hydrate.

    While the browser hydrates, the region's server-rendered DOM is kept
    as is and nothing inside it is mounted, so it costs no Python work
    and never updates. In a page that wasn't server-rendered, the
    children render normally. Use it for content that never changes
    after the first paint: article bodies, footers, legal text.

    Matches Solid 2.0's `<NoHydration>`.
    """
    return h(_NoHydration, {"children": list(children)})


def Hydration(*children: Any, id: str | None = None) -> VNode:
    """Mark a subtree for hydration; a passthrough in Wybthon.

    Solid 2.0 uses `<Hydration>` to re-enable hydration for an island
    inside `<NoHydration>`. Wybthon keeps a `NoHydration` region static
    as a whole while hydrating, so this renders its children unchanged.
    It's provided so code shared with Solid's model reads the same.

    Args:
        *children: The content.
        id: Accepted for parity; unused.
    """
    return Fragment(*children)

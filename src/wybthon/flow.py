"""SolidJS-style flow control components for declarative rendering.

These components provide expressive, declarative alternatives to Python's
built-in control flow for building VNode trees.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["Show", "For", "Index", "Switch", "Match", "Dynamic"]


def Show(
    when: Any,
    children: Any = None,
    *,
    fallback: Any = None,
) -> VNode:
    """Conditionally render *children* when *when* is truthy.

    *when* may be a value or a zero-arg callable (getter).  If falsy the
    *fallback* is rendered instead (defaults to an empty text node).

    Example::

        Show(is_logged_in(), p("Welcome!"), fallback=p("Please log in"))
    """
    condition = when() if callable(when) else when
    if condition:
        if isinstance(children, VNode):
            return children
        if callable(children):
            result = children(condition)
            return result if isinstance(result, VNode) else to_text_vnode(str(result) if result is not None else "")
        return to_text_vnode(str(children) if children is not None else "")

    if fallback is None:
        return to_text_vnode("")
    if isinstance(fallback, VNode):
        return fallback
    if callable(fallback):
        result = fallback()
        return result if isinstance(result, VNode) else to_text_vnode(str(result) if result is not None else "")
    return to_text_vnode(str(fallback))


def For(
    each: Any,
    children: Callable[[Any, Callable[[], int]], VNode],
) -> VNode:
    """Render a list of items using a keyed mapping function.

    *each* is an iterable (or a zero-arg getter returning one).
    *children* is a callback ``(item, index_getter) -> VNode`` called for
    every item.

    Example::

        For(items(), lambda item, i: li(item, key=i()))
    """
    items: Any = each() if callable(each) else each
    if not items:
        return to_text_vnode("")
    vnodes: List[VNode] = []
    for idx, item in enumerate(items):
        _idx = idx

        def _index_getter(_i: int = _idx) -> int:
            return _i

        node = children(item, _index_getter)
        if not isinstance(node, VNode):
            node = to_text_vnode(str(node) if node is not None else "")
        vnodes.append(node)
    return Fragment(*vnodes)


def Index(
    each: Any,
    children: Callable[[Callable[[], Any], int], VNode],
) -> VNode:
    """Render a list by index with a stable item getter.

    Unlike :func:`For`, the *children* callback receives
    ``(item_getter, index)`` so that the DOM node for each index is
    reused even when the underlying data changes.

    Example::

        Index(items(), lambda item, i: li(item()))
    """
    items: Any = each() if callable(each) else each
    if not items:
        return to_text_vnode("")
    item_list = list(items)
    vnodes: List[VNode] = []
    for idx, item in enumerate(item_list):
        _item = item

        def _item_getter(_it: Any = _item) -> Any:
            return _it

        node = children(_item_getter, idx)
        if not isinstance(node, VNode):
            node = to_text_vnode(str(node) if node is not None else "")
        vnodes.append(node)
    return Fragment(*vnodes)


class _MatchResult:
    """Sentinel returned by :func:`Match` to carry its result to :func:`Switch`."""

    __slots__ = ("matched", "vnode")

    def __init__(self, matched: bool, vnode: Any) -> None:
        self.matched = matched
        self.vnode = vnode


def Match(
    when: Any,
    children: Any = None,
) -> _MatchResult:
    """Declare a branch inside a :func:`Switch`.

    *when* is evaluated as a boolean (may be a getter).  If truthy, *children*
    is the content to render.

    Must be used inside ``Switch()``.
    """
    condition = when() if callable(when) else when
    return _MatchResult(matched=bool(condition), vnode=children)


def Switch(
    *branches: Any,
    fallback: Any = None,
) -> VNode:
    """Render the first matching :func:`Match` branch, or *fallback*.

    Example::

        Switch(
            Match(status() == "loading", p("Loading...")),
            Match(status() == "error", p("Error!")),
            Match(status() == "ready", p("Ready")),
            fallback=p("Unknown"),
        )
    """
    for branch in branches:
        if isinstance(branch, _MatchResult) and branch.matched:
            v = branch.vnode
            if isinstance(v, VNode):
                return v
            if callable(v):
                result = v()
                return result if isinstance(result, VNode) else to_text_vnode(str(result) if result is not None else "")
            return to_text_vnode(str(v) if v is not None else "")

    if fallback is None:
        return to_text_vnode("")
    if isinstance(fallback, VNode):
        return fallback
    if callable(fallback):
        result = fallback()
        return result if isinstance(result, VNode) else to_text_vnode(str(result) if result is not None else "")
    return to_text_vnode(str(fallback))


def Dynamic(
    component: Any,
    props: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> VNode:
    """Render a dynamically-chosen component.

    *component* may be a string tag name, a component function, or ``None``
    (renders nothing).

    Example::

        Dynamic(heading_level(), f"Section {idx}")
    """
    if component is None:
        return to_text_vnode("")
    merged: Dict[str, Any] = dict(props) if props else {}
    merged.update(kwargs)
    children = merged.pop("children", [])
    if not isinstance(children, list):
        children = [children]
    return h(component, merged, *children)

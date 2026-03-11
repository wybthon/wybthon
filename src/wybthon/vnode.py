"""Virtual node data structure and creation utilities.

This module defines the core ``VNode`` tree representation and the functions
used to build it (``h``, ``Fragment``, ``memo``).  It is intentionally free
of browser/DOM dependencies so that VNode trees can be constructed and
inspected in any Python environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Union,
)

if TYPE_CHECKING:
    from .component import Component
    from .dom import Element
    from .reactivity import Computation

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "memo",
]

PropsDict = Dict[str, Any]
ChildType = Union["VNode", str]


@dataclass
class VNode:
    """Virtual node representing an element, text, or component subtree."""

    tag: Optional[Union[str, Callable[..., Any]]]
    props: PropsDict = field(default_factory=dict)
    children: List[ChildType] = field(default_factory=list)
    key: Optional[Union[str, int]] = None
    el: Optional[Element] = None
    component_instance: Optional[Component] = None
    subtree: Optional[VNode] = None
    render_effect: Optional[Computation] = None
    hooks_ctx: Optional[Any] = None


def to_text_vnode(value: Any) -> VNode:
    """Convert an arbitrary value to a text VNode."""
    return VNode(tag="_text", props={"nodeValue": "" if value is None else str(value)}, children=[])


def flatten_children(items: Iterable[Any]) -> List[Any]:
    """Flatten nested child lists into a single list while dropping ``None``s."""
    out: List[Any] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            out.extend(flatten_children(item))
        else:
            out.append(item)
    return out


def normalize_children(children: List[ChildType]) -> List[VNode]:
    """Normalize mixed children into a list of VNodes (converting strings)."""
    out: List[VNode] = []
    for ch in children:
        if isinstance(ch, VNode):
            out.append(ch)
        else:
            out.append(to_text_vnode(ch))
    return out


def h(tag: Optional[Union[str, Callable[..., Any]]], props: Optional[PropsDict] = None, *children: Any) -> VNode:
    """Create a VNode from a tag, props, and children (component-aware)."""
    props = props or {}
    key = props.get("key") if "key" in props else None
    flat_children = flatten_children(children)
    if callable(tag):
        if "children" not in props and flat_children:
            props["children"] = list(flat_children)
        vnode_children: List[ChildType] = []
    else:
        vnode_children = list(flat_children)
    return VNode(tag=tag, props=props, children=vnode_children, key=key)


def Fragment(*args: Any) -> VNode:
    """Group multiple children without adding a visible wrapper to the DOM.

    Uses a ``<span style="display:contents">`` so the wrapper is invisible to
    CSS layout while keeping the VDOM diffing algorithm simple.

    Can be called directly::

        Fragment(child1, child2)

    Or used as a component tag via ``h()``::

        h(Fragment, {}, child1, child2)
    """
    children: list
    if len(args) == 1 and isinstance(args[0], dict) and "children" in args[0]:
        kids = args[0].get("children", [])
        children = kids if isinstance(kids, list) else [kids]
    else:
        children = list(args)
    return h("span", {"style": {"display": "contents"}}, *children)


def memo(
    component: Callable[..., Any],
    are_props_equal: Optional[Callable[[PropsDict, PropsDict], bool]] = None,
) -> Callable[..., Any]:
    """Memoize a function component to skip re-renders when props are unchanged.

    By default uses shallow identity comparison (``is``) on each prop value.
    Pass a custom ``are_props_equal(old_props, new_props) -> bool`` for
    deeper comparison logic.
    """

    def _default_compare(old_props: PropsDict, new_props: PropsDict) -> bool:
        if set(old_props.keys()) != set(new_props.keys()):
            return False
        return all(old_props[k] is new_props[k] for k in old_props)

    compare = are_props_equal if are_props_equal is not None else _default_compare

    def MemoWrapper(props: PropsDict) -> Any:
        return component(props)

    MemoWrapper._wyb_memo = True  # type: ignore[attr-defined]
    MemoWrapper._wyb_memo_compare = compare  # type: ignore[attr-defined]
    MemoWrapper._wyb_wrapped = component  # type: ignore[attr-defined]
    MemoWrapper.__name__ = f"memo({getattr(component, '__name__', 'Component')})"
    MemoWrapper.__qualname__ = MemoWrapper.__name__
    return MemoWrapper

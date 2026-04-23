"""Virtual node data structure and creation utilities.

This module defines the core ``VNode`` tree representation and the
functions used to build it (``h``, ``Fragment``, ``memo``, ``dynamic``).
It is intentionally free of browser/DOM dependencies so that VNode
trees can be constructed and inspected in any Python environment.

A ``_dynamic`` VNode (created via :func:`dynamic` or implicitly when a
zero-argument callable appears in a child position) represents a
**reactive hole**: the reconciler wraps the getter in its own effect
that updates only the corresponding DOM region when the getter's
dependencies change.  This is the building block for SolidJS-style
"setup once, update fine-grained" rendering.
"""

from __future__ import annotations

import inspect
import weakref
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
    from .dom import Element
    from .reactivity import Computation

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "memo",
    "dynamic",
    "is_getter",
]

PropsDict = Dict[str, Any]
ChildType = Union["VNode", str]


class VNode:
    """Virtual node representing an element, text, component, or reactive hole.

    Uses ``__slots__`` for compact memory layout and faster attribute
    access — meaningful when authoring large lists.
    """

    __slots__ = (
        "tag",
        "props",
        "children",
        "key",
        "el",
        "subtree",
        "render_effect",
        "component_ctx",
        "_frag_end",
    )

    def __init__(
        self,
        tag: Optional[Union[str, Callable[..., Any]]],
        props: Optional[PropsDict] = None,
        children: Optional[List[ChildType]] = None,
        key: Optional[Union[str, int]] = None,
    ) -> None:
        self.tag = tag
        self.props = props if props is not None else {}
        self.children = children if children is not None else []
        self.key = key
        self.el: Optional[Element] = None
        self.subtree: Optional[VNode] = None
        self.render_effect: Optional[Computation] = None
        self.component_ctx: Optional[Any] = None
        self._frag_end: Optional[Element] = None

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        tag = self.tag
        if callable(tag):
            tag = getattr(tag, "__name__", repr(tag))
        return f"VNode(tag={tag!r}, props={self.props!r}, children={len(self.children)})"


def to_text_vnode(value: Any) -> VNode:
    """Convert an arbitrary value to a text VNode."""
    return VNode(tag="_text", props={"nodeValue": "" if value is None else str(value)}, children=[])


def dynamic(getter: Callable[[], Any], *, key: Optional[Union[str, int]] = None) -> VNode:
    """Create a reactive-hole VNode that re-evaluates *getter* on dependency changes.

    This is the explicit form of the same machinery that wraps callable
    children automatically.  Use it when you want to be explicit about
    which child is dynamic, or to attach a stable ``key`` for keyed
    reuse inside a fragment::

        div(dynamic(lambda: f"Hello, {name()}!"))

    Inside a reactive hole you may return a ``VNode``, a ``str``, a
    list of either, or ``None``.
    """
    return VNode(tag="_dynamic", props={"getter": getter}, children=[], key=key)


# ---------------------------------------------------------------------------
# is_getter — cached signature inspection for callable children / props
# ---------------------------------------------------------------------------

# Cache callables → bool using weak references.  ``inspect.signature``
# is one of the hottest calls in the rendering path; caching the result
# is essential.  Weak refs avoid the id-reuse hazard plain ``dict[id]``
# has when short-lived test functions go out of scope.
_required_pos_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _signature_has_required_positional(fn: Any) -> bool:
    """Return True when *fn* has at least one required positional parameter.

    Result is cached via weak references so per-call cost is amortised
    while still being safe across test runs that recycle ``id`` values.
    """
    try:
        cached = _required_pos_cache.get(fn)
        if cached is not None:
            return cached
    except TypeError:
        cached = None
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        try:
            _required_pos_cache[fn] = True
        except TypeError:
            pass
        return True
    result = False
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if p.default is inspect.Parameter.empty:
                result = True
                break
    try:
        _required_pos_cache[fn] = result
    except TypeError:
        pass
    return result


def is_getter(value: Any) -> bool:
    """Return True when *value* is a zero-argument callable suitable for a reactive hole.

    Excludes:

    * ``VNode`` instances
    * Classes (``isinstance(v, type)``)
    * Components / providers (marked with ``_wyb_component`` / ``_wyb_provider``)
    * ``Ref`` objects (have a ``current`` attribute)
    * Callables that require positional arguments (e.g. event handlers
      taking an event object)
    """
    if value is None:
        return False
    if not callable(value):
        return False
    if isinstance(value, (VNode, type)):
        return False
    if hasattr(value, "current"):
        return False
    if getattr(value, "_wyb_component", False):
        return False
    if getattr(value, "_wyb_provider", False):
        return False
    if getattr(value, "_wyb_getter", False):
        return True
    self_obj = getattr(value, "__self__", None)
    if self_obj is not None and type(self_obj).__name__ == "Signal":
        return True
    return not _signature_has_required_positional(value)


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
    """Normalize mixed children into a list of VNodes.

    * ``VNode`` -- kept as-is (fragments are flattened into the parent list).
    * Zero-argument callable -- wrapped in a ``_dynamic`` VNode (reactive hole).
    * Anything else -- coerced to a text VNode.

    The reconciler always works with a flat list of VNodes.
    """
    out: List[VNode] = []
    for ch in children:
        if isinstance(ch, VNode):
            if ch.tag == "_fragment":
                out.extend(normalize_children(ch.children))
            else:
                out.append(ch)
        elif callable(ch) and is_getter(ch):
            out.append(dynamic(ch))
        else:
            out.append(to_text_vnode(ch))
    return out


def h(tag: Optional[Union[str, Callable[..., Any]]], props: Optional[PropsDict] = None, *children: Any) -> VNode:
    """Create a VNode from a tag, props, and children (component-aware).

    Callable children (zero-argument getters) are passed through
    unchanged; ``normalize_children`` will wrap them as ``_dynamic``
    VNodes when the parent element mounts.  Components receive their
    children verbatim via the ``children`` prop so they can decide how
    to render them.
    """
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
    """Group multiple children without adding extra DOM elements.

    Fragments use comment-node markers and mount children directly into
    the parent container, avoiding extra DOM elements that would
    pollute selectors like ``:first-child`` or affect layout.

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
    return VNode(tag="_fragment", props={}, children=children)


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

    def MemoWrapper(props: Any) -> Any:
        return component(props)

    MemoWrapper._wyb_memo = True  # type: ignore[attr-defined]
    MemoWrapper._wyb_memo_compare = compare  # type: ignore[attr-defined]
    MemoWrapper._wyb_wrapped = component  # type: ignore[attr-defined]
    MemoWrapper.__name__ = f"memo({getattr(component, '__name__', 'Component')})"
    MemoWrapper.__qualname__ = MemoWrapper.__name__
    return MemoWrapper

"""Virtual node data structure and tree-building helpers.

This module defines the core [`VNode`][wybthon.VNode] type and the
functions used to build it ([`h`][wybthon.h], [`Fragment`][wybthon.Fragment],
[`dynamic`][wybthon.dynamic]). It's intentionally free of browser or DOM
dependencies, so VNode trees can be constructed and inspected anywhere
CPython runs.

A `_dynamic` VNode (created via [`dynamic`][wybthon.dynamic] or implicitly
when a zero-argument callable appears in a child position) represents a
**reactive hole**: the reconciler wraps the getter in its own effect that
updates only the corresponding DOM region when the getter's dependencies
change. This is the building block for SolidJS-style "setup once, update
fine-grained" rendering.

Example:
    Building a small subtree without a browser::

        from wybthon import h, Fragment

        view = h("section", {"class": "card"},
                 h("h1", {}, "Hello"),
                 Fragment(h("p", {}, "Body 1"), h("p", {}, "Body 2")))
"""

from __future__ import annotations

import inspect
import weakref
from types import FunctionType
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
    from .reactivity import Computation

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "dynamic",
    "is_getter",
]

PropsDict = Dict[str, Any]
ChildType = Union["VNode", str]


class VNode:
    """Virtual node representing an element, text, component, or reactive hole.

    Uses `__slots__` for a compact memory layout and faster attribute
    access, which is meaningful when authoring large lists. Internal
    attributes (`el`, `subtree`, `render_effect`, `component_ctx`,
    `_frag_end`) are populated by the reconciler when the VNode is
    mounted.

    Attributes:
        tag: Element tag name (`"div"`), special tag (`"_text"`,
            `"_dynamic"`, `"_fragment"`), or component callable.
        props: Mapping of prop names to values. Event handlers, attributes,
            and reactive accessors all live here.
        children: List of child `VNode` instances (or strings, before
            normalization).
        key: Optional stable identity used for keyed list reconciliation.
        el: Kernel node id of this VNode's DOM node once mounted (for
            fragments, the start marker; for holes, the end marker).
        owner_scope: Optional reactive `Owner` under which this VNode
            should be mounted. Set by `For`/`Index` so effects created
            while mounting a cached row belong to the row's scope rather
            than to the list's re-running effect.
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
        "owner_scope",
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
        self.children: List[Any] = children if children is not None else []
        self.key = key
        self.el: Optional[int] = None
        self.subtree: Optional[VNode] = None
        self.render_effect: Optional[Computation] = None
        self.component_ctx: Optional[Any] = None
        self.owner_scope: Optional[Any] = None
        self._frag_end: Optional[int] = None

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        tag = self.tag
        if callable(tag):
            tag = getattr(tag, "__name__", repr(tag))
        return f"VNode(tag={tag!r}, props={self.props!r}, children={len(self.children)})"


def to_text_vnode(value: Any) -> VNode:
    """Convert an arbitrary value to a text `VNode`.

    Args:
        value: Any value. `None` becomes the empty string; everything else
            is coerced via `str()`.

    Returns:
        A `_text` VNode with the stringified content stored at `nodeValue`.
    """
    return VNode(tag="_text", props={"nodeValue": "" if value is None else str(value)}, children=[])


def dynamic(getter: Callable[[], Any], *, key: Optional[Union[str, int]] = None) -> VNode:
    """Create a reactive-hole VNode that re-evaluates `getter` on dependency changes.

    This is the explicit form of the same machinery that wraps callable
    children automatically. Use it when you want to be explicit about
    which child is dynamic, or to attach a stable `key` for keyed reuse
    inside a fragment.

    The getter may return a `VNode`, a `str`, a list of either, or `None`.

    Args:
        getter: Zero-arg callable evaluated inside its own effect. Any
            signal reads inside the getter become dependencies that
            trigger re-evaluation.
        key: Optional stable identity used by keyed reconciliation.

    Returns:
        A `_dynamic` VNode that the reconciler will mount as a reactive hole.

    Example:
        ```python
        div(dynamic(lambda: f"Hello, {name()}!"))
        ```
    """
    return VNode(tag="_dynamic", props={"getter": getter}, children=[], key=key)


# ---------------------------------------------------------------------------
# is_getter: signature inspection for callable children / props
# ---------------------------------------------------------------------------

# Cache for callables that need the slow ``inspect.signature`` path.
# Weak refs avoid the id-reuse hazard plain ``dict[id]`` has when
# short-lived test functions go out of scope.
_required_pos_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _signature_has_required_positional(fn: Any) -> bool:
    """Return True when `fn` declares at least one required positional parameter.

    Plain functions, lambdas, and bound methods are answered from their
    code object directly; this is one of the hottest calls in the
    rendering path (every callable child or prop goes through it, and
    list rows create fresh lambdas), and ``inspect.signature`` is two
    orders of magnitude slower. Exotic callables fall back to
    ``inspect.signature`` with a weak-ref cache.
    """
    code = getattr(fn, "__code__", None)
    if code is not None:
        defaults = getattr(fn, "__defaults__", None)
        n_defaults = len(defaults) if defaults else 0
        argcount = code.co_argcount
        if getattr(fn, "__self__", None) is not None:
            argcount -= 1  # bound method: self is already applied
        return argcount - n_defaults > 0

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
    """Return True when `value` is a zero-arg callable suitable for a reactive hole.

    The check excludes:

    - `VNode` instances
    - Classes (`isinstance(value, type)`)
    - Components and providers (marked with `_wyb_component` /
      `_wyb_provider`)
    - `Ref` objects (have a `current` attribute)
    - Callables that require positional arguments (e.g., event handlers
      taking an event object)

    Args:
        value: Any value, typically a child or prop value being normalized.

    Returns:
        `True` if the value should be treated as a reactive getter.
    """
    # Fast path: plain functions and lambdas (the common case in child
    # positions and list rows). Answered from the code object directly.
    if type(value) is FunctionType:
        d = value.__dict__
        if d:
            if d.get("_wyb_component") or d.get("_wyb_provider"):
                return False
            if d.get("_wyb_getter"):
                return True
        code = value.__code__
        defaults = value.__defaults__
        return code.co_argcount - (len(defaults) if defaults else 0) <= 0

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
    """Flatten nested child lists into a single list, dropping `None` entries."""
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
    """Normalize a mixed list of children into a flat list of VNodes.

    Per-element handling:

    - `VNode`: kept as-is. Fragments are flattened into the parent list.
    - Zero-arg callable: wrapped in a `_dynamic` VNode (reactive hole).
    - Anything else: coerced to a text VNode.

    Args:
        children: Children as produced by `h(...)` or component bodies.

    Returns:
        A flat list of `VNode` instances ready for the reconciler.
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
    """Create a VNode from a tag, props, and children.

    This is the low-level VNode constructor used everywhere. For
    common HTML tags, prefer the helpers in
    [`wybthon.html`][wybthon.html] (`div`, `span`, `button`, …).

    Callable children (zero-argument getters) are passed through
    unchanged; `normalize_children` wraps them as `_dynamic` VNodes when
    the parent element mounts. Components receive their children verbatim
    via the `children` prop so they can decide how to render them.

    Args:
        tag: An HTML tag name (`"div"`), a special tag (`"_text"`,
            `"_dynamic"`, `"_fragment"`), or a component callable.
        props: Mapping of prop names to values. May be `None`.
        *children: Children to attach. Lists/tuples are flattened.

    Returns:
        A new `VNode`.

    Example:
        ```python
        from wybthon import h

        view = h("button", {"on_click": handle_click}, "Click me")
        ```
    """
    props = props or {}
    key = props.get("key")
    flat_children = flatten_children(children)
    if callable(tag):
        if "children" not in props and flat_children:
            props["children"] = flat_children
        vnode_children: List[ChildType] = []
    else:
        vnode_children = flat_children
    return VNode(tag=tag, props=props, children=vnode_children, key=key)


def Fragment(*args: Any) -> VNode:
    """Group multiple children without adding an extra DOM wrapper element.

    Fragments use empty comment nodes as start/end markers and mount their
    children directly into the parent container. This avoids extra
    elements that would pollute selectors like `:first-child` or affect
    layout.

    Args:
        *args: Either a sequence of children (`Fragment(a, b, c)`) or a
            single dict containing a `children` key (the form used when
            `Fragment` is called as `h(Fragment, {}, a, b, c)`).

    Returns:
        A `_fragment` VNode that the reconciler will mount inline.

    Example:
        ```python
        Fragment(h1("Title"), p("Body text"))
        h(Fragment, {}, h1("Title"), p("Body text"))  # same thing
        ```
    """
    children: list
    if len(args) == 1 and isinstance(args[0], dict) and "children" in args[0]:
        kids = args[0].get("children", [])
        children = kids if isinstance(kids, list) else [kids]
    else:
        children = list(args)
    return VNode(tag="_fragment", props={}, children=children)

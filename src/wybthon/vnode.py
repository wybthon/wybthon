"""Virtual node data structure and tree-building helpers.

This module defines the core [`VNode`][wybthon.VNode] type and the
functions used to build it ([`h`][wybthon.h], [`Fragment`][wybthon.Fragment],
[`dynamic`][wybthon.dynamic]). It's intentionally free of browser or DOM
dependencies, so VNode trees can be constructed and inspected anywhere
CPython runs.

A `_dynamic` VNode (created via [`dynamic`][wybthon.dynamic] or implicitly
when a marked accessor appears in a child position) represents a
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
from typing import Any, Callable, Dict, Generic, Iterable, List, Optional, TypeVar, Union

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "dynamic",
    "expr",
    "is_getter",
]

PropsDict = Dict[str, Any]
ChildType = Union["VNode", str]
T = TypeVar("T")


class Expression(Generic[T]):
    """Explicit reactive expression used in child and DOM-prop positions.

    Python has no JSX compiler that can distinguish a render expression
    from an ordinary callback. ``expr`` provides that distinction without
    changing the callable accessor model used by signals and memos.
    """

    __slots__ = ("_fn",)

    _wyb_getter = True

    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn

    def __call__(self) -> T:
        return self._fn()


class VNode:
    """Unmounted render description for an element, component, or region.

    A VNode contains declaration data only. DOM node IDs, reactive
    subscriptions, component owners, and mounted children live in the
    reconciler's ``MountedNode`` objects. Keeping those concerns separate
    means one VNode may safely be mounted in more than one location.

    Attributes:
        tag: Element tag name (`"div"`), special tag (`"_text"`,
            `"_dynamic"`, `"_fragment"`), or component callable.
        props: Mapping of prop names to values. Event handlers, attributes,
            and reactive accessors all live here.
        children: List of child `VNode` instances (or strings, before
            normalization).
        key: Optional stable identity used for keyed list reconciliation.
    """

    __slots__ = ("tag", "props", "children", "key")

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

    This is the VNode form of the same machinery used for marked accessors
    and ``expr(...)`` values. It can also attach a stable `key` for keyed
    reuse inside a fragment.

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


def expr(fn: Callable[[], T]) -> Expression[T]:
    """Mark ``fn`` as a reactive render expression.

    Signal, memo, resource, and prop accessors are already marked by Wybthon and don't need
    wrapping. Use ``expr`` for composite expressions, especially in prop
    positions where an unmarked zero-argument callable may be application
    data rather than a value to invoke.

    Args:
        fn: Zero-argument callable evaluated inside a render binding.

    Returns:
        A callable ``Expression`` recognized by the renderer.
    """
    return Expression(fn)


def scoped(vnode: VNode, owner: Any, *, key: Any = None) -> VNode:
    """Attach a declaration to an existing reactive owner.

    This internal node replaces the old mutable ``VNode.owner_scope``
    field used by list rows and conditional branches.
    """
    return VNode(tag="_scope", props={"owner": owner}, children=[vnode], key=vnode.key if key is None else key)


_required_pos_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _signature_has_required_positional(fn: Any) -> bool:
    """Return whether a callable declares a required positional parameter."""
    code = getattr(fn, "__code__", None)
    if code is not None:
        defaults = getattr(fn, "__defaults__", None)
        argcount = code.co_argcount - (1 if getattr(fn, "__self__", None) is not None else 0)
        return argcount - (len(defaults) if defaults else 0) > 0
    try:
        return _required_pos_cache[fn]
    except (KeyError, TypeError):
        pass
    try:
        signature = inspect.signature(fn)
        result = any(
            parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and parameter.default is inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )
    except (ValueError, TypeError):
        result = True
    try:
        _required_pos_cache[fn] = result
    except TypeError:
        pass
    return result


def is_getter(value: Any) -> bool:
    """Return True when ``value`` is an explicit reactive accessor.

    Signal, memo, prop, and ``expr`` accessors carry Wybthon's
    ``_wyb_getter`` marker. Ordinary Python callables are application data
    and are never invoked implicitly. This explicit contract removes the
    ambiguity between a render expression and a zero-argument callback.

    Args:
        value: Any value, typically a child or prop value being normalized.

    Returns:
        ``True`` if the renderer should evaluate and track ``value``.
    """
    if getattr(value, "_wyb_getter", False):
        return True
    self_obj = getattr(value, "__self__", None)
    if self_obj is not None and type(self_obj).__name__ == "Signal":
        return True
    return False


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
    - Marked accessor: wrapped in a `_dynamic` VNode (reactive hole).
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

    Marked accessor children are passed through unchanged;
    `normalize_children` wraps them as `_dynamic` VNodes when the parent
    element mounts. Components receive their children verbatim via the
    `children` prop so they can decide how to render them.

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
    props = dict(props or {})
    key = props.get("key")
    flat_children = flatten_children(children)
    if callable(tag):
        if "children" not in props and flat_children:
            props["children"] = flat_children
        if getattr(tag, "_wyb_provider", False):
            return VNode(tag="_provider", props=props, children=[], key=key)
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

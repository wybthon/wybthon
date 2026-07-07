"""Template-based mounting: static HTML serialization plus hole wiring.

This module is the runtime analogue of SolidJS's compiled templates. A
run-once component returns a VNode tree whose *structure* is static; only
reactive holes, event handlers, refs, and reactive prop bindings change
after mount. That means the static skeleton can be serialized to an HTML
string in Python (cheap), parsed by the browser in a **single**
`template.innerHTML` assignment (one crossing of the Pyodide-JS bridge
instead of one `createElement`/`setAttribute`/`appendChild` call per
node), and then walked once to wire up the dynamic parts.

The pipeline:

1. [`build_plan`][wybthon.template.build_plan] walks a VNode tree and
   produces a `MountPlan`: the serialized HTML plus the list of dynamic
   bindings (events, reactive props, refs, DOM-property writes) and
   anchor placeholders (holes, fragments, child components), or `None`
   when the tree isn't eligible for the fast path.
2. The reconciler parses the HTML through a scratch `<template>` element
   and calls [`wire_tree`][wybthon.template.wire_tree] to walk the
   cloned DOM and the VNode tree in tandem, populating `VNode.el` and
   collecting anchor positions.
3. Bindings are applied and dynamic children mounted at their anchors.

Trees fall back to the classic per-node mount when they contain
constructs the HTML parser would mangle (adjacent or empty text nodes,
raw text elements, invalid attribute names) or when they're too small
for the template overhead to pay off.
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Tuple, cast

from .props import is_event_prop, to_kebab
from .vnode import ChildType, VNode, is_getter, normalize_children

__all__ = ["MountPlan", "build_plan", "wire_tree"]

# Binding kinds collected by the serializer.
BIND_EVENT = 0
BIND_REACTIVE = 1
BIND_REF = 2
BIND_PROP = 3

# Anchor kinds: a hole reuses its placeholder comment as its end anchor;
# fragments and components mount before the placeholder, which is then
# removed.
ANCHOR_HOLE = 0
ANCHOR_MOUNT = 1

# Minimum number of serialized nodes before the template path is used;
# below this, per-node creation is at least as fast as an HTML parse.
MIN_TEMPLATE_NODES = 3

_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# Raw-text and escapable-raw-text elements whose children the fragment
# parser treats specially; excluded from the fast path for safety.
_RAW_TEXT_ELEMENTS = frozenset({"script", "style", "textarea", "title", "xmp", "iframe", "noscript"})

# Elements whose content model forbids bare text children (the parser
# would foster-parent the text outside the table).
_NO_TEXT_CONTENT = frozenset({"table", "thead", "tbody", "tfoot", "tr", "colgroup", "select", "optgroup", "html"})

_VALID_ATTR_NAME = re.compile(r"^[a-zA-Z_:][-a-zA-Z0-9_:.]*$")

_ESCAPE_TEXT = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
_ESCAPE_ATTR = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _escape_text(value: str) -> str:
    if "&" in value or "<" in value or ">" in value:
        for ch, rep in _ESCAPE_TEXT.items():
            value = value.replace(ch, rep)
    return value


def _escape_attr(value: str) -> str:
    if "&" in value or "<" in value or ">" in value or '"' in value:
        for ch, rep in _ESCAPE_ATTR.items():
            value = value.replace(ch, rep)
    return value


class _NotEligible(Exception):
    """Raised internally when a subtree can't use the template fast path."""


class MountPlan:
    """Serialized mount plan for a static-skeleton VNode subtree.

    Attributes:
        html: The serialized HTML string for the skeleton.
        bindings: List of `(vnode, kind, name, value)` tuples to apply
            after the DOM exists (`vnode.el` is populated by
            [`wire_tree`][wybthon.template.wire_tree] first).
        node_count: Number of serialized DOM nodes (used for the
            eligibility threshold).
    """

    __slots__ = ("html", "bindings", "node_count")

    def __init__(self, html: str, bindings: List[Tuple[VNode, int, str, Any]], node_count: int) -> None:
        self.html = html
        self.bindings = bindings
        self.node_count = node_count


def build_plan(vnode: VNode) -> Optional[MountPlan]:
    """Serialize `vnode`'s static structure, or return `None` when ineligible.

    Eligible trees have an element root and contain only element/text
    nodes plus dynamic placeholders (holes, fragments, components). The
    VNode tree is normalized in place (children lists become `VNode`
    lists) as a side effect, exactly as the classic mount path does.

    Args:
        vnode: An element VNode (string tag, not `_text`/`_dynamic`/
            `_fragment`).

    Returns:
        A `MountPlan`, or `None` when the tree must use per-node mounting.
    """
    if not isinstance(vnode.tag, str) or vnode.tag.startswith("_"):
        return None
    parts: List[str] = []
    bindings: List[Tuple[VNode, int, str, Any]] = []
    counter = [0]
    try:
        _serialize_element(vnode, parts, bindings, counter)
    except _NotEligible:
        return None
    if counter[0] < MIN_TEMPLATE_NODES:
        return None
    return MountPlan("".join(parts), bindings, counter[0])


def _serialize_element(
    vnode: VNode,
    parts: List[str],
    bindings: List[Tuple[VNode, int, str, Any]],
    counter: List[int],
) -> None:
    tag = cast(str, vnode.tag)
    lower = tag.lower()
    if lower in _RAW_TEXT_ELEMENTS:
        raise _NotEligible
    counter[0] += 1

    parts.append("<")
    parts.append(tag)

    for name, value in vnode.props.items():
        if name == "key":
            continue
        if name == "ref":
            if value is not None:
                bindings.append((vnode, BIND_REF, name, value))
            continue
        if is_event_prop(name):
            bindings.append((vnode, BIND_EVENT, name, value))
            continue
        if is_getter(value):
            bindings.append((vnode, BIND_REACTIVE, name, value))
            continue
        if name in ("value", "checked"):
            # DOM properties, not attributes; applied post-clone so the
            # semantics match the classic mount path exactly.
            bindings.append((vnode, BIND_PROP, name, value))
            continue
        _serialize_attr(name, value, parts)

    is_void = lower in _VOID_ELEMENTS
    if is_void:
        parts.append(">")
        if vnode.children:
            raise _NotEligible
        return

    parts.append(">")

    norm_children = normalize_children(vnode.children)
    vnode.children = cast(List[ChildType], norm_children)

    no_text = lower in _NO_TEXT_CONTENT
    prev_was_text = False
    for child in norm_children:
        ctag = child.tag
        if ctag == "_text":
            if prev_was_text or no_text:
                raise _NotEligible
            text = child.props.get("nodeValue", "")
            if text == "":
                raise _NotEligible
            counter[0] += 1
            parts.append(_escape_text(str(text)))
            prev_was_text = True
            continue
        prev_was_text = False
        if isinstance(ctag, str) and not ctag.startswith("_"):
            _serialize_element(child, parts, bindings, counter)
        else:
            # Hole, fragment, or component: a comment placeholder marks
            # its position; the reconciler mounts it during wiring.
            counter[0] += 1
            parts.append("<!---->")

    parts.append("</")
    parts.append(tag)
    parts.append(">")


def _serialize_attr(name: str, value: Any, parts: List[str]) -> None:
    if not _VALID_ATTR_NAME.match(name):
        raise _NotEligible
    if name in ("class", "className"):
        parts.append(' class="')
        parts.append(_escape_attr(_class_string(value)))
        parts.append('"')
        return
    if name == "style":
        if isinstance(value, dict):
            css = ";".join(f"{to_kebab(k)}:{v}" for k, v in value.items())
            parts.append(' style="')
            parts.append(_escape_attr(css))
            parts.append('"')
        return
    if name == "dataset":
        if isinstance(value, dict):
            for dk, dv in value.items():
                if not _VALID_ATTR_NAME.match(str(dk)):
                    raise _NotEligible
                parts.append(f' data-{dk}="')
                parts.append(_escape_attr(str(dv)))
                parts.append('"')
        return
    parts.append(" ")
    parts.append(name)
    parts.append('="')
    parts.append(_escape_attr(str(value)))
    parts.append('"')


def _class_string(value: Any) -> str:
    """Match `props._apply_class` semantics for serialization."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value if x)
    if isinstance(value, dict):
        return " ".join(str(k) for k, v in value.items() if v)
    return str(value)


def wire_tree(
    vnode: VNode,
    dom_node: Any,
    wrap: Callable[[Any], Any],
    anchors: List[Tuple[int, VNode, Any, Any]],
) -> None:
    """Walk the VNode tree and the parsed DOM tree in tandem.

    Populates `vnode.el` for every element and text node and records
    dynamic-child anchors (comment placeholders) for the reconciler to
    process after the walk.

    Args:
        vnode: The element VNode whose plan produced `dom_node`.
        dom_node: The corresponding real DOM element.
        wrap: Factory wrapping a raw node in an `Element` (kept as a
            parameter so this module stays browser-agnostic).
        anchors: Output list receiving `(kind, child_vnode, parent_el,
            comment_node)` tuples.
    """
    el = wrap(dom_node)
    vnode.el = el
    child_dom = dom_node.firstChild
    for child in vnode.children:
        assert isinstance(child, VNode)
        ctag = child.tag
        if ctag == "_text":
            child.el = wrap(child_dom)
        elif isinstance(ctag, str) and not ctag.startswith("_"):
            wire_tree(child, child_dom, wrap, anchors)
        elif ctag == "_dynamic":
            anchors.append((ANCHOR_HOLE, child, el, child_dom))
        else:
            anchors.append((ANCHOR_MOUNT, child, el, child_dom))
        child_dom = child_dom.nextSibling

"""Template-based mounting: static HTML serialization plus hole wiring.

This module is the runtime analogue of SolidJS's compiled templates. A
run-once component returns a VNode tree whose *structure* is static; only
reactive holes, event handlers, refs, and reactive prop bindings change
after mount. That means the static skeleton can be serialized to an HTML
string in Python (cheap) and registered with the rendering kernel once;
every mount of the same skeleton is a single `CLONE_TPL` op that clones
the pre-parsed tree natively. The kernel then walks the clone in
document order, assigning a dense block of node ids.

Because the Python serializer counts nodes in exactly the same pre-order
the kernel walks, every element, text node, and placeholder comment gets
a *predictable* id with zero extra communication: the mount simply
assigns `first_id + k` to the k-th serialized node.

Static **text content is hoisted out of the HTML**: the serializer emits
a one-space placeholder text node and records the real value as a
`SET_TEXT` binding applied after the clone. Hoisting is what makes
templates shared: a thousand list rows that differ only in their text
(ids, labels) produce the *same* skeleton string, so the browser parses
it once and clones it a thousand times.

The pipeline:

1. [`build_plan`][wybthon.template.build_plan] walks a VNode tree and
   produces a `MountPlan`: the serialized HTML, the pre-order node
   list (for id assignment and text bindings), the dynamic bindings
   (events, reactive props, refs, DOM-property writes), or `None` when
   the tree isn't eligible for the fast path.
2. The reconciler registers the HTML (once per unique skeleton),
   allocates the id block, emits the `CLONE_TPL` op, applies bindings
   by id, and mounts dynamic children (holes, fragments, components)
   at their placeholder comments.

Trees fall back to per-node ops (still batched, still one bridge
crossing) when they contain constructs the HTML parser would mangle:
adjacent or empty text nodes, raw text elements, invalid attribute
names, or element nestings the parser rewrites (implied `<tbody>`,
auto-closed `<p>`, and similar).

Plans are **cached per shape**: a single walk of the VNode tree
collects the per-instance data (id order and bindings) while building
a hashable *shape key* that uniquely determines the serialized HTML.
Serialization, escaping, and eligibility validation run only on the
first mount of each shape; every later mount of a structurally
identical tree (for example, the rows of a list) is a dictionary hit.
"""

from __future__ import annotations

from html import escape
from typing import Any

from .props import (
    _BOOLEAN_ATTRS,
    KIND_EVENT,
    KIND_REF,
    KIND_SKIP,
    attr_name,
    binding_value,
    is_event_prop,
    prop_kind,
)
from .vnode import VNode, normalize_children

__all__ = ["MountPlan", "build_plan"]

# Binding kinds collected by the serializer.
BIND_EVENT = 0
BIND_REACTIVE = 1
BIND_REF = 2
BIND_PROP = 3
BIND_TEXT = 4

# Node kinds in the pre-order ``MountPlan.order`` list.
NODE_STATIC = 0  # element or text: assign the id to ``vnode.el``
NODE_HOLE = 1  # placeholder comment adopted as a reactive hole's end anchor
NODE_MOUNT = 2  # placeholder comment replaced by a component/fragment mount

# Minimum number of serialized nodes before the template path is used;
# below this, per-node ops are at least as fast as an HTML parse.
MIN_TEMPLATE_NODES = 3

# Props applied as DOM properties after the clone rather than serialized.
_PROP_NAMES = frozenset({"value", "checked", "selected_values", "inner_html", "innerHTML"})

_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# Raw-text and escapable-raw-text elements whose children the fragment
# parser treats specially; excluded from the fast path for safety.
_RAW_TEXT_ELEMENTS = frozenset({"script", "style", "textarea", "title", "xmp", "iframe", "noscript"})

# Namespace roots. SVG and MathML subtrees always mount with per-node
# ``createElementNS`` ops: the HTML parser only preserves the case of
# attribute names it knows about, so serializing them isn't safe.
_FOREIGN_ROOTS = frozenset({"svg", "math"})

# Elements whose content model forbids bare text children (the parser
# would foster-parent the text outside the table).
_NO_TEXT_CONTENT = frozenset({"table", "thead", "tbody", "tfoot", "tr", "colgroup", "select", "optgroup", "html"})

# Content models the parser enforces by *rewriting* the tree (inserting
# implied elements or dropping illegal ones). Serialized HTML must parse
# 1:1 into the node list, so trees that violate these fall back.
_ALLOWED_CHILDREN = {
    "table": frozenset({"caption", "colgroup", "thead", "tbody", "tfoot"}),
    "thead": frozenset({"tr"}),
    "tbody": frozenset({"tr"}),
    "tfoot": frozenset({"tr"}),
    "tr": frozenset({"td", "th"}),
    "select": frozenset({"option", "optgroup"}),
    "optgroup": frozenset({"option"}),
    "colgroup": frozenset({"col"}),
}

# Start tags that implicitly close an open ``<p>`` element.
_P_CLOSERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "details",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)

# Elements the parser auto-closes (or drops) when nested directly in an
# element of the same tag.
_NO_SELF_NESTING = frozenset({"a", "button", "form", "li", "dt", "dd", "option"})


class _NotEligible(Exception):
    """Raised internally when a subtree can't use the template fast path."""


# Sentinel markers used in shape keys. Distinct objects (hashed by id)
# so they can never collide with user-supplied prop names or values.
_K_REF = object()  # ref binding
_K_EVENT = object()  # event handler binding
_K_GETTER = object()  # reactive prop binding
_K_PROP = object()  # value/checked DOM-property binding
_K_TEXT = object()  # text child (content hoisted, not part of the key)
_K_HOLE = object()  # dynamic-child placeholder
_K_MOUNT = object()  # component/fragment-child placeholder
_K_OPEN = object()  # end of props / start of children
_K_CLOSE = object()  # end of element

# Shape key -> serialized HTML string, or None when the shape is
# ineligible for the template fast path. Bounded to keep pathological
# trees (unique static attr values per instance) from growing without
# limit; entries past the cap simply aren't cached.
# Low-cardinality semantic attributes remain in the native skeleton so cloning
# copies them for free. Instance ids, dataset values, text, and arbitrary attrs
# are bindings. Both shape and native-template caches have explicit bounds.
_STATIC_TEMPLATE_ATTRS = frozenset({"class", "class_", "role", "type", "aria_hidden", "aria-hidden"})


def _static_attribute(name: str, value: Any) -> bool:
    if name in {"class", "class_"}:
        return isinstance(value, str)
    return name in _STATIC_TEMPLATE_ATTRS and type(value) in (str, int, float, bool, type(None))


_shape_cache: dict[tuple[Any, ...], str | None] = {}
_SHAPE_CACHE_MAX = 2048


class MountPlan:
    """Serialized mount plan for a static-skeleton VNode subtree.

    Attributes:
        html: The serialized HTML string for the skeleton. Static text
            content is hoisted (each text node appears as a single-space
            placeholder), so structurally-identical trees share the same
            string regardless of their text.
        order: Pre-order list of `(kind, vnode, parent_vnode)` entries,
            one per serialized DOM node, in exactly the order the
            kernel assigns ids. `parent_vnode` is the enclosing element
            VNode (needed to mount placeholders), or `None` for the
            root.
        bindings: List of `(vnode, kind, name, value)` tuples to apply
            after ids are assigned.
    """

    __slots__ = ("html", "order", "bindings")

    def __init__(
        self,
        html: str,
        order: list[tuple[int, VNode, VNode | None]],
        bindings: list[tuple[VNode, int, str, Any]],
    ) -> None:
        self.html = html
        self.order = order
        self.bindings = bindings

    @property
    def node_count(self) -> int:
        """Number of serialized DOM nodes (length of the id block)."""
        return len(self.order)


def build_plan(vnode: VNode) -> MountPlan | None:
    """Serialize `vnode`'s static structure, or return `None` when ineligible.

    Eligible trees have an element root and contain only element/text
    nodes plus dynamic placeholders (holes, fragments, components). The
    VNode tree is normalized in place (children lists become `VNode`
    lists) as a side effect, exactly as the per-node mount path does.

    A single walk collects the per-instance order and bindings while
    building the shape key. The HTML string (and the eligibility
    verdict) comes from the shape cache; the full serializer runs only
    on the first mount of each shape.

    Args:
        vnode: An element VNode (string tag, not `_text`/`_hole`/
            `_fragment`).

    Returns:
        A `MountPlan`, or `None` when the tree must use per-node mounting.
    """
    if not isinstance(vnode.tag, str) or vnode.tag.startswith("_"):
        return None

    key_parts: list[Any] = []
    order: list[tuple[int, VNode, VNode | None]] = []
    bindings: list[tuple[VNode, int, str, Any]] = []
    _walk_shape(vnode, None, key_parts, order, bindings)

    if len(order) < MIN_TEMPLATE_NODES:
        return None

    key = tuple(key_parts)
    if key in _shape_cache:
        html = _shape_cache[key]
        if html is None:
            return None
        return MountPlan(html, order, bindings)

    plan = _build_plan_uncached(vnode)
    if len(_shape_cache) < _SHAPE_CACHE_MAX:
        _shape_cache[key] = plan.html if plan is not None else None
    return plan


def _build_plan_uncached(vnode: VNode) -> MountPlan | None:
    """Run the full serializer (validation + HTML) for one tree."""
    parts: list[str] = []
    order: list[tuple[int, VNode, VNode | None]] = []
    bindings: list[tuple[VNode, int, str, Any]] = []
    try:
        _serialize_element(vnode, None, parts, order, bindings)
    except _NotEligible:
        return None
    if len(order) < MIN_TEMPLATE_NODES:
        return None
    return MountPlan("".join(parts), order, bindings)


def _walk_shape(
    vnode: VNode,
    parent: VNode | None,
    key_parts: list[Any],
    order: list[tuple[int, VNode, VNode | None]],
    bindings: list[tuple[VNode, int, str, Any]],
) -> None:
    """Collect order/bindings for one tree while building its shape key.

    Performs no validation and builds no HTML; two trees that produce
    the same key are guaranteed to serialize to the same HTML string
    and to have the same fast-path eligibility, so both come from the
    shape cache.
    """
    tag = vnode.tag
    order.append((NODE_STATIC, vnode, parent))
    key_parts.append(tag)

    for name, value in vnode.props.items():
        kind = prop_kind(name)
        if kind == KIND_SKIP:
            continue
        if kind == KIND_REF:
            if value is not None:
                bindings.append((vnode, BIND_REF, name, value))
                key_parts.append(_K_REF)
            continue
        if kind == KIND_EVENT:
            bindings.append((vnode, BIND_EVENT, name, value))
            key_parts.extend((_K_EVENT, name))
            continue
        getter = binding_value(name, value)
        if getter is not None:
            bindings.append((vnode, BIND_REACTIVE, name, getter))
            key_parts.extend((_K_GETTER, name))
        elif _static_attribute(name, value):
            key_parts.extend((_K_PROP, name, type(value), value))
        else:
            # Instance attributes never identify a native template. This also
            # handles style, dataset, and class mappings without cache bypasses.
            bindings.append((vnode, BIND_PROP, name, value))
            key_parts.extend((_K_PROP, name))

    key_parts.append(_K_OPEN)

    children = vnode.children
    if children:
        norm_children = normalize_children(children)
        vnode.children = norm_children
        for child in norm_children:
            ctag = child.tag
            if ctag == "_text":
                order.append((NODE_STATIC, child, vnode))
                bindings.append((child, BIND_TEXT, "", str(child.props.get("nodeValue", ""))))
                key_parts.append(_K_TEXT)
            elif ctag == "_hole":
                order.append((NODE_HOLE, child, vnode))
                key_parts.append(_K_HOLE)
            elif isinstance(ctag, str) and not ctag.startswith("_"):
                _walk_shape(child, vnode, key_parts, order, bindings)
            else:
                order.append((NODE_MOUNT, child, vnode))
                key_parts.append(_K_MOUNT)

    key_parts.append(_K_CLOSE)


def _serialize_element(
    vnode: VNode,
    parent: VNode | None,
    parts: list[str],
    order: list[tuple[int, VNode, VNode | None]],
    bindings: list[tuple[VNode, int, str, Any]],
) -> None:
    tag = vnode.tag
    assert isinstance(tag, str)
    lower = tag.lower()
    if lower in _RAW_TEXT_ELEMENTS or lower in _FOREIGN_ROOTS:
        raise _NotEligible
    order.append((NODE_STATIC, vnode, parent))

    parts.append("<")
    parts.append(tag)

    for name, value in vnode.props.items():
        if name == "key":
            continue
        if name == "ref":
            if value is not None:
                bindings.append((vnode, BIND_REF, name, value))
            continue
        if name == "children":
            continue
        if is_event_prop(name):
            bindings.append((vnode, BIND_EVENT, name, value))
            continue
        getter = binding_value(name, value)
        if getter is not None:
            bindings.append((vnode, BIND_REACTIVE, name, getter))
            continue
        if name in _PROP_NAMES:
            # DOM properties, not attributes; applied post-clone so the
            # semantics match the per-node mount path exactly.
            bindings.append((vnode, BIND_PROP, name, value))
            continue
        if _static_attribute(name, value):
            if value is not None and value is not False:
                attribute = attr_name(name)
                text = ("" if attribute in _BOOLEAN_ATTRS else "true") if value is True else str(value)
                parts.append(f' {attribute}="{escape(text, quote=True)}"')
        else:
            bindings.append((vnode, BIND_PROP, name, value))

    is_void = lower in _VOID_ELEMENTS
    if is_void:
        parts.append(">")
        if vnode.children:
            raise _NotEligible
        return

    parts.append(">")

    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children

    no_text = lower in _NO_TEXT_CONTENT
    allowed_children = _ALLOWED_CHILDREN.get(lower)
    prev_was_text = False
    for child in norm_children:
        ctag = child.tag
        if ctag == "_text":
            if prev_was_text or no_text:
                raise _NotEligible
            # Hoist the content: serialize a one-space placeholder and set
            # the real text after the clone. Trees that differ only in
            # text then share one template (parse once, clone per mount).
            order.append((NODE_STATIC, child, vnode))
            bindings.append((child, BIND_TEXT, "", str(child.props.get("nodeValue", ""))))
            parts.append(" ")
            prev_was_text = True
            continue
        prev_was_text = False
        if isinstance(ctag, str) and not ctag.startswith("_"):
            clower = ctag.lower()
            if allowed_children is not None and clower not in allowed_children:
                raise _NotEligible
            if lower == "p" and clower in _P_CLOSERS:
                raise _NotEligible
            if clower == lower and lower in _NO_SELF_NESTING:
                raise _NotEligible
            _serialize_element(child, vnode, parts, order, bindings)
        else:
            # Hole, fragment, or component: a comment placeholder marks
            # its position; the reconciler mounts it after id assignment.
            kind = NODE_HOLE if ctag == "_hole" else NODE_MOUNT
            order.append((kind, child, vnode))
            parts.append("<!---->")

    parts.append("</")
    parts.append(tag)
    parts.append(">")

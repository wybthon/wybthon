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

import re
from typing import Any, Dict, List, Optional, Tuple

from .props import is_dom_property, is_event_prop, to_kebab
from .vnode import VNode, is_getter, normalize_children

__all__ = ["MountBlueprint", "MountPlan", "build_plan"]

# Binding kinds collected by the serializer.
BIND_EVENT = 0
BIND_REACTIVE = 1
BIND_REF = 2
BIND_PROP = 3
BIND_TEXT = 4

# Node kinds in the pre-order ``MountPlan.order`` list.
NODE_STATIC = 0  # element or text: assign an ID in the mounted tree
NODE_HOLE = 1  # placeholder comment adopted as a reactive hole's end anchor
NODE_MOUNT = 2  # placeholder comment replaced by a component/fragment mount

# Minimum number of serialized nodes before the template path is used;
# below this, per-node ops are at least as fast as an HTML parse.
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

_VALID_ATTR_NAME = re.compile(r"^[a-zA-Z_:][-a-zA-Z0-9_:.]*$")

_ESCAPE_ATTR = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _escape_attr(value: str) -> str:
    if "&" in value or "<" in value or ">" in value or '"' in value:
        for ch, rep in _ESCAPE_ATTR.items():
            value = value.replace(ch, rep)
    return value


class _NotEligible(Exception):
    """Raised internally when a subtree can't use the template fast path."""


class _NoCache(Exception):
    """Raised internally when a tree contains props the shape key can't hash.

    Non-scalar static prop values (style dicts, class lists, datasets)
    would need per-value serialization to key correctly, so such trees
    skip the shape cache and run the full serializer on every mount.
    """


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

# Shape key -> compiled blueprint, or None when the shape is
# ineligible for the template fast path. Bounded to keep pathological
# trees (unique static attr values per instance) from growing without
# limit; entries past the cap simply aren't cached.
_shape_cache: Dict[Tuple[Any, ...], Optional["MountBlueprint"]] = {}
_SHAPE_CACHE_MAX = 2048


class MountBlueprint:
    """Immutable compiled instructions shared by equivalent VNode shapes.

    Attributes:
        html: The serialized HTML string for the skeleton. Static text
            content is hoisted (each text node appears as a single-space
            placeholder), so structurally-identical trees share the same
            string regardless of their text.
        kinds: Node instruction kinds in DOM preorder.
        parents: Parent instruction indexes, or ``-1`` for the root.
        binding_specs: ``(node_index, kind, name)`` instructions whose
            values come from each ``MountPlan`` instance.
    """

    __slots__ = ("html", "kinds", "parents", "binding_specs")

    def __init__(
        self,
        html: str,
        kinds: List[int],
        parents: List[int],
        binding_specs: List[Tuple[int, int, str]],
    ) -> None:
        self.html = html
        self.kinds = tuple(kinds)
        self.parents = tuple(parents)
        self.binding_specs = tuple(binding_specs)

    @property
    def node_count(self) -> int:
        """Number of serialized DOM nodes (length of the id block)."""
        return len(self.kinds)


class MountPlan:
    """Per-mount VNode occurrences and values for a compiled blueprint."""

    __slots__ = ("blueprint", "nodes", "binding_values")

    def __init__(self, blueprint: MountBlueprint, nodes: List[VNode], binding_values: List[Any]) -> None:
        self.blueprint = blueprint
        self.nodes = nodes
        self.binding_values = binding_values

    @property
    def html(self) -> str:
        """The shared serialized HTML skeleton."""
        return self.blueprint.html

    @property
    def node_count(self) -> int:
        """Number of serialized DOM nodes."""
        return self.blueprint.node_count

    @property
    def order(self) -> List[Tuple[int, VNode, int]]:
        """Compatibility view of occurrence-indexed node instructions."""
        return list(zip(self.blueprint.kinds, self.nodes, self.blueprint.parents))

    @property
    def bindings(self) -> List[Tuple[int, int, str, Any]]:
        """Occurrence-indexed binding instructions and instance values."""
        return [
            (node_index, kind, name, value)
            for (node_index, kind, name), value in zip(self.blueprint.binding_specs, self.binding_values)
        ]


def build_plan(vnode: VNode) -> Optional[MountPlan]:
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
        vnode: An element VNode (string tag, not `_text`/`_dynamic`/
            `_fragment`).

    Returns:
        A `MountPlan`, or `None` when the tree must use per-node mounting.
    """
    if not isinstance(vnode.tag, str) or vnode.tag.startswith("_"):
        return None

    key_parts: List[Any] = []
    nodes: List[VNode] = []
    kinds: List[int] = []
    parents: List[int] = []
    binding_specs: List[Tuple[int, int, str]] = []
    binding_values: List[Any] = []
    try:
        _walk_shape(vnode, -1, key_parts, nodes, kinds, parents, binding_specs, binding_values)
    except _NoCache:
        return _build_plan_uncached(vnode)

    if len(nodes) < MIN_TEMPLATE_NODES:
        return None

    key = tuple(key_parts)
    if key in _shape_cache:
        blueprint = _shape_cache[key]
        if blueprint is None:
            return None
        return MountPlan(blueprint, nodes, binding_values)

    plan = _build_plan_uncached(vnode)
    if len(_shape_cache) < _SHAPE_CACHE_MAX:
        _shape_cache[key] = plan.blueprint if plan is not None else None
    return plan


def _build_plan_uncached(vnode: VNode) -> Optional[MountPlan]:
    """Run the full serializer (validation + HTML) for one tree."""
    parts: List[str] = []
    nodes: List[VNode] = []
    kinds: List[int] = []
    parents: List[int] = []
    binding_specs: List[Tuple[int, int, str]] = []
    binding_values: List[Any] = []
    try:
        _serialize_element(vnode, -1, parts, nodes, kinds, parents, binding_specs, binding_values)
    except _NotEligible:
        return None
    if len(nodes) < MIN_TEMPLATE_NODES:
        return None
    blueprint = MountBlueprint("".join(parts), kinds, parents, binding_specs)
    return MountPlan(blueprint, nodes, binding_values)


# Static prop value types the shape key can represent directly. Two
# values that compare equal but serialize differently (5 vs 5.0 vs
# True) are disambiguated by including the type in the key.
_KEYABLE_TYPES = (str, int, float, bool)


def _walk_shape(
    vnode: VNode,
    parent_index: int,
    key_parts: List[Any],
    nodes: List[VNode],
    kinds: List[int],
    parents: List[int],
    binding_specs: List[Tuple[int, int, str]],
    binding_values: List[Any],
) -> None:
    """Collect order/bindings for one tree while building its shape key.

    Performs no validation and builds no HTML; two trees that produce
    the same key are guaranteed to serialize to the same HTML string
    and to have the same fast-path eligibility, so both come from the
    shape cache.
    """
    tag = vnode.tag
    node_index = len(nodes)
    nodes.append(vnode)
    kinds.append(NODE_STATIC)
    parents.append(parent_index)
    key_parts.append(tag)

    for name, value in vnode.props.items():
        if name == "key":
            continue
        if name == "ref":
            if value is not None:
                binding_specs.append((node_index, BIND_REF, name))
                binding_values.append(value)
                key_parts.append(_K_REF)
            continue
        if is_event_prop(name):
            binding_specs.append((node_index, BIND_EVENT, name))
            binding_values.append(value)
            key_parts.append(_K_EVENT)
            key_parts.append(name)
            continue
        if is_getter(value):
            binding_specs.append((node_index, BIND_REACTIVE, name))
            binding_values.append(value)
            key_parts.append(_K_GETTER)
            key_parts.append(name)
            continue
        if is_dom_property(name):
            binding_specs.append((node_index, BIND_PROP, name))
            binding_values.append(value)
            key_parts.append(_K_PROP)
            key_parts.append(name)
            continue
        if value is None or type(value) in _KEYABLE_TYPES:
            key_parts.append(name)
            key_parts.append(type(value))
            key_parts.append(value)
        else:
            raise _NoCache

    key_parts.append(_K_OPEN)

    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    for child in norm_children:
        ctag = child.tag
        if ctag == "_text":
            child_index = len(nodes)
            nodes.append(child)
            kinds.append(NODE_STATIC)
            parents.append(node_index)
            binding_specs.append((child_index, BIND_TEXT, ""))
            binding_values.append(str(child.props.get("nodeValue", "")))
            key_parts.append(_K_TEXT)
        elif isinstance(ctag, str) and not ctag.startswith("_"):
            _walk_shape(
                child,
                node_index,
                key_parts,
                nodes,
                kinds,
                parents,
                binding_specs,
                binding_values,
            )
        elif ctag == "_dynamic":
            nodes.append(child)
            kinds.append(NODE_HOLE)
            parents.append(node_index)
            key_parts.append(_K_HOLE)
        else:
            nodes.append(child)
            kinds.append(NODE_MOUNT)
            parents.append(node_index)
            key_parts.append(_K_MOUNT)

    key_parts.append(_K_CLOSE)


def _serialize_element(
    vnode: VNode,
    parent_index: int,
    parts: List[str],
    nodes: List[VNode],
    kinds: List[int],
    parents: List[int],
    binding_specs: List[Tuple[int, int, str]],
    binding_values: List[Any],
) -> None:
    tag = vnode.tag
    assert isinstance(tag, str)
    lower = tag.lower()
    if lower in _RAW_TEXT_ELEMENTS:
        raise _NotEligible
    node_index = len(nodes)
    nodes.append(vnode)
    kinds.append(NODE_STATIC)
    parents.append(parent_index)

    parts.append("<")
    parts.append(tag)

    for name, value in vnode.props.items():
        if name == "key":
            continue
        if name == "ref":
            if value is not None:
                binding_specs.append((node_index, BIND_REF, name))
                binding_values.append(value)
            continue
        if is_event_prop(name):
            binding_specs.append((node_index, BIND_EVENT, name))
            binding_values.append(value)
            continue
        if is_getter(value):
            binding_specs.append((node_index, BIND_REACTIVE, name))
            binding_values.append(value)
            continue
        if is_dom_property(name):
            # DOM properties, not attributes; applied post-clone so the
            # semantics match the per-node mount path exactly.
            binding_specs.append((node_index, BIND_PROP, name))
            binding_values.append(value)
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
            child_index = len(nodes)
            nodes.append(child)
            kinds.append(NODE_STATIC)
            parents.append(node_index)
            binding_specs.append((child_index, BIND_TEXT, ""))
            binding_values.append(str(child.props.get("nodeValue", "")))
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
            _serialize_element(
                child,
                node_index,
                parts,
                nodes,
                kinds,
                parents,
                binding_specs,
                binding_values,
            )
        else:
            # Hole, fragment, or component: a comment placeholder marks
            # its position; the reconciler mounts it after id assignment.
            kind = NODE_HOLE if ctag == "_dynamic" else NODE_MOUNT
            nodes.append(child)
            kinds.append(kind)
            parents.append(node_index)
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
    if value is None:
        return
    parts.append(" ")
    parts.append(name)
    parts.append('="')
    parts.append(_escape_attr(str(value)))
    parts.append('"')


def _class_string(value: Any) -> str:
    """Match `props._class_string` semantics for serialization."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value if x)
    if isinstance(value, dict):
        return " ".join(str(k) for k, v in value.items() if v)
    return str(value)

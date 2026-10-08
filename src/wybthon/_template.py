"""Compiled template mounting: one generated mount function per subtree shape.

This module is the runtime analogue of SolidJS's compiled templates. A
run-once component returns a VNode tree whose *structure* is static; only
text, reactive holes, event handlers, refs, and reactive prop bindings
vary between instances. So the first time a subtree *shape* mounts, this
module:

1. serializes its static skeleton to HTML (validating that the HTML
   parser will reproduce it node for node);
2. records where its text slots, bindings, and dynamic children sit in
   pre-order;
3. generates a Python function that mounts any tree of that shape in
   straight-line code.

Every later mount of the shape calls that function. It guards the
instance's structure, allocates a dense block of node ids, and emits one
fused `CLONE` command that clones the pre-parsed skeleton, fills its text
slots, marks its delegated listeners, and inserts it. It then wires the
instance's bindings by offset and mounts its dynamic children (holes,
components, lists) at their placeholders. Python and the kernel count
nodes in the same pre-order, so every node's id is known without reading
anything back.

Static text is hoisted out of the HTML, so trees that differ only in text
(list rows) share one skeleton: the browser parses it once and clones it
per mount. A hole whose neighbors aren't text uses a text-node placeholder,
so a text result is a plain `nodeValue` write.

Trees mounted this way keep their VNodes, but assign node ids to static
descendants only when the reconciler first needs them, which happens when
a reactive hole patches the subtree ([`materialize`][wybthon._template.materialize]).
List rows and component output are never patched, so they skip that work.
Teardown uses the shape's binding offsets instead of visiting every node
([`dispose`][wybthon._template.dispose]).

Trees the HTML parser would rewrite (adjacent text, raw-text elements,
implied `<tbody>`, auto-closed `<p>`, and similar) aren't eligible; the
reconciler mounts them with per-node commands, still batched in the same
commit. Shapes and generated functions are cached, and both caches are
bounded. Generated source contains only framework names and integer
offsets; tags, prop names, and static values live in a constants table.
"""

from __future__ import annotations

from collections import OrderedDict
from html import escape
from types import MappingProxyType
from typing import Any, Callable

from . import diagnostics, kernel
from ._dom_props import (
    _BOOLEAN_ATTRS,
    _FRESH,
    KIND_EVENT,
    KIND_REF,
    KIND_SKIP,
    _apply_single_prop,
    _bind_reactive_prop,
    _bindings,
    attach_ref,
    attr_name,
    binding_value,
    detach_ref,
    prop_kind,
)
from .events import NON_BUBBLING, EventHandler, _event_key, _handlers, bind_delegated, set_handler
from .reactivity._core import is_accessor
from .vnode import VNode, hole, normalize_children

__all__ = ["Shape", "mount", "materialize", "dispose"]

# Node kinds in a shape's pre-order.
_STATIC = 0  # element or static text
_HOLE = 1  # reactive hole: its placeholder becomes the hole's end anchor
_MOUNT = 2  # component, fragment, or list: mounted before its placeholder, which is then disposed

# Minimum number of serialized nodes before the template path is used;
# a single element is as cheap to create directly.
MIN_TEMPLATE_NODES = 2

# Props applied as DOM properties after the clone rather than serialized.
_PROP_NAMES = frozenset({"value", "checked", "selected_values", "inner_html", "innerHTML"})

_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# Raw-text and escapable-raw-text elements whose children the fragment
# parser treats specially; excluded from the fast path for safety.
_RAW_TEXT_ELEMENTS = frozenset({"script", "style", "textarea", "title", "xmp", "iframe", "noscript", "template"})

# Namespace roots. SVG and MathML subtrees always mount with per-node
# ``createElementNS`` commands: the HTML parser only preserves the case of
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
        "search",
        "section",
        "table",
        "ul",
    }
)

# Elements the parser auto-closes (or drops) when nested directly in an
# element of the same tag.
_NO_SELF_NESTING = frozenset({"a", "button", "form", "li", "dt", "dd", "option"})

# Low-cardinality semantic attributes stay in the native skeleton so cloning
# copies them for free. Instance ids, dataset values, text, and arbitrary
# attributes are bindings applied after the clone.
_STATIC_TEMPLATE_ATTRS = frozenset({"class", "class_", "role", "type", "aria_hidden", "aria-hidden"})


def _static_attribute(name: str, value: Any) -> bool:
    if name == "class" or name == "class_":
        return isinstance(value, str)
    return name in _STATIC_TEMPLATE_ATTRS and type(value) in (str, int, float, bool, type(None))


# Sentinel markers used in shape keys. Distinct objects (hashed by id)
# so they can never collide with user-supplied prop names or values.
_K_REF = object()  # ref binding
_K_EVENT = object()  # delegated event handler
_K_DIRECT = object()  # event handler with native listener options
_K_GETTER = object()  # reactive prop binding
_K_PROP = object()  # static prop applied after the clone (or serialized, with its value)
_K_SKIP = object()  # key / children prop: present, never written
_K_TEXT = object()  # text child (content hoisted, not part of the key)
_K_HOLE = object()  # reactive hole
_K_MOUNT = object()  # component / fragment / list child
_K_OPEN = object()  # end of props / start of children
_K_CLOSE = object()  # end of element


class _NotEligible(Exception):
    """Raised internally when a subtree can't use the template fast path."""


class Shape:
    """A compiled subtree shape: skeleton HTML, slot offsets, and a mount function.

    Attributes:
        html: The serialized skeleton. Static text is hoisted (each text
            node is a one-space placeholder), so structurally identical
            trees share it regardless of their text.
        count: Number of serialized nodes (the length of the id block).
        texts: Pre-order offsets of the text slots the clone command fills.
        listens: `[offset, event_type]` pairs for delegated handlers; the
            kernel marks them while cloning, so mounting sends no
            per-handler commands.
        tpl: The kernel's template id, or `0` when not registered with
            the current backend.
        mount: The generated mount function, `(root, parent_id,
            anchor_id) -> bool`. It returns `False`, having changed
            nothing, when an instance doesn't match the shape.
        handlers: Offsets of nodes with Python-side event handlers.
        refs: Offsets of nodes with refs.
        bindings: `(offset, prop name)` for each reactive prop binding,
            in the order the mount function records their computations.
        holes: Number of dynamic children recorded on the root.
        order: Pre-order `(kind, path)` entries used by `materialize`.
    """

    __slots__ = ("html", "count", "texts", "listens", "tpl", "mount", "handlers", "refs", "bindings", "dynamic")

    def __init__(self, html: str, count: int, texts: list[int], listens: list[list[Any]]) -> None:
        self.html = html
        self.count = count
        self.texts = texts
        self.listens = listens
        self.tpl = 0
        self.mount: Callable[[VNode, int, int | None], bool] = _never
        self.handlers: tuple[int, ...] = ()
        self.refs: tuple[int, ...] = ()
        self.bindings: tuple[tuple[int, str], ...] = ()
        self.dynamic = 0


def _never(root: VNode, parent: int, anchor: int | None) -> bool:
    return False


# Shape key -> Shape, or None when the shape is ineligible. Bounded to keep
# pathological trees (unique static attribute values per instance) from
# growing without limit; entries past the cap simply aren't cached.
_shapes: OrderedDict[tuple[Any, ...], Shape | None] = OrderedDict()
_SHAPE_CACHE_MAX = 1024

# The most recently mounted shape per root tag: list rows and repeated
# components hit this without computing a key at all.
_recent: dict[str, Shape] = {}


_SEALED_CHILDREN: Any = ()
_SEALED_PROPS: Any = MappingProxyType({})


def mount(vnode: VNode, parent_id: int, anchor_id: int | None, final: bool = False) -> bool:
    """Mount an HTML element subtree from a compiled shape.

    Returns `False` when the tree isn't eligible for the template path;
    the caller then mounts it with per-node commands. A `final` subtree
    (a list row or a component's output) is never patched, so once it's
    mounted its static VNodes are released: only the root, its dynamic
    children, and its bindings stay referenced.
    """
    tag = vnode.tag
    shape = _recent.get(tag)  # type: ignore[arg-type]
    if shape is not None and shape.mount(vnode, parent_id, anchor_id):
        if diagnostics._active is not None:
            diagnostics._active.counts["template_recipe_hits"] += 1
        if final:
            vnode.children = _SEALED_CHILDREN
            vnode.props = _SEALED_PROPS
        return True
    if diagnostics._active is not None:
        diagnostics._active.counts["template_shape_walks"] += 1
    if not isinstance(tag, str) or tag.startswith("_"):
        return False
    parts: list[Any] = []
    count = _shape_key(vnode, parts)
    if count < MIN_TEMPLATE_NODES:
        return False
    key = tuple(parts)
    shape = _shapes.get(key, _MISSING_SHAPE)
    if shape is _MISSING_SHAPE:
        shape = _build_shape(vnode)
        if len(_shapes) >= _SHAPE_CACHE_MAX:
            _shapes.popitem(last=False)
        _shapes[key] = shape
    if shape is None:
        return False
    _recent[tag] = shape
    if len(_recent) > _SHAPE_CACHE_MAX:
        _recent.pop(next(iter(_recent)))
    mounted = shape.mount(vnode, parent_id, anchor_id)
    assert mounted, "a shape's mount function must accept the tree it was compiled from"
    if final:
        vnode.children = _SEALED_CHILDREN
        vnode.props = _SEALED_PROPS
    return True


_MISSING_SHAPE: Any = object()

# Framework names a generated mount function closes over.
_CELL_NAMES = (
    "S",
    "VNode",
    "EventHandler",
    "hole",
    "is_accessor",
    "binding_value",
    "static_attribute",
    "register",
    "alloc",
    "OPS",
    "FRESH",
    "attach_ref",
    "bind_delegated",
    "set_handler",
    "bind_prop",
    "apply_prop",
    "mount_hole",
    "mount_child",
)

# Set to a list to collect generated sources (tests and debugging).
_debug_sources: list[str] | None = None


# ---------------------------------------------------------------------------
# Shape keys
# ---------------------------------------------------------------------------


def _event_kind(name: str, value: Any) -> Any:
    """`_K_EVENT` for a delegated handler, `_K_DIRECT` for one needing a native listener."""
    key = _event_key(name)
    if key.endswith(":capture") or key in NON_BUBBLING or isinstance(value, EventHandler):
        return _K_DIRECT
    return _K_EVENT


def _shape_key(vnode: VNode, parts: list[Any]) -> int:
    """Append `vnode`'s shape key to `parts` and return its serialized node count.

    Normalizes children in place (text becomes `_text` VNodes, reactive
    expressions become holes), exactly as the per-node mount path does.
    Two trees with equal keys serialize to the same skeleton, have the
    same eligibility, and are accepted by the same mount function.
    """
    parts.append(vnode.tag)
    for name, value in vnode.props.items():
        kind = prop_kind(name)
        if kind == KIND_SKIP:
            parts.extend((_K_SKIP, name))
        elif kind == KIND_REF:
            parts.extend((_K_REF, name))
        elif kind == KIND_EVENT:
            parts.extend((_event_kind(name, value), name))
        elif binding_value(name, value) is not None:
            parts.extend((_K_GETTER, name))
        elif _static_attribute(name, value):
            parts.extend((_K_PROP, name, type(value), value))
        else:
            parts.extend((_K_PROP, name))
    parts.append(_K_OPEN)
    count = 1
    children = vnode.children
    if children:
        norm = normalize_children(children)
        vnode.children = norm
        for child in norm:
            ctag = child.tag
            if ctag == "_text":
                parts.append(_K_TEXT)
                count += 1
            elif ctag == "_hole":
                parts.append(_K_HOLE)
                count += 1
            elif isinstance(ctag, str) and not ctag.startswith("_"):
                count += _shape_key(child, parts)
            else:
                parts.append(_K_MOUNT)
                count += 1
    parts.append(_K_CLOSE)
    return count


# ---------------------------------------------------------------------------
# Serialization and compilation
# ---------------------------------------------------------------------------


class _Compiler:
    """Serializes one (normalized) tree and generates its shape's mount function."""

    def __init__(self) -> None:
        self.html: list[str] = []
        self.count = 0
        self.texts: list[int] = []
        self.listens: list[list[Any]] = []
        self.constants: list[Any] = []
        self.guards: list[str] = []
        self.effects: list[str] = []
        self.text_vars: list[str] = []
        self.holes: list[str] = []
        self.mounts: list[str] = []
        self.handlers: list[int] = []
        self.refs: list[int] = []
        self.bindings: list[tuple[int, str]] = []
        self.binding_vars: list[str] = []
        self.hole_effects: list[str] = []
        self.mount_effects: list[str] = []

    def const(self, value: Any) -> str:
        self.constants.append(value)
        return f"K{len(self.constants) - 1}"

    def guard(self, line: str) -> None:
        self.guards.append(line)

    def element(self, vnode: VNode, var: str, parent_offset: int) -> None:
        tag = vnode.tag
        assert isinstance(tag, str)
        lower = tag.lower()
        if lower in _RAW_TEXT_ELEMENTS or lower in _FOREIGN_ROOTS:
            raise _NotEligible
        offset = self.count
        self.count += 1
        nid = f"first + {offset}" if offset else "first"
        html = self.html
        html.append("<" + tag)
        if var != "n0":
            self.guard(f"if type({var}) is not VNode or {var}.tag != {self.const(tag)}: return False")
        props = vnode.props
        p = f"p{offset}"
        self.guard(f"{p} = {var}.props")
        self.guard(f"if len({p}) != {len(props)}: return False")
        for name, value in props.items():
            name_ref = self.const(name)
            v = f"v{offset}_{len(self.constants)}"
            self.guard(f"{v} = {p}[{name_ref}]")
            kind = prop_kind(name)
            if kind == KIND_SKIP:
                continue
            if kind == KIND_REF:
                self.refs.append(offset)
                self.effects.append(f"attach_ref({v}, {nid})")
                continue
            if kind == KIND_EVENT:
                event_kind = _event_kind(name, value)
                key = _event_key(name)
                if event_kind is _K_EVENT:
                    self.guard(f"if type({v}) is EventHandler: return False")
                    self.listens.append([offset, key])
                    self.effects.append(f"bind_delegated({nid}, {self.const(key)}, {name_ref}, {v})")
                else:
                    if isinstance(value, EventHandler):
                        self.guard(f"if type({v}) is not EventHandler: return False")
                    else:
                        self.guard(f"if type({v}) is EventHandler: return False")
                    self.effects.append(f"set_handler({nid}, {name_ref}, {v} if callable({v}) else None)")
                self.handlers.append(offset)
                continue
            getter = binding_value(name, value)
            if getter is not None:
                g = f"g{offset}_{len(self.constants)}"
                self.guard(f"{g} = binding_value({name_ref}, {v})")
                self.guard(f"if {g} is None: return False")
                b = f"b{len(self.binding_vars)}"
                self.binding_vars.append(b)
                self.bindings.append((offset, name))
                self.effects.append(f"{b} = bind_prop({nid}, {name_ref}, {g}, FRESH, False)")
                continue
            if name in _PROP_NAMES or not _static_attribute(name, value):
                self.guard(
                    f"if binding_value({name_ref}, {v}) is not None or static_attribute({name_ref}, {v}): return False"
                )
                self.effects.append(f"apply_prop({nid}, {name_ref}, FRESH, {v})")
                continue
            if type(value) is str:
                # Only a string can equal a string constant.
                self.guard(f"if {v} != {self.const(value)}: return False")
            else:
                self.guard(f"if type({v}) is not {self.const(type(value))} or {v} != {self.const(value)}: return False")
            if value is not None and value is not False:
                attribute = attr_name(name)
                text = ("" if attribute in _BOOLEAN_ATTRS else "true") if value is True else str(value)
                html.append(f' {attribute}="{escape(text, quote=True)}"')
        html.append(">")
        children = vnode.children
        if lower in _VOID_ELEMENTS:
            if children:
                raise _NotEligible
            self.guard(f"if {var}.children: return False")
            return
        c = f"c{offset}"
        self.guard(f"{c} = {var}.children")
        if any(child.tag == "_hole" for child in children):
            # Holes are converted in place, which needs a list.
            self.guard(f"if type({c}) is not list or len({c}) != {len(children)}: return False")
        else:
            self.guard(f"if len({c}) != {len(children)}: return False")
        no_text = lower in _NO_TEXT_CONTENT
        allowed = _ALLOWED_CHILDREN.get(lower)
        # Whether the previously serialized sibling is a text node: adjacent
        # text nodes would merge when the browser parses the skeleton.
        prev_text = False
        for index, child in enumerate(children):
            ctag = child.tag
            x = f"x{self.count}"
            self.guard(f"{x} = {c}[{index}]")
            if ctag == "_text":
                if prev_text or no_text:
                    raise _NotEligible
                t = f"t{len(self.text_vars)}"
                self.text_vars.append(t)
                self.texts.append(self.count)
                self.count += 1
                self.guard(f"tx = type({x})")
                self.guard(f"if tx is str: {t} = {x}")
                self.guard(f"elif tx is VNode and {x}.tag == '_text': {t} = str({x}.props.get('nodeValue', ''))")
                self.guard(f"elif tx is int or tx is float: {t} = str({x})")
                self.guard("else: return False")
                html.append(" ")
                prev_text = True
                continue
            if isinstance(ctag, str) and not ctag.startswith("_"):
                clower = ctag.lower()
                if allowed is not None and clower not in allowed:
                    raise _NotEligible
                if lower == "p" and clower in _P_CLOSERS:
                    raise _NotEligible
                if clower == lower and lower in _NO_SELF_NESTING:
                    raise _NotEligible
                self.element(child, x, offset)
                prev_text = False
                continue
            if no_text and ctag == "_hole":
                # A text result can't live directly in a table section either.
                raise _NotEligible
            child_offset = self.count
            self.count += 1
            cnid = f"first + {child_offset}"
            if ctag == "_hole":
                next_child = children[index + 1] if index + 1 < len(children) else None
                text_anchor = not prev_text and not (next_child is not None and next_child.tag in ("_text", "_hole"))
                self.guard(f"if type({x}) is not VNode:")
                self.guard(f"    if not is_accessor({x}): return False")
                self.guard(f"    {x} = hole({x})")
                self.guard(f"    {c}[{index}] = {x}")
                self.guard(f"elif {x}.tag != '_hole': return False")
                self.holes.append(x)
                if text_anchor:
                    # The hole's first text result fills this slot of the
                    # clone command instead of a separate write.
                    slot = 5 + len(self.text_vars)
                    self.texts.append(child_offset)
                    self.text_vars.append('" "')
                    self.hole_effects.append(f"mount_hole({x}, {nid}, None, {cnid}, None, True, op, {slot})")
                else:
                    self.hole_effects.append(f"mount_hole({x}, {nid}, None, {cnid}, None, False)")
                html.append(" " if text_anchor else "<!---->")
                prev_text = text_anchor
                continue
            # Component, fragment, list, or branch: a comment placeholder marks
            # its position; it mounts before the placeholder, which is then disposed.
            self.guard(f"if type({x}) is not VNode: return False")
            self.guard(f"tg = {x}.tag")
            self.guard("if isinstance(tg, str) and (tg in ('_text', '_hole') or not tg.startswith('_')): return False")
            self.guard(f"if tg == '_fragment' and {x}.owner_scope is None and {x}.key is None: return False")
            self.mounts.append(x)
            self.mount_effects.append(f"mount_child({x}, {nid}, {cnid}, None)")
            self.mount_effects.append(f"OPS(({kernel.OP_DISPOSE}, {cnid}))")
            html.append("<!---->")
            prev_text = False
        html.append(f"</{tag}>")

    def build(self, root: VNode) -> Shape | None:
        try:
            self.element(root, "n0", -1)
        except _NotEligible:
            return None
        if self.count < MIN_TEMPLATE_NODES:
            return None
        from .reconciler import _mount_hole, mount

        shape = Shape("".join(self.html), self.count, self.texts, self.listens)
        # Constants and framework callables become closure cells of a factory,
        # so the generated function reads them as fast locals. Missing props
        # surface as KeyError from the guards and reject the instance.
        cells = [f"K{i}" for i in range(len(self.constants))]
        lines = [f"def factory({', '.join(cells + list(_CELL_NAMES))}):", "    def mount(n0, parent, anchor):"]
        lines.append("        try:")
        for guard in self.guards:
            lines.append("            " + guard)
        lines.append("        except KeyError:")
        lines.append("            return False")
        texts = "".join(f", {t}" for t in self.text_vars)
        lines.append("        tid = S.tpl or register(S)")
        lines.append(f"        first = alloc({self.count})")
        lines.append(f"        op = [{kernel.OP_CLONE}, first, tid, parent, anchor{texts}]")
        lines.append("        OPS(op)")
        lines.append("        n0.el = first")
        lines.append("        n0.tpl = S")
        for effect in self.effects:
            lines.append("        " + effect)
        dynamic = self.holes + self.mounts
        record = ", ".join(dynamic + self.binding_vars)
        if record:
            lines.append(f"        n0.dyn = ({record},)")
        for effect in self.hole_effects:
            lines.append("        " + effect)
        for effect in self.mount_effects:
            lines.append("        " + effect)
        lines.append("        return True")
        lines.append("    return mount")
        framework = {
            "S": shape,
            "VNode": VNode,
            "EventHandler": EventHandler,
            "hole": hole,
            "is_accessor": is_accessor,
            "binding_value": binding_value,
            "static_attribute": _static_attribute,
            "register": kernel.register_template,
            "alloc": kernel.alloc_ids,
            "OPS": kernel.emit,
            "FRESH": _FRESH,
            "attach_ref": _attach_ref,
            "bind_delegated": bind_delegated,
            "set_handler": set_handler,
            "bind_prop": _bind_reactive_prop,
            "apply_prop": _apply_single_prop,
            "mount_hole": _mount_hole,
            "mount_child": mount,
        }
        source = "\n".join(lines)
        if _debug_sources is not None:
            _debug_sources.append(source)
        namespace: dict[str, Any] = {}
        exec(compile(source, f"<wybthon template {root.tag}>", "exec"), namespace)
        mount_fn = namespace["factory"](*self.constants, *(framework[name] for name in _CELL_NAMES))
        shape.mount = mount_fn
        shape.handlers = tuple(self.handlers)
        shape.refs = tuple(self.refs)
        shape.bindings = tuple(self.bindings)
        shape.dynamic = len(dynamic)
        return shape


def _build_shape(vnode: VNode) -> Shape | None:
    """Serialize and compile the shape of a normalized tree, or `None` when ineligible."""
    return _Compiler().build(vnode)


def _attach_ref(ref: Any, node_id: int) -> None:
    if ref is not None:
        attach_ref({"ref": ref}, node_id)


# ---------------------------------------------------------------------------
# Materialization and teardown
# ---------------------------------------------------------------------------


def materialize(root: VNode) -> None:
    """Give every node of a template-mounted subtree its id, so it can be patched.

    Compiled mounts record node ids only on the root and its dynamic
    children. Before the reconciler first patches such a subtree, this
    assigns ids to the static descendants (converting raw text children
    to `_text` VNodes) and registers the reactive bindings by node, so
    the subtree becomes an ordinary mounted tree.
    """
    shape = root.tpl
    if shape is None:
        return
    if root.children is _SEALED_CHILDREN:
        raise RuntimeError("A list row or component output can't be patched")
    first = root.el
    assert first is not None
    counter = [first]

    def walk(vnode: VNode) -> None:
        vnode.el = counter[0]
        counter[0] += 1
        children = vnode.children
        for index, child in enumerate(children):
            if type(child) is not VNode:
                child = children[index] = VNode("_text", {"nodeValue": str(child)})
            tag = child.tag
            if tag == "_text":
                child.el = counter[0]
                counter[0] += 1
            elif isinstance(tag, str) and not tag.startswith("_"):
                walk(child)
            else:
                counter[0] += 1

    walk(root)
    dyn = root.dyn
    if shape.bindings and dyn:
        comps = dyn[shape.dynamic :]
        for (offset, name), comp in zip(shape.bindings, comps, strict=True):
            table = _bindings.get(first + offset)
            if table is None:
                _bindings[first + offset] = {name: comp}
            else:
                table[name] = comp
    root.tpl = None
    root.dyn = None


def dispose(root: VNode, dispose_tree: Callable[[VNode], None], owned: bool = False) -> None:
    """Tear down a template-mounted subtree using its shape's offsets.

    Removes Python-side handlers and refs by offset and recurses into the
    dynamic children. The native nodes are released by the kernel when
    their range is disposed.

    With `owned`, the subtree's owner is about to be disposed (a list row
    leaving), which disposes the subtree's computations and scopes; only
    the per-node tables and hole subtrees need attention here.
    """
    shape = root.tpl
    assert shape is not None
    first = root.el
    assert first is not None
    handlers = _handlers
    for offset in shape.handlers:
        mapping = handlers.pop(first + offset, None)
        if mapping:
            for handler in mapping.values():
                if handler.task_owner is not None:
                    handler.task_owner.dispose()
    for offset in shape.refs:
        detach_ref(first + offset)
    dyn = root.dyn
    if dyn:
        n = shape.dynamic
        if owned:
            for index in range(n):
                item = dyn[index]
                if item.tag == "_hole":
                    if item.subtree is not None:
                        dispose_tree(item.subtree)
                        item.subtree = None
                    item.el = None
                else:
                    dispose_tree(item)
        else:
            for index, item in enumerate(dyn):
                if index < n:
                    dispose_tree(item)
                else:
                    item.dispose()
    root.el = None
    root.tpl = None
    root.dyn = None

"""Virtual node data structure and tree-building helpers.

This module defines [`VNode`][wybthon.VNode] and the functions that
build trees of them: [`h`][wybthon.h], [`Fragment`][wybthon.Fragment],
and [`hole`][wybthon.hole]. It has no browser or DOM dependencies, so
VNode trees can be constructed and inspected anywhere CPython runs.

A **reactive hole** is a `_hole` VNode wrapping a reactive expression
(an [`Accessor`][wybthon.Accessor] or a zero-argument function). The
reconciler runs the expression inside its own render effect and patches
only that region of the DOM when its dependencies change. Holes are
created implicitly whenever a reactive expression appears in a child
position, and explicitly with `hole()` when you want a `key`.

Example:
    Building a small subtree without a browser:

    ```python
    from wybthon import h, Fragment

    view = h("section", {"class": "card"},
             h("h1", {}, "Hello"),
             Fragment(h("p", {}, "Body 1"), h("p", {}, "Body 2")))
    ```
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from string.templatelib import Interpolation, Template
from typing import TYPE_CHECKING, Any

from .reactivity._core import is_accessor

if TYPE_CHECKING:
    from .reactivity import Computation

__all__ = ["VNode", "h", "Fragment", "hole", "copy_vnode", "render_template", "template_getter"]

PropsDict = dict[str, Any]

# XML namespaces for non-HTML elements. ``None`` means HTML.
NS_SVG = "http://www.w3.org/2000/svg"
NS_MATHML = "http://www.w3.org/1998/Math/MathML"


class VNode:
    """Virtual node representing an element, text, component, fragment, or hole.

    Uses `__slots__` for a compact layout. The renderer populates the
    internal attributes (`el`, `subtree`, `render_effect`,
    `component_ctx`, `ns`, `_frag_end`) when the VNode mounts.

    Attributes:
        tag: Element tag name (`"div"`), a special tag (`"_text"`,
            `"_hole"`, `"_fragment"`), or a component.
        props: Mapping of prop names to values: attributes, event
            handlers, refs, and reactive bindings.
        children: Child VNodes (mixed values before normalization).
        key: Optional stable identity for keyed reconciliation.
        el: Kernel node id once mounted (for fragments the start
            marker; for holes the end marker).
        owner_scope: Optional reactive `Owner` to mount under. Set by
            list primitives so a cached row's effects belong to the
            row's scope rather than to the list's re-running effect.
    """

    # The fields every node uses are slots. The rest belong to particular
    # kinds (holes, components, fragments, list rows, template roots): they
    # read through the class defaults below and are stored in the node's
    # dict only when set, so building a tree initializes five fields.
    __slots__ = ("tag", "props", "children", "key", "el", "__dict__")

    subtree: VNode | None = None
    render_effect: Computation | None = None
    component_ctx: Any = None
    owner_scope: Any = None
    # A hole's stable ownership scope: the subtree it mounts belongs here
    # (not to the re-running render effect), so components kept across
    # re-evaluations stay alive and context lookups resolve.
    scope: Any = None
    ns: str | None = None
    _frag_end: int | None = None
    _hole_text: str | None = None
    # Set on the root of a template-mounted subtree: its compiled shape, and
    # its dynamic children plus binding computations (see ``wybthon._template``).
    tpl: Any = None
    dyn: tuple[Any, ...] | None = None
    # ``pk`` (position key: the node's place in the rendered tree) is left
    # unset except during server rendering and hydration; read it with
    # ``getattr(vnode, "pk", None)``. See ``wybthon.reactivity._session``.
    pk: str | None

    def __init__(
        self,
        tag: str | Callable[..., Any] | None,
        props: PropsDict | None = None,
        children: list[Any] | None = None,
        key: str | int | None = None,
    ) -> None:
        self.tag = tag
        self.props: PropsDict = props if props is not None else {}
        self.children: list[Any] = children if children is not None else []
        self.key = key
        self.el: int | None = None

    def __getitem__(self, children: Any) -> VNode:
        """Set this node's children with item syntax and return the node.

        `Card(title="Hi")[h2("Body"), p("More")]` passes the children to a
        component as its `children` prop; on an element,
        `div(class_="card")[h2("Body")]` sets its child nodes.
        """
        kids = flatten_children(children if isinstance(children, tuple) else (children,))
        if callable(self.tag):
            self.props["children"] = kids
        else:
            self.children = kids
        return self

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        tag = self.tag
        if callable(tag):
            tag = getattr(tag, "__name__", repr(tag))
        return f"VNode(tag={tag!r}, props={self.props!r}, children={len(self.children)})"


def to_text_vnode(value: Any) -> VNode:
    """Convert an arbitrary value to a text `VNode` (`None` becomes `""`)."""
    return VNode(tag="_text", props={"nodeValue": "" if value is None else str(value)}, children=[])


def hole(getter: Callable[[], Any], *, key: str | int | None = None) -> VNode:
    """Create a reactive hole explicitly, optionally with a `key`.

    Reactive expressions in child positions become holes automatically;
    reach for `hole()` when you need a stable `key` for keyed
    reconciliation inside a fragment, or to make a hole visually
    explicit.

    The expression may return a `VNode`, a string, a list of either, or
    `None`.

    Args:
        getter: Zero-arg reactive expression evaluated inside its own
            render effect.
        key: Optional stable identity for keyed reconciliation.

    Returns:
        A `_hole` VNode.

    Example:
        ```python
        div(hole(lambda: f"Hello, {name()}!"))
        div(lambda: f"Hello, {name()}!")   # equivalent
        ```
    """
    return VNode(tag="_hole", props={"getter": getter}, children=[], key=key)


def _format(item: Interpolation, call: bool) -> str:
    value = item.value
    if call and is_accessor(value):
        value = value()
    conversion = item.conversion
    if conversion == "r":
        value = repr(value)
    elif conversion == "s":
        value = str(value)
    elif conversion == "a":
        value = ascii(value)
    if value is None:
        return ""
    return format(value, item.format_spec)


def render_template(template: Template, call: bool = True) -> str:
    """Render a t-string to text, calling reactive interpolations when `call` is true."""
    out: list[str] = []
    for item in template:
        if isinstance(item, str):
            out.append(item)
        else:
            out.append(_format(item, call))
    return "".join(out)


def template_getter(template: Template) -> Callable[[], str] | None:
    """Return a reactive expression rendering `template`, or `None` when it's static.

    A t-string is reactive when at least one interpolation is an accessor
    or zero-argument function. The expression calls every reactive
    interpolation, so the whole string updates as one binding.
    """
    for value in template.values:
        if is_accessor(value):
            return lambda: render_template(template)
    return None


def _interpolation_getter(item: Interpolation) -> Callable[[], str]:
    def getter() -> str:
        return _format(item, True)

    return getter


def _template_children(template: Template) -> list[Any]:
    """Expand a t-string child into text and holes.

    Without VNode interpolations it's one text node: static, or a single
    reactive hole. Interpolated VNodes (and lists of them) are kept as
    separate children, with the surrounding text around them.
    """
    if not any(isinstance(value, (VNode, list, tuple)) for value in template.values):
        getter = template_getter(template)
        return [render_template(template, False)] if getter is None else [hole(getter)]
    out: list[Any] = []
    text: list[str] = []
    for item in template:
        if isinstance(item, str):
            text.append(item)
            continue
        value = item.value
        if isinstance(value, (VNode, list, tuple)):
            if text:
                out.append("".join(text))
                text = []
            out.extend(flatten_children([value]))
        elif is_accessor(value):
            if text:
                out.append("".join(text))
                text = []
            out.append(hole(_interpolation_getter(item)))
        else:
            text.append(_format(item, False))
    if text:
        out.append("".join(text))
    return out


def flatten_children(items: Iterable[Any]) -> list[Any]:
    """Flatten nested child lists into a single list, dropping `None` entries."""
    out: list[Any] = []
    for item in items:
        t = type(item)
        if t is VNode or t is str:
            out.append(item)
        elif item is None:
            continue
        elif t is Template:
            out.extend(_template_children(item))
        elif isinstance(item, (list, tuple)):
            out.extend(flatten_children(item))
        else:
            out.append(item)
    return out


def normalize_children(children: list[Any]) -> list[VNode]:
    """Normalize a mixed list of children into a flat list of VNodes.

    - `VNode`: kept as is; fragments are flattened into the parent list.
    - Reactive expression (accessor or zero-arg function): wrapped in a
      `_hole` VNode.
    - `None`, `True`, and `False`: skipped, so `cond and Widget()` renders
      nothing when the condition is false (as in SolidJS).
    - Anything else: coerced to a text VNode.
    """
    out: list[VNode] = []
    for ch in children:
        t = type(ch)
        if t is VNode or isinstance(ch, VNode):
            if ch.tag == "_fragment" and ch.owner_scope is None and ch.key is None:
                out.extend(normalize_children(ch.children))
            else:
                out.append(ch)
        elif t is str:
            out.append(VNode("_text", {"nodeValue": ch}, []))
        elif ch is None or ch is True or ch is False:
            continue
        elif is_accessor(ch):
            out.append(hole(ch))
        elif t is Template:
            out.extend(normalize_children(_template_children(ch)))
        else:
            out.append(to_text_vnode(ch))
    return out


def h(tag: str | Callable[..., Any] | None, props: PropsDict | None = None, *children: Any) -> VNode:
    """Create a VNode from a tag, props, and children.

    The low-level constructor behind the helpers in
    [`wybthon.html`][wybthon.html]. Reactive expressions in child
    positions are wrapped as holes when the parent mounts; components
    receive their children verbatim through the `children` prop.

    Args:
        tag: An HTML tag name, a special tag (`"_text"`, `"_hole"`,
            `"_fragment"`), or a component.
        props: Mapping of prop names to values. May be `None`.
        *children: Children to attach. Lists and tuples are flattened.

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
    if not children:
        flat_children = []
    elif len(children) == 1 and type(children[0]) in (VNode, str):
        flat_children = [children[0]]
    else:
        flat_children = flatten_children(children)
    if tag is Fragment:
        return VNode(tag="_fragment", props={}, children=flat_children, key=key)
    if callable(tag):
        if "children" not in props and flat_children:
            props["children"] = flat_children
        vnode_children: list[Any] = []
    else:
        vnode_children = flat_children
    return VNode(tag=tag, props=props, children=vnode_children, key=key)


def Fragment(*args: Any) -> VNode:
    """Group children without adding a wrapper element.

    Fragments mount their children directly into the parent between two
    empty comment markers, so they never pollute selectors like
    `:first-child` or affect layout.

    Args:
        *args: Children. Lists and tuples are flattened.

    Returns:
        A `_fragment` VNode.

    Example:
        ```python
        Fragment(h1("Title"), p("Body text"))
        ```
    """
    return VNode(tag="_fragment", props={}, children=flatten_children(args))


def copy_vnode(value: Any) -> Any:
    """Return a structural copy of an unmounted VNode tree (other values unchanged).

    Mounting records DOM ids and normalized children on the VNodes it
    mounts, so a tree mounts once. Server rendering copies the root
    view for each render pass.
    """
    if not isinstance(value, VNode):
        return value
    props = dict(value.props)
    nested = props.get("children")
    if isinstance(nested, list):
        props["children"] = [copy_vnode(child) for child in nested]
    return VNode(value.tag, props, [copy_vnode(child) for child in value.children], value.key)

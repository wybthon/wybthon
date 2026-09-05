"""Reconciliation engine: mounting, patching, and unmounting VNode trees.

Translates VNode trees into batched DOM operations. Nothing here touches
the DOM directly: every mutation is emitted as a compact op against an
integer node id (see `wybthon.kernel`), and the whole buffer is applied
in one bridge crossing at commit time (the end of `render`, the DOM
phase of every flush).

Mental model:

- **Components run once.** A component body is invoked a single time
  during mount and its returned tree is mounted directly. Updates flow
  through reactive holes and prop bindings embedded in that tree, never
  by re-running the body.
- **Reactive holes** are `_hole` VNodes whose expression runs inside a
  render effect; when its dependencies change, only that region is
  patched. Holes are created for every reactive expression in a child
  position and explicitly with [`hole`][wybthon.hole].
- **Namespaces are inferred.** An `svg` or `math` element switches its
  subtree to the SVG or MathML namespace (`foreignObject` switches back
  to HTML), so SVG works with the same helpers as HTML.

Public surface: [`render`][wybthon.render], plus the lower-level
`mount`, `unmount`, and `patch` used by control-flow primitives.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

from . import kernel
from ._warnings import component_name, log_error
from .component import Component
from .dom import Element
from .events import remove_handlers_for, set_handler
from .kernel import (
    OP_CLONE_TPL,
    OP_CREATE_COMMENT,
    OP_CREATE_ELEMENT,
    OP_CREATE_ELEMENT_NS,
    OP_CREATE_TEXT,
    OP_HOLE_TEXT,
    OP_INSERT,
    OP_MOVE_RANGE,
    OP_RELEASE,
    OP_REMOVE,
    OP_REMOVE_RANGE,
    OP_ROOT,
    OP_SET_TEXT,
    OP_UNROOT,
)
from .props import (
    _UNSET,
    _apply_single_prop,
    _bind_reactive_prop,
    apply_initial_props,
    apply_props,
    attach_ref,
    detach_ref,
    remove_bindings_for,
)
from .reactivity import _core
from .reactivity._core import (
    _K_RENDER,
    Computation,
    NotReadyError,
    Owner,
    _ComponentContext,
    _enter_component_setup,
    _exit_component_setup,
    flush,
    is_accessor,
)
from .reactivity._props import Props
from .template import (
    BIND_EVENT,
    BIND_PROP,
    BIND_REACTIVE,
    BIND_TEXT,
    NODE_HOLE,
    NODE_STATIC,
    build_plan,
)
from .vnode import NS_MATHML, NS_SVG, Fragment, VNode, hole, normalize_children, to_text_vnode

__all__ = ["render", "Root", "mount", "unmount", "patch"]

_emit = kernel.emit
_alloc_id = kernel.alloc_id


# ---------------------------------------------------------------------------
# Error routing
# ---------------------------------------------------------------------------


def _dispatch_to_error_boundary(exc: BaseException, comp: Computation | None = None) -> bool:
    """Route a mount or render error to the nearest ancestor `Errored` boundary.

    Walks the active ownership chain looking for an `_error_handler`.
    `comp` is the computation that was running when the error surfaced;
    the boundary uses its dependency set to heal when an input changes.
    Returns `True` when one handled the error, `False` when the caller
    should log it.
    """
    owner = _core._current_owner
    while owner is not None:
        handler = owner._error_handler
        if handler is not None:
            try:
                handler(exc, comp)
            except Exception as handler_exc:  # pragma: no cover - defensive
                log_error(f"Error boundary handler raised: {handler_exc}", handler_exc)
            return True
        owner = owner._parent
    return False


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------


class Root:
    """A mounted application root returned by [`render`][wybthon.render].

    Attributes:
        container: The container [`Element`][wybthon.Element].
        vnode: The currently rendered root VNode.
    """

    __slots__ = ("container", "vnode", "_owner", "_disposed", "_release_container")

    def __init__(self, container: Element, vnode: VNode, owner: Owner) -> None:
        self.container = container
        self.vnode = vnode
        self._owner = owner
        self._disposed = False
        self._release_container = False

    @property
    def node_id(self) -> int:
        """Kernel node id of the container."""
        return self.container.node_id

    def dispose(self) -> None:
        """Unmount the tree, dispose every reactive scope, and stop event delegation."""
        if self._disposed:
            return
        self._disposed = True
        container_id = self.container.node_id
        _roots.pop(container_id, None)
        _unmount(self.vnode)
        self._owner.dispose()
        _emit((OP_UNROOT, container_id))
        if self._release_container:
            _emit((OP_RELEASE, [container_id]))
        kernel.commit()


# Live roots keyed by the container's kernel node id.
_roots: dict[int, Root] = {}


def render(vnode: Any, container: Element | str | int) -> Root:
    """Render a tree into a container element.

    Mounts `vnode` under `container`, commits every buffered DOM op in
    one bridge crossing, and registers the container as an event
    delegation root. Rendering into the same container again patches the
    existing tree in place.

    Args:
        vnode: The root VNode (or a component call, string, list, or
            reactive expression; anything a component may return).
        container: An [`Element`][wybthon.Element], a CSS selector for
            an existing DOM node, or a kernel node id.

    Returns:
        A [`Root`][wybthon.Root]; call `.dispose()` to tear the app down.

    Example:
        ```python
        from wybthon import render
        from wybthon.html import h1

        root = render(h1("Hello, world!"), "#app")
        ```
    """
    if isinstance(container, str):
        container_el = Element(container, existing=True)
    elif isinstance(container, int):
        container_el = Element(node_id=container)
    else:
        container_el = container
    container_id = container_el.node_id
    node = _coerce_result(vnode)

    # The mount is a commit window like a flush: pause the cyclic GC so
    # it doesn't repeatedly traverse the heap mid-build (see _core._gc_pause).
    _core._gc_pause()
    try:
        existing = _roots.get(container_id)
        if existing is not None and not existing._disposed:
            _core.run_with_owner(existing._owner, lambda: patch(existing.vnode, node, container_id))
            existing.vnode = node
            flush()
            return existing

        owner = Owner()
        root = Root(container_el, node, owner)
        root._release_container = isinstance(container, str)
        _roots[container_id] = root
        _emit((OP_ROOT, container_id))
        _core.run_with_owner(owner, lambda: mount(node, container_id))
        flush()
        return root
    finally:
        _core._gc_resume()


# ---------------------------------------------------------------------------
# DOM-position helpers (computed from the VNode tree; no DOM reads)
# ---------------------------------------------------------------------------


def _first_dom_id(vnode: VNode) -> int | None:
    """Return the id of the first DOM node belonging to this vnode."""
    while True:
        if vnode.tag == "_hole":
            if vnode.subtree is not None:
                first = _first_dom_id(vnode.subtree)
                if first is not None:
                    return first
            return vnode.el
        if vnode.subtree is not None:
            vnode = vnode.subtree
            continue
        return vnode.el


def _range_bounds(vnode: VNode) -> tuple[int | None, int | None]:
    first = _first_dom_id(vnode)
    while vnode.subtree is not None and vnode.tag != "_hole":
        vnode = vnode.subtree
    last = vnode._frag_end if vnode._frag_end is not None else vnode.el
    return first, last


def _move_range(vnode: VNode, parent_id: int, anchor: int | None) -> None:
    first, last = _range_bounds(vnode)
    if first is not None:
        _emit((OP_MOVE_RANGE, parent_id, first, last, anchor))


def _dom_node_ids(vnode: VNode) -> list[int]:
    """Return the ids of all top-level DOM nodes belonging to this vnode."""
    if vnode.tag == "_hole":
        nodes: list[int] = []
        if vnode.subtree is not None:
            nodes.extend(_dom_node_ids(vnode.subtree))
        if vnode.el is not None:
            nodes.append(vnode.el)
        return nodes
    if vnode.subtree is not None:
        return _dom_node_ids(vnode.subtree)
    if vnode.tag in ("_fragment", "_list", "_branch"):
        if vnode.el is None:
            return []
        frag_nodes: list[int] = [vnode.el]
        for child in vnode.children:
            frag_nodes.extend(_dom_node_ids(child))
        if vnode._frag_end is not None:
            frag_nodes.append(vnode._frag_end)
        return frag_nodes
    if vnode.el is not None:
        return [vnode.el]
    return []


# ---------------------------------------------------------------------------
# Parking (used by Loading to keep pending content mounted off-document)
# ---------------------------------------------------------------------------


def _create_lot() -> int:
    """Create a detached element that can hold parked DOM nodes."""
    lot = _alloc_id()
    _emit((OP_CREATE_ELEMENT, lot, "div"))
    return lot


def _release_lot(lot: int) -> None:
    _emit((OP_RELEASE, [lot]))


def _park(vnode: VNode, lot: int) -> None:
    """Move every DOM node of `vnode` into `lot`, keeping it mounted and reactive.

    Later updates inside the subtree keep working: the kernel inserts
    relative to the anchor's live parent, so nodes addressed to the
    original parent land in the lot while parked.
    """
    for nid in _dom_node_ids(vnode):
        _emit((OP_INSERT, lot, nid, None))


def _unpark(vnode: VNode, anchor_id: int) -> None:
    """Move every DOM node of `vnode` back in front of `anchor_id`."""
    for nid in _dom_node_ids(vnode):
        _emit((OP_INSERT, 0, nid, anchor_id))


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def _child_ns(tag: str, ns: str | None) -> str | None:
    """Namespace for the children of element `tag` mounted in namespace `ns`."""
    if ns is None:
        if tag == "svg":
            return NS_SVG
        if tag == "math":
            return NS_MATHML
        return None
    if ns == NS_SVG and tag == "foreignObject":
        return None
    return ns


def _element_ns(tag: str, ns: str | None) -> str | None:
    """Namespace to create element `tag` in when its parent namespace is `ns`."""
    if ns is None:
        if tag == "svg":
            return NS_SVG
        if tag == "math":
            return NS_MATHML
        return None
    return ns


def mount(vnode: VNode | str, parent_id: int, anchor_id: int | None = None, ns: str | None = None) -> None:
    """Emit ops mounting a VNode (or string) under `parent_id`.

    When the VNode carries an `owner_scope` (set by list primitives for
    cached rows), mounting runs under that owner with tracking suspended,
    so the row's effects survive later list updates.

    Args:
        vnode: The VNode to mount. Strings are coerced to text VNodes.
        parent_id: Kernel id of the parent node.
        anchor_id: Optional sibling id to insert before (`None` appends).
        ns: Namespace of the parent (`None` for HTML).
    """
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)
    scope = vnode.owner_scope
    if scope is not None:
        _core._run_owned_untracked(scope, lambda: _mount_dispatch(vnode, parent_id, anchor_id, ns))
        return
    _mount_dispatch(vnode, parent_id, anchor_id, ns)


def _mount_dispatch(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    tag = vnode.tag
    vnode.ns = ns

    if tag == "_text":
        nid = _alloc_id()
        vnode.el = nid
        _emit((OP_CREATE_TEXT, nid, vnode.props.get("nodeValue", "")))
        _emit((OP_INSERT, parent_id, nid, anchor_id))
        return

    if tag == "_hole":
        _mount_hole(vnode, parent_id, anchor_id)
        return

    if tag in ("_list", "_branch"):
        from ._regions import mount_branch, mount_list

        (mount_list if tag == "_list" else mount_branch)(vnode, parent_id, anchor_id)
        return

    if tag == "_fragment":
        _mount_fragment(vnode, parent_id, anchor_id, ns)
        return

    if callable(tag):
        _mount_component(vnode, parent_id, anchor_id, ns)
        return

    if ns is None and _mount_template(vnode, parent_id, anchor_id):
        return

    _mount_element(vnode, parent_id, anchor_id, ns)


def _mount_element(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    """Mount an element subtree with per-node ops (the template-ineligible path)."""
    tag = vnode.tag
    assert isinstance(tag, str)
    nid = _alloc_id()
    vnode.el = nid
    el_ns = _element_ns(tag, ns)
    if el_ns is None:
        _emit((OP_CREATE_ELEMENT, nid, tag))
    else:
        _emit((OP_CREATE_ELEMENT_NS, nid, el_ns, tag))
    apply_initial_props(nid, vnode.props)
    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    child_ns = _child_ns(tag, ns)
    for child in norm_children:
        mount(child, nid, None, child_ns)
    _emit((OP_INSERT, parent_id, nid, anchor_id))
    attach_ref(vnode.props, nid)


def _mount_template(vnode: VNode, parent_id: int, anchor_id: int | None) -> bool:
    """Mount an element subtree through the template fast path.

    The static skeleton is serialized to HTML once per shape and cloned
    natively with one `CLONE_TPL` op; text, bindings, and dynamic children
    are then wired by id. Returns `False` when the tree isn't eligible.
    """
    if not kernel.supports_html():
        return False
    plan = build_plan(vnode)
    if plan is None:
        return False

    count = plan.node_count
    first = kernel.alloc_ids(count)
    _emit((OP_CLONE_TPL, first, count, kernel.template_id(plan.html)))

    holes: list[Any] = []
    mounts: list[Any] = []
    nid = first
    for kind, node, parent in plan.order:
        if kind == NODE_STATIC:
            node.el = nid
        elif kind == NODE_HOLE:
            holes.append((node, parent, nid))
        else:
            mounts.append((node, parent, nid))
        nid += 1

    for target, bkind, name, value in plan.bindings:
        el = target.el
        assert el is not None
        if bkind == BIND_TEXT:
            if value != " ":  # the clone already holds the placeholder space
                _emit((OP_SET_TEXT, el, value))
        elif bkind == BIND_EVENT:
            set_handler(el, name, value if callable(value) else None)
        elif bkind == BIND_REACTIVE:
            _bind_reactive_prop(el, name, value)
        elif bkind == BIND_PROP:
            _apply_single_prop(el, name, _UNSET, value)
        else:  # BIND_REF
            attach_ref({name: value}, el)

    _emit((OP_INSERT, parent_id, first, anchor_id))

    for node, parent, comment_id in holes:
        _mount_hole(node, parent.el, end_id=comment_id, ns=_template_ns(parent))

    if mounts:
        removed: list[int] = []
        for node, parent, comment_id in mounts:
            mount(node, parent.el, comment_id, _template_ns(parent))
            _emit((OP_REMOVE, comment_id))
            removed.append(comment_id)
        _emit((OP_RELEASE, removed))

    return True


def _template_ns(parent: VNode) -> str | None:
    """Namespace for children of a template-mounted element (HTML root)."""
    ns = parent.ns
    tag = parent.tag
    if isinstance(tag, str):
        return _child_ns(tag, ns)
    return ns


def _mount_fragment(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    """Mount a fragment: comment markers with the children directly in the parent."""
    start_id = _alloc_id()
    vnode.el = start_id
    _emit((OP_CREATE_COMMENT, start_id))
    _emit((OP_INSERT, parent_id, start_id, anchor_id))

    end_id = _alloc_id()
    vnode._frag_end = end_id
    _emit((OP_CREATE_COMMENT, end_id))
    _emit((OP_INSERT, parent_id, end_id, anchor_id))

    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    for child in norm_children:
        mount(child, parent_id, end_id, ns)


# ---------------------------------------------------------------------------
# Reactive holes
# ---------------------------------------------------------------------------


def _coerce_result(value: Any) -> VNode:
    """Convert what a hole or component returned into a single VNode."""
    if isinstance(value, VNode):
        return value
    if isinstance(value, (list, tuple)):
        return Fragment(*value)
    if value is None or value is True or value is False:
        return to_text_vnode("")
    if is_accessor(value):
        return hole(value)
    return to_text_vnode(value)


def _hole_updater(vnode: VNode, parent_id: int, end_id: int, getter: Any) -> Computation:
    """Create the render effect that evaluates a hole and patches its region.

    The expression runs tracked in the compute stage (owned by the
    effect, so anything it creates is disposed before the next run). The
    resulting tree is mounted in the apply stage under the hole's stable
    `scope`, so components kept across re-evaluations survive and
    context lookups from inside them resolve through the tree.
    """
    ns = vnode.ns
    scope_parent = _core._current_owner

    def compute() -> Any:
        try:
            return getter()
        except NotReadyError:
            # An async source has no value yet. Keep the current content;
            # the read registered with the nearest Loading boundary and
            # subscribed this hole to the resolution.
            return _KEEP
        except Exception as exc:
            if not _dispatch_to_error_boundary(exc, _core._current_observer):
                log_error(f"Reactive hole raised: {exc}", exc)
            return _KEEP

    def apply(result: Any) -> None:
        if result is _KEEP:
            return
        prev = vnode.subtree
        rtype = type(result)
        if rtype is str or rtype is int or rtype is float:
            text = result if rtype is str else str(result)
            if prev is not None:
                _unmount(prev)
                vnode.subtree = None
            if vnode._hole_text != text:
                _emit((OP_HOLE_TEXT, end_id, text))
                vnode._hole_text = text
            return
        if vnode._hole_text is not None:
            if vnode._hole_text:
                _emit((OP_SET_TEXT, end_id, ""))
            vnode._hole_text = None
        if vnode.scope is None:
            vnode.scope = Owner()
            if scope_parent is not None:
                scope_parent._add_child(vnode.scope)
        new_node = _coerce_result(result)
        vnode.subtree = new_node

        def commit() -> None:
            try:
                if prev is None:
                    mount(new_node, parent_id, end_id, ns)
                else:
                    patch(prev, new_node, parent_id, ns)
            except Exception as exc:
                if not _dispatch_to_error_boundary(exc):
                    log_error(f"Reactive hole update failed: {exc}", exc)

        _core._run_owned_untracked(vnode.scope, commit)

    comp = Computation(compute, kind=_K_RENDER, apply_scope=False, apply=apply, pass_prev=False)
    if scope_parent is not None:
        scope_parent._add_child(comp)
    comp._update_if_necessary()
    return comp


_KEEP = object()


def _mount_hole(
    vnode: VNode,
    parent_id: int,
    anchor_id: int | None = None,
    end_id: int | None = None,
    ns: str | None = None,
) -> None:
    """Mount a reactive hole: an end-anchor comment plus a render effect.

    When `end_id` is provided (template fast path), the existing
    placeholder comment is adopted as the end anchor.
    """
    if end_id is None:
        end_id = _alloc_id()
        _emit((OP_CREATE_COMMENT, end_id))
        _emit((OP_INSERT, parent_id, end_id, anchor_id))
    else:
        vnode.ns = ns
    vnode.el = end_id
    vnode._frag_end = end_id

    getter = vnode.props.get("getter")
    if not callable(getter):
        return
    vnode.render_effect = _hole_updater(vnode, parent_id, end_id, getter)


def _patch_hole(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch one hole against another, reusing the anchor, scope, and subtree."""
    new.el = old.el
    new._frag_end = old._frag_end
    new.subtree = old.subtree
    new.ns = old.ns
    new.scope = old.scope
    new._hole_text = old._hole_text

    old_getter = old.props.get("getter")
    new_getter = new.props.get("getter")

    if old_getter is new_getter:
        new.render_effect = old.render_effect
        return

    if old.render_effect is not None:
        old.render_effect.dispose()
        old.render_effect = None

    if not callable(new_getter):
        return
    assert new._frag_end is not None
    new.render_effect = _hole_updater(new, parent_id, new._frag_end, new_getter)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def _mount_component(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    """Mount a component with the run-once model.

    The body runs exactly once under a fresh ownership scope with a
    [`Props`][wybthon.Props] mapping bound to its parameters. Its result
    is coerced to a VNode and mounted; a reactive expression result
    becomes a single hole.
    """
    comp = vnode.tag
    assert callable(comp)

    ctx = _ComponentContext(comp)
    ctx._vnode = vnode
    vnode.component_ctx = ctx

    declared: Component | None = comp if isinstance(comp, Component) else None
    props = Props(vnode.props, declared.defaults if declared is not None else None)
    ctx._props = props

    parent_owner = _core._current_owner
    if parent_owner is not None:
        parent_owner._add_child(ctx)

    saved = _enter_component_setup(ctx)
    try:
        try:
            result = declared._render(props) if declared is not None else comp(props)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                result = None
            else:
                log_error(f"Render failed in component {component_name(comp)}", exc)
                raise
    finally:
        _exit_component_setup(saved)

    sub_tree = _coerce_result(result)
    vnode.subtree = sub_tree

    # Mount owned by the component and untracked (inlined
    # `_run_owned_untracked`: this runs once per component instance).
    prev_owner = _core._current_owner
    prev_obs = _core._current_observer
    _core._current_owner = ctx
    _core._current_observer = None
    try:
        try:
            mount(sub_tree, parent_id, anchor_id, ns)
            vnode.el = _first_dom_id(sub_tree)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                placeholder = to_text_vnode("")
                vnode.subtree = placeholder
                mount(placeholder, parent_id, anchor_id, ns)
                vnode.el = placeholder.el
            else:
                raise
    finally:
        _core._current_owner = prev_owner
        _core._current_observer = prev_obs


def _patch_component(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch a component: push the new props into the live accessors."""
    ctx = old.component_ctx
    if ctx is None:
        _replace(old, new, parent_id, old.ns)
        return
    props = ctx._props
    if props is not None:
        props._update(new.props)
    ctx._vnode = new
    new.component_ctx = ctx
    new.render_effect = old.render_effect
    new.subtree = old.subtree
    new.el = old.el
    new.ns = old.ns


# ---------------------------------------------------------------------------
# Unmount
# ---------------------------------------------------------------------------


def unmount(vnode: VNode) -> None:
    """Unmount `vnode`: dispose its scopes and effects, then remove its DOM.

    Safe to call on already-unmounted nodes (a no-op).
    """
    _unmount(vnode)
    kernel.commit()


def _unmount(vnode: VNode) -> None:
    first, last = _range_bounds(vnode)
    if first is not None:
        _emit((OP_REMOVE_RANGE, first, last))
    released: list[int] = []
    _dispose_tree(vnode, released)
    if released:
        _emit((OP_RELEASE, released))


def _dispose_tree(vnode: VNode, released: list[int]) -> None:
    """Dispose scopes, effects, and handlers recursively, collecting ids to release."""
    tag = vnode.tag

    if tag == "_hole":
        if vnode.render_effect is not None:
            vnode.render_effect.dispose()
            vnode.render_effect = None
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree, released)
            vnode.subtree = None
        if vnode.scope is not None:
            vnode.scope.dispose()
            vnode.scope = None
        if vnode.el is not None:
            released.append(vnode.el)
            vnode.el = None
        return

    if callable(tag):
        if vnode.component_ctx is not None:
            try:
                vnode.component_ctx.dispose()
            except Exception as e:
                log_error(f"Component disposal failed in {component_name(tag)}", e)
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree, released)
        vnode.el = None
        return

    if tag in ("_fragment", "_list", "_branch"):
        if vnode.render_effect is not None:
            vnode.render_effect.dispose()
            vnode.render_effect = None
        if vnode.scope is not None:
            vnode.scope.dispose()
            vnode.scope = None
        for child in vnode.children:
            if isinstance(child, VNode):
                _dispose_tree(child, released)
        if vnode.el is not None:
            released.append(vnode.el)
            vnode.el = None
        if vnode._frag_end is not None:
            released.append(vnode._frag_end)
            vnode._frag_end = None
        return

    if vnode.el is None:
        return
    detach_ref(vnode.el)
    remove_handlers_for(vnode.el)
    remove_bindings_for(vnode.el)
    for child in vnode.children:
        if isinstance(child, VNode):
            _dispose_tree(child, released)
    released.append(vnode.el)
    vnode.el = None


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


def _replace(old: VNode, new: VNode, parent_id: int, ns: str | None) -> None:
    """Unmount `old` and mount `new` at the same DOM position."""
    anchor = _first_dom_id(old)
    if anchor is None:
        _unmount(old)
        mount(new, parent_id, None, ns)
        return
    marker = _alloc_id()
    _emit((OP_CREATE_COMMENT, marker))
    _emit((OP_INSERT, parent_id, marker, anchor))
    _unmount(old)
    mount(new, parent_id, marker, ns)
    _emit((OP_REMOVE, marker))
    _emit((OP_RELEASE, [marker]))


def patch(old: VNode | None, new: VNode, parent_id: int, ns: str | None = None) -> None:
    """Diff `old` against `new` and emit minimal DOM ops under `parent_id`.

    Identical instances (`old is new`, e.g. cached list rows) are skipped.
    VNodes with the same type and key are patched in place; a different
    type or key is unmounted and remounted at the same position.
    """
    if old is None:
        mount(new, parent_id, None, ns)
        return

    if old is new:
        return

    # A different key means a different identity: remount rather than patch,
    # so `Leaf(key=user_id())` restarts its state when the id changes.
    if old.tag != new.tag or old.key != new.key:
        _replace(old, new, parent_id, ns)
        return

    tag = new.tag
    new.ns = old.ns

    if tag == "_text":
        new.el = old.el
        if new.el is not None:
            old_text = old.props.get("nodeValue", "")
            new_text = new.props.get("nodeValue", "")
            if old_text != new_text:
                _emit((OP_SET_TEXT, new.el, new_text))
        return

    if tag == "_hole":
        _patch_hole(old, new, parent_id)
        return

    if tag in ("_list", "_branch"):
        _replace(old, new, parent_id, ns)
        return

    if tag == "_fragment":
        _patch_fragment(old, new, parent_id)
        return

    if callable(tag):
        _patch_component(old, new, parent_id)
        return

    assert old.el is not None
    new.el = old.el
    apply_props(new.el, old.props, new.props)
    if new.props.get("ref") is not old.props.get("ref"):
        detach_ref(new.el)
        attach_ref(new.props, new.el)

    new_children = normalize_children(new.children)
    new.children = new_children
    assert isinstance(tag, str)
    _reconcile_children(old.children, new_children, new.el, None, _child_ns(tag, old.ns))


def _patch_fragment(old: VNode, new: VNode, parent_id: int) -> None:
    new.el = old.el
    new._frag_end = old._frag_end
    new_children = normalize_children(new.children)
    new.children = new_children
    _reconcile_children(old.children, new_children, parent_id, new._frag_end, old.ns)


def _reconcile_children(
    old_children: list[VNode],
    new_children: list[VNode],
    parent_id: int,
    end_marker: int | None,
    ns: str | None,
) -> None:
    """Diff two child lists and emit mounts, patches, moves, and removals.

    Matching runs in three linear passes: identity (the same VNode
    instance, e.g. cached rows), key, then type in document order. DOM
    moves are minimized with a longest-increasing-subsequence pass.

    List rows (VNodes carrying an `owner_scope`) match by identity only:
    a row the list primitive didn't reuse belongs to a disposed scope and
    must be replaced, never patched into.
    """
    n_old = len(old_children)
    n = len(new_children)

    def same_edge(old: VNode, new: VNode) -> bool:
        return old is new or (
            old.owner_scope is None
            and new.owner_scope is None
            and old.key is not None
            and old.key == new.key
            and old.tag == new.tag
        )

    prefix = 0
    while prefix < min(n_old, n) and same_edge(old_children[prefix], new_children[prefix]):
        patch(old_children[prefix], new_children[prefix], parent_id, ns)
        prefix += 1
    suffix = 0
    while suffix < min(n_old, n) - prefix and same_edge(old_children[-1 - suffix], new_children[-1 - suffix]):
        suffix += 1
    if prefix or suffix or not n_old or not n:
        for i in range(suffix, 0, -1):
            patch(old_children[-i], new_children[-i], parent_id, ns)
        old_middle = old_children[prefix : n_old - suffix]
        new_middle = new_children[prefix : n - suffix]
        anchor = _first_dom_id(new_children[n - suffix]) if suffix else end_marker
        if not old_middle:
            for child in new_middle:
                mount(child, parent_id, anchor, ns)
        elif not new_middle:
            for child in old_middle:
                _unmount(child)
        else:
            _reconcile_children(old_middle, new_middle, parent_id, anchor, ns)
        return

    used_old: list[bool] = [False] * n_old
    sources: list[int] = [-1] * n
    needs_patch: list[bool] = [False] * n

    old_ids: dict[int, int] = {}
    old_keys: dict[str | int, int] = {}
    for j, oc in enumerate(old_children):
        old_ids[id(oc)] = j
        if oc.key is not None and oc.owner_scope is None:
            old_keys[oc.key] = j

    unmatched: list[int] = []
    for i, nc in enumerate(new_children):
        j = old_ids.get(id(nc))
        if j is not None and not used_old[j]:
            used_old[j] = True
            sources[i] = j
            continue
        if nc.owner_scope is not None:
            continue
        if nc.key is not None:
            j = old_keys.get(nc.key)
            if j is not None and not used_old[j]:
                used_old[j] = True
                sources[i] = j
                needs_patch[i] = True
                continue
        unmatched.append(i)

    if unmatched:
        type_queues: dict[Any, list[int]] = {}
        type_pos: dict[Any, int] = {}
        for j, oc in enumerate(old_children):
            if not used_old[j] and oc.key is None and oc.owner_scope is None:
                type_queues.setdefault(oc.tag, []).append(j)
        for i in unmatched:
            nc = new_children[i]
            if nc.key is not None:
                continue
            queue = type_queues.get(nc.tag)
            if queue is None:
                continue
            pos = type_pos.get(nc.tag, 0)
            while pos < len(queue) and used_old[queue[pos]]:
                pos += 1
            type_pos[nc.tag] = pos
            if pos < len(queue):
                j = queue[pos]
                type_pos[nc.tag] = pos + 1
                used_old[j] = True
                sources[i] = j
                needs_patch[i] = True

    for i in range(n):
        if needs_patch[i]:
            patch(old_children[sources[i]], new_children[i], parent_id, ns)

    previous_source = -1
    ordered = True
    for source in sources:
        if source >= 0:
            if source < previous_source:
                ordered = False
                break
            previous_source = source
    lis_set: set[int] | None = None
    if not ordered:
        tails: list[int] = []
        tails_idx: list[int] = []
        prev_idx: list[int] = [-1] * n
        for i in range(n):
            s = sources[i]
            if s == -1:
                continue
            pos = bisect_left(tails, s)
            if pos == len(tails):
                tails.append(s)
                tails_idx.append(i)
            else:
                tails[pos] = s
                tails_idx[pos] = i
            prev_idx[i] = tails_idx[pos - 1] if pos > 0 else -1

        lis_set = set()
        k = tails_idx[-1] if tails_idx else -1
        while k != -1:
            lis_set.add(k)
            k = prev_idx[k]

    next_anchor = end_marker
    i = n - 1
    while i >= 0:
        if sources[i] == -1:
            # A run of new children mounts in document order, each before
            # the same anchor, so component bodies and on_settled callbacks
            # run front to back like an initial mount.
            start = i
            while start > 0 and sources[start - 1] == -1:
                start -= 1
            run_first: int | None = None
            for r in range(start, i + 1):
                new_child = new_children[r]
                try:
                    mount(new_child, parent_id, next_anchor, ns)
                except Exception as e:
                    if not _dispatch_to_error_boundary(e):
                        log_error(f"Failed to mount child at index {r}", e)
                    continue
                if run_first is None:
                    run_first = _first_dom_id(new_child)
            if run_first is not None:
                next_anchor = run_first
            i = start - 1
            continue
        new_child = new_children[i]
        first_dom = _first_dom_id(new_child)
        if first_dom is not None:
            if lis_set is not None and i not in lis_set:
                _move_range(new_child, parent_id, next_anchor)
            next_anchor = first_dom
        i -= 1

    for j, oc in enumerate(old_children):
        if not used_old[j]:
            _unmount(oc)

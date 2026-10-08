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

- **Hydration claims instead of creating.** [`hydrate`][wybthon.hydrate]
  runs the same mount code, but each node claims the matching node a
  server render already put in the document (see
  [`wybthon.server`][wybthon.server]).

Public surface: [`render`][wybthon.render] and
[`hydrate`][wybthon.hydrate], plus the lower-level `mount`, `unmount`,
and `patch` used by control-flow primitives.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

from . import _template as template
from . import kernel
from ._dom_props import (
    _bindings,
    _ref_cleanups,
    apply_initial_props,
    apply_props,
    attach_ref,
    detach_ref,
    remove_bindings_for,
)
from ._warnings import component_name, log_error
from .component import Component
from .dom import Element
from .events import _handlers, remove_handlers_for
from .kernel import (
    OP_CLAIM_COMMENT,
    OP_CLAIM_ELEMENT,
    OP_CLAIM_STATIC,
    OP_CLAIM_TEXT,
    OP_CREATE_COMMENT,
    OP_CREATE_ELEMENT,
    OP_CREATE_ELEMENT_NS,
    OP_CREATE_TEXT,
    OP_DISPOSE,
    OP_DISPOSE_RANGE,
    OP_HOLE_TEXT,
    OP_HYDRATE,
    OP_HYDRATE_END,
    OP_INSERT,
    OP_MOVE_RANGE,
    OP_RELEASE,
    OP_ROOT,
    OP_SET_TEXT,
    OP_UNROOT,
)
from .reactivity import _core
from .reactivity._core import (
    _K_RENDER,
    Computation,
    Owner,
    _ComponentContext,
    _enter_component_setup,
    _exit_component_setup,
    flush,
    is_accessor,
)
from .reactivity._props import RawProps
from .vnode import NS_MATHML, NS_SVG, Fragment, VNode, hole, normalize_children, to_text_vnode

__all__ = ["render", "hydrate", "Root", "mount", "unmount", "patch"]

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
    container_el = _container(container)
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

        root = _new_root(container_el, node, release=isinstance(container, str))
        _core.run_with_owner(root._owner, lambda: mount(node, container_id))
        flush()
        return root
    finally:
        _core._gc_resume()


def hydrate(vnode: Any, container: Element | str | int) -> Root:
    """Adopt server-rendered HTML under `container` and make it interactive.

    The counterpart of [`render`][wybthon.render] for pages rendered by
    [`wybthon.server`][wybthon.server]. The tree mounts exactly as
    `render` would mount it, except that each node claims the matching
    node the server already put in the document instead of creating a
    new one. Async values the server resolved come from the page's
    `data-wyb-state` script, so they're neither fetched again nor shown
    as loading. Input recorded by the production bootstrap before
    hydration is replayed afterward.

    Mismatches never break the page: a node that doesn't match is
    created in place, server nodes nobody claimed are removed, and dev
    mode logs a warning.

    Args:
        vnode: The same root view the server rendered.
        container: The element holding the server-rendered markup: an
            [`Element`][wybthon.Element], a CSS selector, or a kernel
            node id.

    Returns:
        A [`Root`][wybthon.Root], as from `render`.

    Example:
        ```python
        from wybthon import hydrate

        hydrate(App(), "#app")
        ```
    """
    from .reactivity._session import Session, decode_state

    container_el = _container(container)
    container_id = container_el.node_id
    values, errors, failed = decode_state(kernel.take_state(container_id))
    node = _coerce_result(vnode)
    session = Session("hydrate", values=values, errors=errors, failed=failed)

    _core._gc_pause()
    try:
        root = _new_root(container_el, node, release=isinstance(container, str))
        _emit((OP_HYDRATE, container_id))
        previous = _core._session
        _core._session = session
        session.keying = True
        kernel.claiming = True
        node.pk = "r"
        try:
            _core.run_with_owner(root._owner, lambda: mount(node, container_id))
        finally:
            kernel.claiming = False
            session.keying = False
            _core._session = previous
            _emit((OP_HYDRATE_END,))
        flush()
    finally:
        _core._gc_resume()
    kernel.replay_events()
    if session.after_hydration:
        for callback in session.after_hydration:
            try:
                callback()
            except Exception as exc:
                log_error(f"Post-hydration callback raised: {exc}", exc)
        flush()
    return root


def _container(container: Element | str | int) -> Element:
    if isinstance(container, str):
        return Element(container, existing=True)
    if isinstance(container, int):
        return Element(node_id=container)
    return container


def _new_root(container_el: Element, node: VNode, *, release: bool) -> Root:
    container_id = container_el.node_id
    root = Root(container_el, node, Owner())
    root._release_container = release
    _roots[container_id] = root
    _emit((OP_ROOT, container_id))
    return root


def _server_render(vnode: Any, container_id: int, session: Any) -> Root:
    """Mount `vnode` into a server container for one server render pass.

    The session keys memos for the whole pass (mount and flush) and
    carries the request URL. See `wybthon.server`.
    """
    node = _coerce_result(vnode)
    _core._gc_pause()
    previous = _core._session
    _core._session = session
    session.keying = True
    try:
        root = Root(Element(node_id=container_id), node, Owner())
        root._release_container = True
        _roots[container_id] = root
        node.pk = "r"
        _core.run_with_owner(root._owner, lambda: mount(node, container_id))
        flush()
        return root
    finally:
        session.keying = False
        _core._session = previous
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
    if vnode.tag in ("_fragment", "_list", "_branch", "_static"):
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
    # Disposing the lot also releases any content still parked inside it.
    _emit((OP_DISPOSE, lot))


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


def mount(
    vnode: VNode | str, parent_id: int, anchor_id: int | None = None, ns: str | None = None, final: bool = False
) -> None:
    """Emit ops mounting a VNode (or string) under `parent_id`.

    When the VNode carries an `owner_scope` (set by list primitives for
    cached rows), mounting runs under that owner with tracking suspended,
    so the row's effects survive later list updates.

    Args:
        vnode: The VNode to mount. Strings are coerced to text VNodes.
        parent_id: Kernel id of the parent node.
        anchor_id: Optional sibling id to insert before (`None` appends).
        ns: Namespace of the parent (`None` for HTML).
        final: The subtree will never be patched (a component's output).
            List rows are final too. A final template-mounted subtree
            releases its static VNodes once mounted.
    """
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)
    scope = vnode.owner_scope
    if scope is not None:
        _core._run_owned_untracked(scope, lambda: _mount_dispatch(vnode, parent_id, anchor_id, ns, True))
        return
    _mount_dispatch(vnode, parent_id, anchor_id, ns, final)


def _mount_dispatch(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None, final: bool = False) -> None:
    tag = vnode.tag
    vnode.ns = ns

    if tag == "_text":
        nid = _alloc_id()
        vnode.el = nid
        if kernel.claiming:
            _emit((OP_CLAIM_TEXT, nid, parent_id, vnode.props.get("nodeValue", "")))
            return
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

    if tag == "_static":
        _mount_static(vnode, parent_id, anchor_id)
        return

    if callable(tag):
        _mount_component(vnode, parent_id, anchor_id, ns)
        return

    if (
        ns is None
        and not kernel.claiming
        and (kernel.html_templates or (kernel.html_templates is None and kernel.supports_html()))
        and template.mount(vnode, parent_id, anchor_id, final)
    ):
        return

    _mount_element(vnode, parent_id, anchor_id, ns)


def _mount_element(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    """Mount an element subtree with per-node ops (the template-ineligible path)."""
    tag = vnode.tag
    assert isinstance(tag, str)
    nid = _alloc_id()
    vnode.el = nid
    el_ns = _element_ns(tag, ns)
    claiming = kernel.claiming
    if claiming:
        _emit((OP_CLAIM_ELEMENT, nid, parent_id, tag, el_ns))
    elif el_ns is None:
        _emit((OP_CREATE_ELEMENT, nid, tag))
    else:
        _emit((OP_CREATE_ELEMENT_NS, nid, el_ns, tag))
    apply_initial_props(nid, vnode.props)
    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    child_ns = _child_ns(tag, ns)
    if _core._session is not None:
        _assign_positions(vnode, norm_children)
    for child in norm_children:
        mount(child, nid, None, child_ns)
    if not claiming:
        _emit((OP_INSERT, parent_id, nid, anchor_id))
    attach_ref(vnode.props, nid)


def _mount_fragment(vnode: VNode, parent_id: int, anchor_id: int | None, ns: str | None) -> None:
    """Mount a fragment: comment markers with the children directly in the parent."""
    claim_end = _open_fragment(vnode, parent_id, anchor_id)
    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    end_id = vnode._frag_end
    if _core._session is not None:
        _assign_positions(vnode, norm_children)
    for child in norm_children:
        mount(child, parent_id, end_id, ns)
    if claim_end:
        _close_fragment(vnode, parent_id)


def _mount_static(vnode: VNode, parent_id: int, anchor_id: int | None) -> None:
    """Keep a server-rendered region as static DOM (`NoHydration` while hydrating)."""
    claim_end = _open_fragment(vnode, parent_id, anchor_id)
    if claim_end:
        _emit((OP_CLAIM_STATIC, parent_id, "/" + vnode.props["marker"]))
        _close_fragment(vnode, parent_id)


def _assign_positions(parent: VNode, children: list[VNode]) -> None:
    """Give each child a position key derived from its parent's (hydration keys)."""
    base = getattr(parent, "pk", None) or _core._position
    for i, child in enumerate(children):
        child.pk = f"{base}.{i}"


def _open_fragment(vnode: VNode, parent_id: int, anchor_id: int | None) -> bool:
    """Create (or claim) a fragment's start marker and allocate its end marker.

    Returns True when the end marker must be claimed with
    `_close_fragment` once the content has been claimed: in hydration
    the end marker follows the content in the server's DOM. A `marker`
    prop becomes the markers' comment data (`Loading` boundaries use it
    for streaming and to resynchronize hydration).
    """
    marker = vnode.props.get("marker")
    start_id = _alloc_id()
    vnode.el = start_id
    end_id = _alloc_id()
    vnode._frag_end = end_id
    if kernel.claiming:
        _emit((OP_CLAIM_COMMENT, start_id, parent_id, marker or ""))
        return True
    if marker:
        _emit((OP_CREATE_COMMENT, start_id, marker))
        _emit((OP_INSERT, parent_id, start_id, anchor_id))
        _emit((OP_CREATE_COMMENT, end_id, "/" + marker))
    else:
        _emit((OP_CREATE_COMMENT, start_id))
        _emit((OP_INSERT, parent_id, start_id, anchor_id))
        _emit((OP_CREATE_COMMENT, end_id))
    _emit((OP_INSERT, parent_id, end_id, anchor_id))
    return False


def _close_fragment(vnode: VNode, parent_id: int) -> None:
    marker = vnode.props.get("marker")
    _emit((OP_CLAIM_COMMENT, vnode._frag_end, parent_id, "/" + marker if marker else ""))


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


def _hole_updater(
    vnode: VNode, parent_id: int, end_id: int, getter: Any, claim: list[bool] | None = None
) -> Computation:
    """Create the render effect that evaluates a hole and patches its region.

    The expression runs tracked in the compute stage (owned by the
    effect's provisional owner). Superseded preparations are disposed;
    the published preparation survives until a replacement applies. The tree
    is mounted in the apply stage under the hole's stable
    `scope`, so components kept across re-evaluations survive and
    context lookups from inside them resolve through the tree.
    """
    ns = vnode.ns
    scope_parent = _core._current_owner

    # The expression runs as a ``keep`` render effect: when an async source
    # has no value yet, the hole keeps its current content (the read
    # registered with the nearest Loading boundary and subscribed this hole
    # to the resolution), and an exception routes to the nearest Errored
    # boundary through the apply stage.
    def apply(result: Any) -> None:
        if result is _KEEP:
            return
        prev = vnode.subtree
        rtype = type(result)
        if claim is not None and claim[0] and kernel.claiming:
            # Hydrating: a text result claims the server's text node as the
            # anchor itself; other results claim their content first and the
            # anchor comment after it, in document order.
            claim[0] = False
            if rtype is str or rtype is int or rtype is float:
                text = result if rtype is str else str(result)
                _emit((OP_CLAIM_TEXT, end_id, parent_id, text))
                vnode._hole_text = text
                return
            if vnode.scope is None:
                vnode.scope = Owner()
                if scope_parent is not None:
                    scope_parent._add_child(vnode.scope)
            new_node = _coerce_result(result)
            new_node.pk = f"{getattr(vnode, 'pk', None) or _core._position}.h"
            vnode.subtree = new_node

            def claim_content() -> None:
                try:
                    mount(new_node, parent_id, end_id, ns)
                except Exception as exc:
                    if not _dispatch_to_error_boundary(exc):
                        log_error(f"Reactive hole update failed: {exc}", exc)

            _core._run_owned_untracked(vnode.scope, claim_content)
            _emit((OP_CLAIM_COMMENT, end_id, parent_id, ""))
            return
        if rtype is str or rtype is int or rtype is float:
            text = result if rtype is str else str(result)
            if prev is not None:
                _unmount(prev)
                vnode.subtree = None
            if vnode._hole_text != text:
                slot = _clone_slot
                if slot is not None and slot[2] is vnode and slot[3] == kernel.generation:
                    slot[0][slot[1]] = text
                else:
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
        if _core._session is not None:
            new_node.pk = f"{getattr(vnode, 'pk', None) or _core._position}.h"
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

    fn: Any = getter
    if _core._session is not None:
        # Server rendering and hydration: memos created by the expression
        # are keyed by the hole's position (checked per run, since the
        # session ends after the mount).
        position = f"{getattr(vnode, 'pk', None) or _core._position}h"
        plain = fn

        def fn() -> Any:
            session = _core._session
            if session is None or not session.keying:
                return plain()
            previous = _core._enter_position(position)
            try:
                return plain()
            finally:
                _core._restore_position(previous)

    comp = Computation(fn, kind=_K_RENDER, apply_scope=False, apply=apply, pass_prev=False, keep=True)
    if scope_parent is not None:
        scope_parent._add_child(comp)
    comp._update_if_necessary()
    return comp


_KEEP = _core._SKIP_APPLY

# While a template mount creates a text-anchored hole: `(clone command,
# slot index, hole VNode, kernel generation)`. The hole's first text result
# fills that slot of the not-yet-committed clone instead of a separate write.
_clone_slot: tuple[list[Any], int, VNode, int] | None = None


def _mount_hole(
    vnode: VNode,
    parent_id: int,
    anchor_id: int | None = None,
    end_id: int | None = None,
    ns: str | None = None,
    text: bool = False,
    clone: list[Any] | None = None,
    slot: int = 0,
) -> None:
    """Mount a reactive hole: an end anchor plus a render effect.

    When `end_id` is provided (template fast path), the existing
    placeholder is adopted as the end anchor. `text` marks a placeholder
    that's a one-space text node rather than a comment: a text result is
    then written straight into it. `clone` and `slot` name the template's
    clone command and the text slot the hole's first text result fills.
    """
    claim: list[bool] | None = None
    if end_id is None:
        end_id = _alloc_id()
        if kernel.claiming:
            claim = [True]
        else:
            _emit((OP_CREATE_COMMENT, end_id))
            _emit((OP_INSERT, parent_id, end_id, anchor_id))
    else:
        vnode.ns = ns
        if text:
            vnode._hole_text = " "
    vnode.el = end_id
    vnode._frag_end = end_id

    getter = vnode.props.get("getter")
    if callable(getter):
        if clone is None:
            vnode.render_effect = _hole_updater(vnode, parent_id, end_id, getter, claim)
        else:
            global _clone_slot
            previous = _clone_slot
            _clone_slot = (clone, slot, vnode, kernel.generation)
            try:
                vnode.render_effect = _hole_updater(vnode, parent_id, end_id, getter, claim)
            finally:
                _clone_slot = previous
    if claim is not None and claim[0]:
        # Nothing claimed the anchor (the expression isn't ready, or its
        # first result applies later): it's the server's empty-hole comment.
        claim[0] = False
        _emit((OP_CLAIM_COMMENT, end_id, parent_id, ""))


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

    The body runs exactly once under a fresh ownership scope, receiving
    its typed [`Props`][wybthon.Props] instance. Its result
    is coerced to a VNode and mounted; a reactive expression result
    becomes a single hole.
    """
    comp = vnode.tag
    assert callable(comp)

    ctx = _ComponentContext(comp)
    ctx._vnode = vnode
    vnode.component_ctx = ctx

    parent_owner = _core._current_owner
    if parent_owner is not None:
        parent_owner._add_child(ctx)

    session = _core._session
    keyed = session is not None and session.keying
    if keyed:
        position = f"{getattr(vnode, 'pk', None) or _core._position}:{component_name(comp)}"
        previous_position = _core._enter_position(position)
    saved = _enter_component_setup(ctx)
    try:
        try:
            if isinstance(comp, Component):
                result, ctx._props = comp._render(vnode.props)
            else:
                ctx._props = RawProps(vnode.props)
                result = comp(ctx._props)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                result = None
            else:
                log_error(f"Render failed in component {component_name(comp)}", exc)
                raise
    finally:
        _exit_component_setup(saved)
        if keyed:
            _core._restore_position(previous_position)

    sub_tree = _coerce_result(result)
    vnode.subtree = sub_tree
    if keyed:
        sub_tree.pk = position + "/"

    # Mount owned by the component and untracked (inlined
    # `_run_owned_untracked`: this runs once per component instance).
    prev_owner = _core._current_owner
    prev_obs = _core._current_observer
    _core._current_owner = ctx
    _core._current_observer = None
    try:
        try:
            # A component's output is never patched: only its props update.
            mount(sub_tree, parent_id, anchor_id, ns, True)
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
        props._wyb_update(new.props)
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
        # The kernel releases every node registered inside the range.
        _emit((OP_DISPOSE_RANGE, first, last))
    _dispose_tree(vnode)


def _dispose_tree(vnode: VNode) -> None:
    """Dispose scopes, effects, handlers, refs, and bindings recursively.

    Native nodes are released by the kernel when their range is
    disposed; this only tears down the Python side.
    """
    tag = vnode.tag

    if tag == "_hole":
        if vnode.render_effect is not None:
            vnode.render_effect.dispose()
            vnode.render_effect = None
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree)
            vnode.subtree = None
        if vnode.scope is not None:
            vnode.scope.dispose()
            vnode.scope = None
        vnode.el = None
        return

    if vnode.tpl is not None:
        template.dispose(vnode, _dispose_tree)
        return

    if callable(tag):
        if vnode.component_ctx is not None:
            try:
                vnode.component_ctx.dispose()
            except Exception as e:
                log_error(f"Component disposal failed in {component_name(tag)}", e)
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree)
        vnode.el = None
        return

    if tag in ("_fragment", "_list", "_branch", "_static"):
        if vnode.render_effect is not None:
            vnode.render_effect.dispose()
            vnode.render_effect = None
        if vnode.scope is not None:
            vnode.scope.dispose()
            vnode.scope = None
        for child in vnode.children:
            if isinstance(child, VNode):
                _dispose_tree(child)
        vnode.el = None
        vnode._frag_end = None
        return

    el = vnode.el
    if el is None:
        return
    if el in _ref_cleanups:
        detach_ref(el)
    if el in _handlers:
        remove_handlers_for(el)
    if el in _bindings:
        remove_bindings_for(el)
    for child in vnode.children:
        if isinstance(child, VNode):
            _dispose_tree(child)
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
    _emit((OP_DISPOSE, marker))


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

    if tag in ("_list", "_branch", "_static"):
        _replace(old, new, parent_id, ns)
        return

    if tag == "_fragment":
        _patch_fragment(old, new, parent_id)
        return

    if callable(tag):
        _patch_component(old, new, parent_id)
        return

    if old.tpl is not None:
        template.materialize(old)
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
        if old_children[prefix] is not new_children[prefix]:
            patch(old_children[prefix], new_children[prefix], parent_id, ns)
        prefix += 1
    suffix = 0
    while suffix < min(n_old, n) - prefix and same_edge(old_children[-1 - suffix], new_children[-1 - suffix]):
        suffix += 1
    if prefix or suffix or not n_old or not n:
        for i in range(suffix, 0, -1):
            if old_children[-i] is not new_children[-i]:
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

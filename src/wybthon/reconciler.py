"""Reconciliation engine: mounting, patching, and unmounting VNode trees.

This module translates VNode trees into batched DOM operations. It
never touches the DOM directly: every mutation is emitted as a compact
op against an integer node id (see `wybthon.kernel`), and the whole
buffer is applied in a single bridge crossing at commit time (end of
`render`, end of each effect flush).

Mental model:

- **Components run once.** A function component is invoked a single time
  during mount. Its returned VNode tree is mounted directly. Reactive
  updates flow through *reactive holes* embedded in that tree, not by
  re-running the component body.
- **Reactive holes** are `_dynamic` VNodes whose `getter` is re-evaluated
  by an effect when its dependencies change. They're created automatically
  whenever a callable child or callable prop value appears in the tree,
  and explicitly via [`dynamic`][wybthon.dynamic].
- **Components return a VNode** (or a value coercible to one). The
  idiomatic style is to return a static tree and use `dynamic` for
  explicit reactive subtrees; a returned zero-arg callable is also
  accepted and is wrapped in a single reactive hole for convenience
  (handy when authoring higher-order components).

Public surface:

- [`render`][wybthon.render]: top-level entry point.
- [`mount`][wybthon.reconciler.mount]: emit ops creating DOM for a new
  VNode under a parent node id.
- [`unmount`][wybthon.reconciler.unmount]: tear down a VNode and its DOM.
- [`patch`][wybthon.reconciler.patch]: diff two VNodes and emit the
  difference.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Dict, List, Optional, Set, Union

from . import kernel
from ._warnings import component_name, log_error
from .dom import Element
from .events import remove_handlers_for, set_handler
from .kernel import (
    OP_CLONE_TPL,
    OP_CREATE_COMMENT,
    OP_CREATE_ELEMENT,
    OP_CREATE_TEXT,
    OP_INSERT,
    OP_RELEASE,
    OP_REMOVE,
    OP_SET_TEXT,
)
from .props import _apply_single_prop, _bind_reactive_prop, apply_initial_props, apply_props, attach_ref, detach_ref
from .reactivity import (
    ReactiveProps,
    _ComponentContext,
    _get_component_ctx,
    batch,
    effect,
)
from .template import (
    BIND_EVENT,
    BIND_PROP,
    BIND_REACTIVE,
    BIND_TEXT,
    NODE_HOLE,
    NODE_STATIC,
    build_plan,
)
from .vnode import VNode, dynamic, normalize_children, to_text_vnode

__all__ = ["render", "mount", "unmount", "patch"]

# Rendered root per container, keyed by the container's kernel node id.
_container_registry: Dict[int, VNode] = {}

_emit = kernel.emit
_alloc_id = kernel.alloc_id


def _dispatch_to_error_boundary(exc: BaseException) -> bool:
    """Route a mount/render error to the nearest ancestor error boundary.

    Walks the active ownership chain (from the current owner upward) looking
    for the first scope that has an ``_error_handler`` installed by
    :func:`wybthon.error_boundary.ErrorBoundary`. If one is found it's
    invoked (which swaps in the boundary's fallback on the next flush) and
    this returns ``True``. When no boundary exists it returns ``False`` so
    the caller can log and swallow the error as before.

    This is what makes ``ErrorBoundary`` catch *synchronous* errors thrown
    while mounting descendant components or evaluating reactive holes; the
    reconciler's defensive ``try``/``except`` sites would otherwise swallow
    them before they could reach a boundary.
    """
    import wybthon.reactivity as _rx

    owner = _rx._current_owner
    while owner is not None:
        handler = getattr(owner, "_error_handler", None)
        if handler is not None:
            try:
                handler(exc)
            except Exception as handler_exc:  # pragma: no cover - defensive
                log_error(f"Error boundary handler raised: {handler_exc}", handler_exc)
            return True
        owner = owner._parent
    return False


def render(vnode: VNode, container: Union[Element, str, int]) -> Element:
    """Render a VNode tree into a container element.

    Subsequent calls with the same `container` *patch* the existing tree
    in place; only the differences are applied. All emitted DOM ops are
    committed to the backend in one batch before this returns.

    Args:
        vnode: The root VNode to render.
        container: An [`Element`][wybthon.Element] wrapper, a CSS selector
            string identifying an existing DOM node, or a kernel node id.

    Returns:
        The wrapped container `Element`. Useful for chaining or for
        retaining a reference to the mount point.

    Example:
        ```python
        from wybthon import h, render

        render(h("h1", {}, "Hello, world!"), "#app")
        ```
    """
    if isinstance(container, str):
        container_el = Element(container, existing=True)
    elif isinstance(container, int):
        container_el = Element(node_id=container)
    else:
        container_el = container
    container_id = container_el.node_id
    prev = _container_registry.get(container_id)
    # Batch so signal writes during mount (Suspense registrations, error
    # boundary trips) defer their effects until the mount stack has fully
    # unwound, instead of re-entering the reconciler mid-mount.
    batch(lambda: patch(prev, vnode, container_id))
    _container_registry[container_id] = vnode
    kernel.commit()
    return container_el


# ---------------------------------------------------------------------------
# DOM-position helpers (computed from the VNode tree; no DOM reads)
# ---------------------------------------------------------------------------


def _first_dom_id(vnode: VNode) -> Optional[int]:
    """Return the id of the first DOM node belonging to this vnode."""
    while True:
        if vnode.tag == "_dynamic":
            if vnode.subtree is not None:
                first = _first_dom_id(vnode.subtree)
                if first is not None:
                    return first
            return vnode.el
        if vnode.subtree is not None:
            vnode = vnode.subtree
            continue
        return vnode.el


def _dom_node_ids(vnode: VNode) -> List[int]:
    """Return the ids of all top-level DOM nodes belonging to this vnode."""
    if vnode.tag == "_dynamic":
        nodes: List[int] = []
        if vnode.subtree is not None:
            nodes.extend(_dom_node_ids(vnode.subtree))
        if vnode.el is not None:
            nodes.append(vnode.el)
        return nodes
    if vnode.subtree is not None:
        return _dom_node_ids(vnode.subtree)
    if vnode.tag == "_fragment":
        if vnode.el is None:
            return []
        # Mounted fragments always carry normalized children.
        frag_nodes: List[int] = [vnode.el]
        for child in vnode.children:
            frag_nodes.extend(_dom_node_ids(child))
        if vnode._frag_end is not None:
            frag_nodes.append(vnode._frag_end)
        return frag_nodes
    if vnode.el is not None:
        return [vnode.el]
    return []


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def mount(vnode: Union[VNode, str], parent_id: int, anchor_id: Optional[int] = None) -> None:
    """Emit ops mounting a VNode (or string) under the node `parent_id`.

    When the VNode carries an `owner_scope` (set by `For`/`Index` for
    cached rows), mounting runs under that reactive owner so the row's
    effects survive later list updates.

    Args:
        vnode: The VNode to mount. Strings are coerced to text VNodes.
        parent_id: Kernel id of the parent node.
        anchor_id: Optional id of the sibling node to insert before.
            When `None`, the new nodes are appended to the parent.
    """
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)

    scope = vnode.owner_scope
    if scope is not None:
        import wybthon.reactivity as _rx

        prev_owner = _rx._current_owner
        _rx._current_owner = scope
        try:
            _mount_dispatch(vnode, parent_id, anchor_id)
        finally:
            _rx._current_owner = prev_owner
        return

    _mount_dispatch(vnode, parent_id, anchor_id)


def _mount_dispatch(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> None:
    """Route a VNode to the appropriate mount strategy by tag."""
    tag = vnode.tag

    if tag == "_text":
        nid = _alloc_id()
        vnode.el = nid
        _emit((OP_CREATE_TEXT, nid, vnode.props.get("nodeValue", "")))
        _emit((OP_INSERT, parent_id, nid, anchor_id))
        return

    if tag == "_dynamic":
        _mount_dynamic(vnode, parent_id, anchor_id)
        return

    if tag == "_fragment":
        _mount_fragment(vnode, parent_id, anchor_id)
        return

    if callable(tag):
        _mount_component(vnode, parent_id, anchor_id)
        return

    if _mount_template(vnode, parent_id, anchor_id):
        return

    _mount_element(vnode, parent_id, anchor_id)


def _mount_element(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> None:
    """Mount an element subtree with per-node ops (the template-ineligible path)."""
    assert isinstance(vnode.tag, str)
    nid = _alloc_id()
    vnode.el = nid
    _emit((OP_CREATE_ELEMENT, nid, vnode.tag))
    apply_initial_props(nid, vnode.props)
    norm_children = normalize_children(vnode.children)
    vnode.children = norm_children
    for child in norm_children:
        mount(child, nid)
    _emit((OP_INSERT, parent_id, nid, anchor_id))
    attach_ref(vnode.props, nid)


def _mount_template(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> bool:
    """Mount an element subtree through the template fast path.

    Serializes the static skeleton to HTML (text content hoisted),
    registers it with the kernel on first use, and emits one
    `CLONE_TPL` op; the kernel clones the pre-parsed template and
    assigns a dense id block in the same pre-order the serializer
    counted, so every element, text node, and placeholder comment is
    addressable with no further communication. Text content, dynamic
    bindings, and dynamic children are then wired by id.

    Returns:
        `True` when the subtree was mounted, `False` when it isn't
        eligible (the caller falls back to per-node ops).
    """
    if not kernel.supports_html():
        return False
    plan = build_plan(vnode)
    if plan is None:
        return False

    count = plan.node_count
    first = kernel.alloc_ids(count)
    _emit((OP_CLONE_TPL, first, count, kernel.template_id(plan.html)))

    holes: List[Any] = []
    mounts: List[Any] = []
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
            _apply_single_prop(el, name, None, value)
        else:  # BIND_REF
            attach_ref({name: value}, el)

    _emit((OP_INSERT, parent_id, first, anchor_id))

    for node, parent, comment_id in holes:
        _mount_dynamic(node, parent.el, end_id=comment_id)

    if mounts:
        removed: List[int] = []
        for node, parent, comment_id in mounts:
            mount(node, parent.el, comment_id)
            _emit((OP_REMOVE, comment_id))
            removed.append(comment_id)
        _emit((OP_RELEASE, removed))

    return True


def _mount_fragment(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> None:
    """Mount a fragment using comment markers, children directly in the parent."""
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
        mount(child, parent_id, end_id)


# ---------------------------------------------------------------------------
# Reactive hole (``_dynamic``) mounting
# ---------------------------------------------------------------------------


def _coerce_dynamic_result(value: Any) -> VNode:
    """Convert the result of a reactive hole getter into a single VNode."""
    if isinstance(value, VNode):
        return value
    if isinstance(value, list):
        from .vnode import Fragment

        return Fragment(*value)
    if value is None:
        return to_text_vnode("")
    return to_text_vnode(value)


def _hole_updater(vnode: VNode, parent_id: int, end_id: int, getter: Any) -> Any:
    """Build the effect body that re-evaluates a hole and patches its region."""

    def update() -> None:
        try:
            result = getter()
        except Exception as exc:
            if not _dispatch_to_error_boundary(exc):
                log_error(f"Reactive hole getter raised: {exc}", exc)
            return
        new_node = _coerce_dynamic_result(result)
        prev = vnode.subtree
        vnode.subtree = new_node
        if prev is None:
            try:
                mount(new_node, parent_id, end_id)
            except Exception as exc:
                if not _dispatch_to_error_boundary(exc):
                    log_error(f"Reactive hole mount failed: {exc}", exc)
        else:
            try:
                patch(prev, new_node, parent_id)
            except Exception as exc:
                if not _dispatch_to_error_boundary(exc):
                    log_error(f"Reactive hole patch failed: {exc}", exc)

    return update


def _mount_dynamic(
    vnode: VNode,
    parent_id: int,
    anchor_id: Optional[int] = None,
    end_id: Optional[int] = None,
) -> None:
    """Mount a reactive hole: an effect re-evaluates *getter* and patches its region.

    When `end_id` is provided (the template fast path), the existing
    placeholder comment is adopted as the hole's end anchor instead of
    creating and inserting a new one.
    """
    if end_id is None:
        end_id = _alloc_id()
        _emit((OP_CREATE_COMMENT, end_id))
        _emit((OP_INSERT, parent_id, end_id, anchor_id))
    vnode.el = end_id
    vnode._frag_end = end_id

    getter = vnode.props.get("getter")
    if not callable(getter):
        return

    vnode.render_effect = effect(_hole_updater(vnode, parent_id, end_id, getter))


def _patch_dynamic(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch one reactive hole against another.

    If the getter object is the same instance, no work is needed; the
    existing effect already tracks the same dependencies and will fire
    on its own.  If the getter changed (e.g., a parent re-rendered with
    a new lambda), dispose the old effect and install a new one,
    re-using the existing end-anchor and any currently-mounted subtree.
    """
    new.el = old.el
    new._frag_end = old._frag_end
    new.subtree = old.subtree

    old_getter = old.props.get("getter")
    new_getter = new.props.get("getter")

    if old_getter is new_getter:
        new.render_effect = old.render_effect
        return

    if old.render_effect is not None:
        try:
            old.render_effect.dispose()
        except Exception as exc:  # pragma: no cover - defensive
            log_error(f"Failed disposing old reactive hole effect: {exc}", exc)
    old.render_effect = None

    if not callable(new_getter):
        return

    assert new._frag_end is not None
    new.render_effect = effect(_hole_updater(new, parent_id, new._frag_end, new_getter))


# ---------------------------------------------------------------------------
# Component mounting (run-once model)
# ---------------------------------------------------------------------------


def _mount_component(vnode: VNode, parent_id: int, anchor_id: Optional[int] = None) -> None:
    """Mount a function component using the run-once + reactive-holes model.

    The component body is invoked exactly once.  The return value is
    coerced to a VNode subtree.  As a convenience, a callable return
    is wrapped in a single-root reactive hole (the same primitive
    :func:`wybthon.dynamic` produces), so HOCs that build a render
    callback continue to work.  Idiomatic components return a
    :class:`VNode` directly and use :func:`wybthon.dynamic` where they
    need reactive subtrees.
    """
    import wybthon.reactivity as _rx

    comp_fn = vnode.tag
    assert callable(comp_fn)

    ctx = _ComponentContext()
    ctx._props = vnode.props
    ctx._vnode = vnode
    vnode.component_ctx = ctx

    comp_defaults = getattr(comp_fn, "_wyb_defaults", {})
    ctx._reactive_props = ReactiveProps(vnode.props, comp_defaults)

    parent_ctx = _get_component_ctx()
    if parent_ctx is not None:
        parent_ctx._add_child(ctx)
    elif _rx._current_owner is not None:
        _rx._current_owner._add_child(ctx)

    is_provider = getattr(comp_fn, "_wyb_provider", False)

    if is_provider:
        ctx_obj = ctx._props.get("context")
        value = ctx._props.get("value")
        if ctx_obj is not None:
            # Store a Signal so descendants get fine-grained reactive
            # updates when the provider's ``value`` prop changes.
            from .vnode import is_getter as _is_getter

            initial_value = value() if callable(value) and _is_getter(value) else value
            value_sig = _rx.Signal(initial_value)
            ctx._set_context(ctx_obj.id, value_sig)
            # Remember the signal so the patch path can update it in
            # place without rebuilding child contexts.
            if ctx._provider_value_signals is None:
                ctx._provider_value_signals = {}
            ctx._provider_value_signals[ctx_obj.id] = value_sig

            # If ``value`` is itself a getter, set up an effect owned by
            # this Provider's context so the value signal stays in sync
            # with the upstream source, without re-mounting subtrees.
            if callable(value) and _is_getter(value):
                value_getter = value
                prev_owner = _rx._current_owner
                _rx._current_owner = ctx
                try:

                    def _track_value() -> None:
                        value_sig.set(value_getter())

                    _rx.create_effect(_track_value)
                finally:
                    _rx._current_owner = prev_owner

    prev_owner = _rx._current_owner
    _rx._current_owner = ctx
    try:
        try:
            result = comp_fn(ctx._reactive_props)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                result = to_text_vnode("")
            else:
                log_error(f"Render failed in function component {component_name(comp_fn)}", exc)
                raise
    finally:
        _rx._current_owner = prev_owner

    sub_tree = _normalize_component_result(result, ctx, comp_fn)

    vnode.subtree = sub_tree

    prev_owner = _rx._current_owner
    _rx._current_owner = ctx
    try:
        try:
            mount(sub_tree, parent_id, anchor_id)
            vnode.el = _first_dom_id(sub_tree)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                placeholder = to_text_vnode("")
                vnode.subtree = placeholder
                mount(placeholder, parent_id, anchor_id)
                vnode.el = placeholder.el
            else:
                raise
    finally:
        _rx._current_owner = prev_owner

    ctx._run_mount_callbacks()


def _normalize_component_result(result: Any, ctx: _ComponentContext, comp_fn: Any = None) -> VNode:
    """Coerce a component's return value to a VNode subtree.

    Components should return a ``VNode``; use :func:`wybthon.dynamic`
    for reactive subtrees.  As a courtesy, a callable return is
    wrapped in a single-root reactive hole so it still renders
    (useful for HOCs that build a render callback).
    """
    if isinstance(result, VNode):
        return result
    if callable(result):
        return dynamic(result)
    return to_text_vnode(result)


def _patch_component(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch a function component: update props on the existing context.

    Components don't re-render on patch; the existing reactive props
    proxy is updated in place, and any reactive holes inside the
    subtree that read those props will re-fire automatically.
    """
    ctx = old.component_ctx
    is_provider = getattr(new.tag, "_wyb_provider", False)

    if ctx is None:
        _replace(old, new, parent_id)
        return

    ctx._props = new.props
    if ctx._reactive_props is not None:
        ctx._reactive_props._update(new.props)

    if is_provider:
        ctx_obj = new.props.get("context")
        new_value = new.props.get("value")
        if ctx_obj is not None:
            from .vnode import is_getter as _is_getter

            resolved = new_value() if callable(new_value) and _is_getter(new_value) else new_value
            existing_signals = ctx._provider_value_signals
            if existing_signals is not None and ctx_obj.id in existing_signals:
                existing_signals[ctx_obj.id].set(resolved)
            else:
                from .reactivity import Signal as _Signal

                value_sig = _Signal(resolved)
                ctx._set_context(ctx_obj.id, value_sig)
                if ctx._provider_value_signals is None:
                    ctx._provider_value_signals = {}
                ctx._provider_value_signals[ctx_obj.id] = value_sig

    ctx._vnode = new

    new.component_ctx = ctx
    new.render_effect = old.render_effect
    new.subtree = old.subtree
    new.el = old.el


# ---------------------------------------------------------------------------
# Unmount
# ---------------------------------------------------------------------------


def unmount(vnode: VNode) -> None:
    """Unmount `vnode`, disposing its effects, ownership scope, and DOM.

    Calls cleanup on the owning component context (if any), removes
    delegated event handlers, runs `on_cleanup` callbacks, and removes
    the subtree's DOM. The removal itself is a handful of ops (one
    `REMOVE` per top-level node plus one `RELEASE` for the whole
    subtree), applied in a single commit.

    Args:
        vnode: The VNode to tear down. Safe to call on already-unmounted
            nodes (becomes a no-op).
    """
    _unmount(vnode)
    kernel.commit()


def _unmount(vnode: VNode) -> None:
    """Internal unmount: emits ops but leaves committing to the caller."""
    top_ids = _dom_node_ids(vnode)
    for nid in top_ids:
        _emit((OP_REMOVE, nid))
    released: List[int] = []
    _dispose_tree(vnode, released)
    if released:
        _emit((OP_RELEASE, released))


def _dispose_tree(vnode: VNode, released: List[int]) -> None:
    """Dispose scopes/effects/handlers recursively, collecting node ids to release."""
    tag = vnode.tag

    if tag == "_dynamic":
        if vnode.render_effect is not None:
            try:
                vnode.render_effect.dispose()
            except Exception as exc:  # pragma: no cover - defensive
                log_error(f"Failed disposing reactive hole effect: {exc}", exc)
            vnode.render_effect = None
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree, released)
            vnode.subtree = None
        if vnode.el is not None:
            released.append(vnode.el)
            vnode.el = None
        return

    if callable(tag):
        if vnode.component_ctx is not None:
            try:
                vnode.component_ctx.dispose()
            except Exception as e:
                log_error(f"Component context disposal failed in {component_name(tag)}", e)
        elif vnode.render_effect is not None:
            try:
                vnode.render_effect.dispose()
            except Exception as e:
                log_error(f"Effect disposal failed in {component_name(tag)}", e)
        if vnode.subtree is not None:
            _dispose_tree(vnode.subtree, released)
        vnode.el = None
        return

    if tag == "_fragment":
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

    # Element or text node.
    if vnode.el is None:
        return
    detach_ref(vnode.props)
    remove_handlers_for(vnode.el)
    if vnode.render_effect is not None:
        try:
            vnode.render_effect.dispose()
        except Exception as e:
            log_error(f"Effect disposal failed in {component_name(tag)}", e)
    for child in vnode.children:
        if isinstance(child, VNode):
            _dispose_tree(child, released)
    released.append(vnode.el)
    vnode.el = None


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


def _same_type(a: VNode, b: VNode) -> bool:
    """Return True when both VNodes represent the same tag/component type."""
    return a.tag == b.tag


def _replace(old: VNode, new: VNode, parent_id: int) -> None:
    """Unmount `old` and mount `new` at the same DOM position.

    A temporary comment marker holds the position, preserving the
    lifecycle order (old cleanups run before the new tree mounts).
    """
    anchor = _first_dom_id(old)
    if anchor is None:
        _unmount(old)
        mount(new, parent_id)
        return
    marker = _alloc_id()
    _emit((OP_CREATE_COMMENT, marker))
    _emit((OP_INSERT, parent_id, marker, anchor))
    _unmount(old)
    mount(new, parent_id, marker)
    _emit((OP_REMOVE, marker))
    _emit((OP_RELEASE, [marker]))


def patch(old: Optional[VNode], new: VNode, parent_id: int) -> None:
    """Diff `old` against `new` and emit minimal DOM ops under `parent_id`.

    Identical VNode instances (`old is new`, e.g. cached `For` rows) are
    skipped entirely. Same-type VNodes are patched in place (props and
    children diffed); different types are unmounted and remounted at the
    same position.

    Args:
        old: The previously-rendered VNode, or `None` for the initial
            mount.
        new: The new VNode to render.
        parent_id: Kernel id of the node that directly contains this
            VNode's DOM.
    """
    if old is None:
        mount(new, parent_id)
        return

    if old is new:
        return

    if not _same_type(old, new):
        _replace(old, new, parent_id)
        return

    if old.tag == "_text" and new.tag == "_text":
        new.el = old.el
        if new.el is not None:
            old_text = old.props.get("nodeValue", "")
            new_text = new.props.get("nodeValue", "")
            if old_text != new_text:
                _emit((OP_SET_TEXT, new.el, new_text))
        return

    if old.tag == "_dynamic" and new.tag == "_dynamic":
        _patch_dynamic(old, new, parent_id)
        return

    if old.tag == "_fragment" and new.tag == "_fragment":
        _patch_fragment(old, new, parent_id)
        return

    assert old.el is not None
    new.el = old.el

    if callable(new.tag):
        _patch_component(old, new, parent_id)
        return

    apply_props(new.el, old.props, new.props)
    attach_ref(new.props, new.el)

    # `old` was mounted (or patched) before, so its children are
    # already normalized; only the new side needs normalization.
    new_children = normalize_children(new.children)
    new.children = new_children
    _reconcile_children(old.children, new_children, new.el, None)


def _patch_fragment(old: VNode, new: VNode, parent_id: int) -> None:
    """Patch two fragment VNodes in place."""
    new.el = old.el
    new._frag_end = old._frag_end

    new_children = normalize_children(new.children)
    new.children = new_children

    _reconcile_children(old.children, new_children, parent_id, new._frag_end)


def _reconcile_children(
    old_children: List[VNode],
    new_children: List[VNode],
    parent_id: int,
    end_marker: Optional[int],
) -> None:
    """Diff two child lists and emit mounts, patches, moves, and removals.

    Matching runs in three passes, all `O(n)`:

    1. **Identity**: the same VNode instance in both lists (cached `For`
       rows) is reused with no patching at all.
    2. **Key**: children with equal `key` values are patched in place.
    3. **Type**: remaining unkeyed children are matched against unused
       old children of the same tag in document order.

    DOM moves are minimized with a longest-increasing-subsequence pass:
    only children outside the LIS are repositioned.

    Args:
        old_children: Normalized previous children.
        new_children: Normalized next children.
        parent_id: Id of the node that directly contains the children's
            DOM.
        end_marker: Exclusive end anchor id (a fragment's end comment),
            or `None` when children occupy the whole parent.
    """
    n_old = len(old_children)
    n = len(new_children)
    used_old: List[bool] = [False] * n_old
    sources: List[int] = [-1] * n
    needs_patch: List[bool] = [False] * n

    old_ids: Dict[int, int] = {}
    old_keys: Dict[Union[str, int], int] = {}
    for j, oc in enumerate(old_children):
        old_ids[id(oc)] = j
        if oc.key is not None:
            old_keys[oc.key] = j

    # Pass 1 + 2: identity and key matches (reserved before type matching
    # so an unkeyed scan can't steal a child that matches later by
    # identity or key).
    unmatched: List[int] = []
    for i, nc in enumerate(new_children):
        j = old_ids.get(id(nc))
        if j is not None and not used_old[j]:
            used_old[j] = True
            sources[i] = j
            continue
        if nc.key is not None:
            j = old_keys.get(nc.key)
            if j is not None and not used_old[j]:
                used_old[j] = True
                sources[i] = j
                needs_patch[i] = True
                continue
        unmatched.append(i)

    # Pass 3: unkeyed children match unused old children of the same tag
    # in order. Per-tag index queues keep this linear.
    if unmatched:
        type_queues: Dict[Any, List[int]] = {}
        type_pos: Dict[Any, int] = {}
        for j, oc in enumerate(old_children):
            if not used_old[j] and oc.key is None:
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
            patch(old_children[sources[i]], new_children[i], parent_id)

    # Longest increasing subsequence over matched source indices; children
    # inside the LIS keep their DOM position.
    tails: List[int] = []
    tails_idx: List[int] = []
    prev_idx: List[int] = [-1] * n
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

    lis_set: Set[int] = set()
    k = tails_idx[-1] if tails_idx else -1
    while k != -1:
        lis_set.add(k)
        k = prev_idx[k]

    next_anchor = end_marker
    for i in range(n - 1, -1, -1):
        new_child = new_children[i]
        s = sources[i]
        if s == -1:
            try:
                mount(new_child, parent_id, next_anchor)
                first = _first_dom_id(new_child)
                if first is not None:
                    next_anchor = first
            except Exception as e:
                if not _dispatch_to_error_boundary(e):
                    log_error(f"Failed to mount child at index {i}", e)
        else:
            first_dom = _first_dom_id(new_child)
            if first_dom is not None:
                if i not in lis_set:
                    for nid in _dom_node_ids(new_child):
                        _emit((OP_INSERT, parent_id, nid, next_anchor))
                next_anchor = first_dom

    for j, oc in enumerate(old_children):
        if not used_old[j]:
            _unmount(oc)

"""Reconciliation engine: mounting, patching, and unmounting VNode trees.

This module is the bridge between the virtual DOM and real DOM. It
implements the diffing algorithm that translates VNode trees into
attribute writes, child insertions, and node removals.

Mental model:

- **Components run once.** A function component is invoked a single time
  during mount. Its returned VNode tree is mounted directly. Reactive
  updates flow through *reactive holes* embedded in that tree — not by
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
- [`mount`][wybthon.reconciler.mount]: create DOM for a new VNode.
- [`unmount`][wybthon.reconciler.unmount]: tear down a VNode and its DOM.
- [`patch`][wybthon.reconciler.patch]: diff two VNodes and apply DOM
  changes.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Dict, List, Optional, Set, Union, cast

from js import document

from ._warnings import component_name, log_error
from .dom import Element
from .events import remove_all_for
from .props import apply_initial_props, apply_props, attach_ref, detach_ref
from .reactivity import (
    ReactiveProps,
    _ComponentContext,
    _get_component_ctx,
    effect,
)
from .vnode import ChildType, VNode, dynamic, normalize_children, to_text_vnode

__all__ = ["render", "mount", "unmount", "patch"]

_container_registry: Dict[int, VNode] = {}


def render(vnode: VNode, container: Union[Element, str]) -> Element:
    """Render a VNode tree into a container element.

    Subsequent calls with the same `container` *patch* the existing tree
    in place — only the differences are applied. Pass `None` (via the
    internal API) to unmount.

    Args:
        vnode: The root VNode to render.
        container: An [`Element`][wybthon.Element] wrapper or a CSS selector
            string identifying an existing DOM node.

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
    else:
        container_el = container
    prev = _container_registry.get(id(container_el.element))
    patch(prev, vnode, container_el)
    _container_registry[id(container_el.element)] = vnode
    return container_el


# ---------------------------------------------------------------------------
# DOM creation
# ---------------------------------------------------------------------------


def _create_dom(vnode: VNode) -> Element:
    """Create a real DOM element for an element/text VNode and its subtree."""
    if vnode.tag == "_text":
        node = document.createTextNode(vnode.props.get("nodeValue", ""))
        el = Element(node=node)
        vnode.el = el
        return el

    assert vnode.tag is not None, "VNode.tag must not be None for element nodes"
    assert isinstance(vnode.tag, str), "_create_dom only handles element or text nodes"
    el = Element(vnode.tag)
    apply_initial_props(el, vnode.props, vnode)
    norm_children = normalize_children(vnode.children)
    vnode.children = cast(List[ChildType], norm_children)
    for child in norm_children:
        mount(child, el)
    vnode.el = el
    attach_ref(vnode.props, el)
    return el


# ---------------------------------------------------------------------------
# Sibling / DOM-position helpers
# ---------------------------------------------------------------------------


def _get_next_sibling(vnode: VNode) -> Any:
    """Get the DOM node immediately after all of this vnode's DOM nodes."""
    if vnode.tag == "_dynamic":
        if vnode._frag_end is not None:
            return vnode._frag_end.element.nextSibling
        if vnode.subtree is not None:
            return _get_next_sibling(vnode.subtree)
        return None
    if vnode.subtree is not None:
        return _get_next_sibling(vnode.subtree)
    if vnode.tag == "_fragment" and vnode._frag_end is not None:
        return vnode._frag_end.element.nextSibling
    if vnode.el is not None:
        return vnode.el.element.nextSibling
    return None


def _get_first_dom(vnode: VNode) -> Any:
    """Get the first DOM node belonging to this vnode."""
    if vnode.tag == "_dynamic":
        if vnode.subtree is not None:
            first = _get_first_dom(vnode.subtree)
            if first is not None:
                return first
        if vnode.el is not None:
            return vnode.el.element
        return None
    if vnode.subtree is not None:
        return _get_first_dom(vnode.subtree)
    if vnode.el is not None:
        return vnode.el.element
    return None


def _get_dom_nodes(vnode: VNode) -> List[Any]:
    """Get all top-level DOM nodes belonging to this vnode."""
    if vnode.tag == "_dynamic":
        nodes: List[Any] = []
        if vnode.subtree is not None:
            nodes.extend(_get_dom_nodes(vnode.subtree))
        if vnode.el is not None:
            nodes.append(vnode.el.element)
        return nodes
    if vnode.subtree is not None:
        return _get_dom_nodes(vnode.subtree)
    if vnode.tag == "_fragment":
        frag_nodes: List[Any] = []
        if vnode.el is not None:
            frag_nodes.append(vnode.el.element)
        for child in normalize_children(vnode.children):
            frag_nodes.extend(_get_dom_nodes(child))
        if vnode._frag_end is not None:
            frag_nodes.append(vnode._frag_end.element)
        return frag_nodes
    if vnode.el is not None:
        return [vnode.el.element]
    return []


# ---------------------------------------------------------------------------
# Fragment mounting
# ---------------------------------------------------------------------------


def _mount_fragment(vnode: VNode, container: Element, anchor: Any = None) -> Element:
    """Mount a fragment using comment markers, children directly in container."""
    start_comment = document.createComment("")
    start_el = Element(node=start_comment)
    vnode.el = start_el

    if anchor is None:
        container.element.appendChild(start_comment)
    else:
        container.element.insertBefore(start_comment, anchor)

    end_comment = document.createComment("")
    end_el = Element(node=end_comment)
    vnode._frag_end = end_el

    if anchor is None:
        container.element.appendChild(end_comment)
    else:
        container.element.insertBefore(end_comment, anchor)

    norm_children = normalize_children(vnode.children)
    vnode.children = cast(List[ChildType], norm_children)
    for child in norm_children:
        mount(child, container, end_comment)

    return start_el


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


def _mount_dynamic(vnode: VNode, container: Element, anchor: Any = None) -> Element:
    """Mount a reactive hole: an effect re-evaluates *getter* and patches the DOM region."""
    end_comment = document.createComment("")
    end_el = Element(node=end_comment)
    if anchor is None:
        container.element.appendChild(end_comment)
    else:
        container.element.insertBefore(end_comment, anchor)
    vnode.el = end_el
    vnode._frag_end = end_el

    getter = vnode.props.get("getter")
    if not callable(getter):
        return end_el

    def update() -> None:
        try:
            result = getter()
        except Exception as exc:
            log_error(f"Reactive hole getter raised: {exc}", exc)
            return
        new_node = _coerce_dynamic_result(result)
        prev = vnode.subtree
        vnode.subtree = new_node
        if prev is None:
            try:
                mount(new_node, container, end_comment)
            except Exception as exc:
                log_error(f"Reactive hole mount failed: {exc}", exc)
        else:
            try:
                patch(prev, new_node, container)
            except Exception as exc:
                log_error(f"Reactive hole patch failed: {exc}", exc)

    vnode.render_effect = effect(update)
    return end_el


def _patch_dynamic(old: VNode, new: VNode, container: Element) -> None:
    """Patch one reactive hole against another.

    If the getter object is the same instance, no work is needed -- the
    existing effect already tracks the same dependencies and will fire
    on its own.  If the getter changed (e.g. a parent re-rendered with
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

    end_comment = new._frag_end.element if new._frag_end is not None else None

    if not callable(new_getter):
        return

    def update() -> None:
        try:
            result = new_getter()
        except Exception as exc:
            log_error(f"Reactive hole getter raised: {exc}", exc)
            return
        new_node = _coerce_dynamic_result(result)
        prev = new.subtree
        new.subtree = new_node
        if prev is None:
            try:
                mount(new_node, container, end_comment)
            except Exception as exc:
                log_error(f"Reactive hole mount failed: {exc}", exc)
        else:
            try:
                patch(prev, new_node, container)
            except Exception as exc:
                log_error(f"Reactive hole patch failed: {exc}", exc)

    new.render_effect = effect(update)


def _unmount_dynamic(vnode: VNode) -> None:
    """Tear down a reactive hole's effect, subtree, and end-anchor."""
    if vnode.render_effect is not None:
        try:
            vnode.render_effect.dispose()
        except Exception as exc:  # pragma: no cover - defensive
            log_error(f"Failed disposing reactive hole effect: {exc}", exc)
        vnode.render_effect = None
    if vnode.subtree is not None:
        try:
            unmount(vnode.subtree)
        except Exception as exc:  # pragma: no cover - defensive
            log_error(f"Failed unmounting reactive hole subtree: {exc}", exc)
        vnode.subtree = None
    if vnode.el is not None and vnode.el.element.parentNode is not None:
        try:
            vnode.el.element.parentNode.removeChild(vnode.el.element)
        except Exception:
            pass
    vnode.el = None


# ---------------------------------------------------------------------------
# Top-level mount
# ---------------------------------------------------------------------------


def mount(vnode: Union[VNode, str], container: Element, anchor: Any = None) -> Element:
    """Mount a VNode (or string) into `container`, returning its DOM element.

    Args:
        vnode: The VNode to mount. Strings are coerced to text VNodes.
        container: The parent element wrapper.
        anchor: Optional sibling DOM node to insert before. When `None`,
            the new element is appended to `container`.

    Returns:
        The mounted [`Element`][wybthon.Element] wrapper.
    """
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)

    if vnode.tag == "_dynamic":
        return _mount_dynamic(vnode, container, anchor)

    if vnode.tag == "_fragment":
        return _mount_fragment(vnode, container, anchor)

    if callable(vnode.tag):
        return _mount_component(vnode, container, anchor)

    el = _create_dom(vnode)
    if anchor is None:
        container.element.appendChild(el.element)
    else:
        container.element.insertBefore(el.element, anchor)
    return el


# ---------------------------------------------------------------------------
# Component mounting (run-once model)
# ---------------------------------------------------------------------------


def _mount_component(vnode: VNode, container: Element, anchor: Any = None) -> Element:
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
            # with the upstream source — without re-mounting subtrees.
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
            if ctx._error_handler is not None:
                ctx._error_handler(exc)
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
            mounted_el = mount(sub_tree, container, anchor)
            vnode.el = mounted_el
        except Exception as exc:
            if ctx._error_handler is not None:
                ctx._error_handler(exc)
                placeholder = to_text_vnode("")
                vnode.subtree = placeholder
                vnode.el = mount(placeholder, container, anchor)
            else:
                raise
    finally:
        _rx._current_owner = prev_owner

    ctx._run_mount_callbacks()
    assert vnode.el is not None
    return vnode.el


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


def _patch_component(old: VNode, new: VNode, container: Element) -> None:
    """Patch a function component: update props on the existing context.

    Components do not re-render on patch -- the existing reactive props
    proxy is updated in place, and any reactive holes inside the
    subtree that read those props will re-fire automatically.
    """
    ctx = old.component_ctx
    is_provider = getattr(new.tag, "_wyb_provider", False)

    if getattr(new.tag, "_wyb_memo", False):
        compare_fn = getattr(new.tag, "_wyb_memo_compare", None)
        old_props = ctx._props if ctx is not None else {}
        if compare_fn is not None and compare_fn(old_props, new.props):
            new.component_ctx = ctx
            new.render_effect = old.render_effect
            new.subtree = old.subtree
            new.el = old.el
            if ctx is not None:
                ctx._vnode = new
            return

    if ctx is None:
        anchor = _get_next_sibling(old)
        unmount(old)
        mount(new, container, anchor)
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


def _unmount_fragment(vnode: VNode) -> None:
    """Unmount a fragment: dispose children, remove comment markers."""
    for child in normalize_children(vnode.children):
        if isinstance(child, VNode):
            unmount(child)
    if vnode.el is not None and vnode.el.element.parentNode is not None:
        vnode.el.element.parentNode.removeChild(vnode.el.element)
    if vnode._frag_end is not None and vnode._frag_end.element.parentNode is not None:
        vnode._frag_end.element.parentNode.removeChild(vnode._frag_end.element)


def unmount(vnode: VNode) -> None:
    """Unmount `vnode`, disposing its effects, ownership scope, and DOM.

    Calls cleanup on the owning component context (if any), removes
    delegated event handlers, runs `on_cleanup` callbacks, and detaches
    the underlying DOM node from its parent.

    Args:
        vnode: The VNode to tear down. Safe to call on already-unmounted
            nodes (becomes a no-op).
    """
    if vnode.tag == "_dynamic":
        _unmount_dynamic(vnode)
        return

    if vnode.el is None:
        return

    if vnode.tag == "_fragment":
        _unmount_fragment(vnode)
        return

    detach_ref(vnode.props)
    try:
        remove_all_for(vnode.el)
        vnode.el.cleanup()
    except Exception as e:
        log_error(f"Cleanup failed for {component_name(vnode.tag)}", e)

    if vnode.component_ctx is not None:
        try:
            vnode.component_ctx.dispose()
        except Exception as e:
            log_error(f"Component context disposal failed in {component_name(vnode.tag)}", e)
    elif vnode.render_effect is not None:
        try:
            vnode.render_effect.dispose()
        except Exception as e:
            log_error(f"Effect disposal failed in {component_name(vnode.tag)}", e)

    if vnode.subtree is not None:
        unmount(vnode.subtree)
    for child in normalize_children(vnode.children):
        if isinstance(child, VNode):
            unmount(child)
    if vnode.el.element.parentNode is not None:
        vnode.el.element.parentNode.removeChild(vnode.el.element)


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


def _same_type(a: VNode, b: VNode) -> bool:
    """Return True when both VNodes represent the same tag/component type."""
    return a.tag == b.tag


def patch(old: Optional[VNode], new: VNode, container: Element) -> None:
    """Diff `old` against `new` and apply minimal DOM changes inside `container`.

    Same-type VNodes are patched in place (props and children diffed);
    different types are unmounted and remounted at the same anchor.

    Args:
        old: The previously-rendered VNode, or `None` for the initial
            mount.
        new: The new VNode to render.
        container: The parent element wrapper.
    """
    if old is None:
        mount(new, container)
        return

    if not _same_type(old, new):
        anchor = _get_next_sibling(old)
        unmount(old)
        mount(new, container, anchor)
        return

    if old.tag == "_text" and new.tag == "_text":
        new.el = old.el
        if new.el is not None:
            old_text = old.props.get("nodeValue", "")
            new_text = new.props.get("nodeValue", "")
            if old_text != new_text:
                new.el.element.nodeValue = new_text
        return

    if old.tag == "_dynamic" and new.tag == "_dynamic":
        _patch_dynamic(old, new, container)
        return

    if old.tag == "_fragment" and new.tag == "_fragment":
        _patch_fragment(old, new, container)
        return

    assert old.el is not None
    new.el = old.el

    if callable(new.tag):
        _patch_component(old, new, container)
        return

    apply_props(new.el, old.props, new.props)
    attach_ref(new.props, new.el)
    _patch_children(old, new)


def _patch_fragment(old: VNode, new: VNode, container: Element) -> None:
    """Patch two fragment VNodes in place."""
    new.el = old.el
    new._frag_end = old._frag_end

    old_children = normalize_children(old.children)
    new_children = normalize_children(new.children)
    new.children = cast(List[ChildType], new_children)

    end_marker = new._frag_end.element if new._frag_end is not None else None

    old_key_to_index: Dict[Union[str, int], int] = {}
    for i, ch in enumerate(old_children):
        if ch.key is not None:
            old_key_to_index[ch.key] = i

    used_old: List[bool] = [False] * len(old_children)
    sources: List[int] = [-1] * len(new_children)

    for i, new_child in enumerate(new_children):
        if new_child.key is not None and new_child.key in old_key_to_index:
            idx = old_key_to_index[new_child.key]
            sources[i] = idx
            used_old[idx] = True
            patch(old_children[idx], new_child, container)
        else:
            for j, oc in enumerate(old_children):
                if used_old[j]:
                    continue
                if oc.key is None and _same_type(oc, new_child):
                    sources[i] = j
                    used_old[j] = True
                    patch(oc, new_child, container)
                    break

    n = len(new_children)
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

    next_anchor_node = end_marker
    for i in range(n - 1, -1, -1):
        new_child = new_children[i]
        s = sources[i]
        if s == -1:
            try:
                mount(new_child, container, next_anchor_node)
                first = _get_first_dom(new_child)
                if first is not None:
                    next_anchor_node = first
            except Exception as e:
                log_error(f"Failed to mount fragment child at index {i}", e)
        else:
            first_dom = _get_first_dom(new_child)
            if first_dom is not None:
                if i not in lis_set:
                    for dom_node in _get_dom_nodes(new_child):
                        try:
                            container.element.insertBefore(dom_node, next_anchor_node)
                        except Exception as e:
                            log_error(f"Failed to reorder fragment child at index {i}", e)
                next_anchor_node = first_dom

    for j, oc in enumerate(old_children):
        if not used_old[j]:
            unmount(oc)


def _patch_children(old: VNode, new: VNode) -> None:
    """Diff and apply changes for a node's children using key-aware reordering."""
    parent = new.el
    assert parent is not None

    old_children = normalize_children(old.children)
    new_children = normalize_children(new.children)
    new.children = cast(List[ChildType], new_children)

    old_key_to_index: Dict[Union[str, int], int] = {}
    for i, ch in enumerate(old_children):
        if ch.key is not None:
            old_key_to_index[ch.key] = i

    used_old: List[bool] = [False] * len(old_children)
    sources: List[int] = [-1] * len(new_children)

    for i, new_child in enumerate(new_children):
        if new_child.key is not None and new_child.key in old_key_to_index:
            idx = old_key_to_index[new_child.key]
            sources[i] = idx
            used_old[idx] = True
            patch(old_children[idx], new_child, parent)
        else:
            for j, oc in enumerate(old_children):
                if used_old[j]:
                    continue
                if oc.key is None and _same_type(oc, new_child):
                    sources[i] = j
                    used_old[j] = True
                    patch(oc, new_child, parent)
                    break

    n = len(new_children)
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

    next_anchor_node = None
    for i in range(n - 1, -1, -1):
        new_child = new_children[i]
        s = sources[i]
        if s == -1:
            try:
                mount(new_child, parent, next_anchor_node)
                first = _get_first_dom(new_child)
                if first is not None:
                    next_anchor_node = first
            except Exception as e:
                log_error(f"Failed to mount child at index {i}", e)
        else:
            first_dom = _get_first_dom(new_child)
            if first_dom is not None:
                if i not in lis_set:
                    for dom_node in _get_dom_nodes(new_child):
                        try:
                            parent.element.insertBefore(dom_node, next_anchor_node)
                        except Exception as e:
                            log_error(f"Failed to reorder child at index {i}", e)
                next_anchor_node = first_dom

    for j, oc in enumerate(old_children):
        if not used_old[j]:
            unmount(oc)

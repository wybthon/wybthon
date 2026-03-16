"""Core reconciliation engine: mounting, patching, and unmounting VNode trees.

This module implements the VDOM diffing algorithm that translates virtual node
trees into real DOM mutations.  All components are function components using
the signals-first reactive model.

Key functions:
  - ``render(vnode, container)`` -- top-level entry point
  - ``mount(vnode, container, anchor)`` -- create DOM for a new VNode
  - ``unmount(vnode)`` -- tear down a VNode and its DOM
  - ``patch(old, new, container)`` -- diff two VNodes and apply DOM changes
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Dict, List, Optional, Set, Union, cast

from js import document

from ._warnings import component_name, log_error
from .context import pop_provider_value, push_provider_value
from .dom import Element
from .events import remove_all_for
from .props import apply_props, attach_ref, detach_ref
from .reactivity import (
    _ComponentContext,
    _pop_component_ctx,
    _push_component_ctx,
    effect,
)
from .vnode import ChildType, VNode, normalize_children, to_text_vnode

__all__ = ["render", "mount", "unmount", "patch"]

_container_registry: Dict[int, VNode] = {}


def render(vnode: VNode, container: Union[Element, str]) -> Element:
    """Render a VNode tree into a container ``Element`` or CSS selector."""
    if isinstance(container, str):
        container_el = Element(container, existing=True)
    else:
        container_el = container
    prev = _container_registry.get(id(container_el.element))
    patch(prev, vnode, container_el)
    _container_registry[id(container_el.element)] = vnode
    return container_el


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
    apply_props(el, {}, vnode.props)
    norm_children = normalize_children(vnode.children)
    vnode.children = cast(List[ChildType], norm_children)
    for child in norm_children:
        mount(child, el)
    vnode.el = el
    attach_ref(vnode.props, el)
    return el


def mount(vnode: Union[VNode, str], container: Element, anchor: Any = None) -> Element:
    """Mount a VNode (or string) into the container, returning its element."""
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)

    if callable(vnode.tag):
        return _mount_component(vnode, container, anchor)

    el = _create_dom(vnode)
    if anchor is None:
        container.element.appendChild(el.element)
    else:
        container.element.insertBefore(el.element, anchor)
    return el


def _mount_component(vnode: VNode, container: Element, anchor: Any) -> Element:
    """Mount a function component using the signals-first model.

    The component function is called once (setup phase).  If it returns a
    *callable*, that callable is treated as the render function and wrapped
    in a reactive ``effect`` so it re-runs when signals change (stateful).
    If it returns a ``VNode`` directly, the component is treated as
    stateless and the entire function is re-called on signal changes.
    """
    comp_fn = vnode.tag
    assert callable(comp_fn)

    ctx = _ComponentContext()
    ctx._props = vnode.props
    ctx._vnode = vnode
    vnode.component_ctx = ctx

    is_provider = getattr(comp_fn, "_wyb_provider", False)
    setup_done: List[bool] = [False]

    def run_component(
        _ctx: _ComponentContext = ctx,
        _comp_fn: Any = comp_fn,
        _container: Element = container,
        _anchor: Any = anchor,
    ) -> None:
        cur_vnode = _ctx._vnode

        if not setup_done[0]:
            # -- first run: setup + initial render --
            _push_component_ctx(_ctx)
            try:
                result = _comp_fn(_ctx._props)
            finally:
                _pop_component_ctx()

            if callable(result) and not isinstance(result, VNode):
                _ctx._render_fn = result
                sub_tree = result()
            else:
                sub_tree = result

            if not isinstance(sub_tree, VNode):
                sub_tree = to_text_vnode(sub_tree)

            cur_vnode.subtree = sub_tree

            if is_provider:
                push_provider_value(_ctx._props.get("context"), _ctx._props.get("value"))

            try:
                mounted_el = mount(sub_tree, _container, _anchor)
                cur_vnode.el = mounted_el
            except Exception as e:
                if is_provider:
                    pop_provider_value()
                if _ctx._error_handler is not None:
                    _ctx._error_handler(e)
                    placeholder = to_text_vnode("")
                    cur_vnode.subtree = placeholder
                    mounted_el = mount(placeholder, _container, _anchor)
                    cur_vnode.el = mounted_el
                else:
                    raise
            else:
                if is_provider:
                    pop_provider_value()

            setup_done[0] = True
        else:
            # -- subsequent runs: re-render (signal change) --
            if _ctx._render_fn is not None:
                sub_tree = _ctx._render_fn()
            else:
                _push_component_ctx(_ctx)
                try:
                    sub_tree = _comp_fn(_ctx._props)
                finally:
                    _pop_component_ctx()

            if not isinstance(sub_tree, VNode):
                sub_tree = to_text_vnode(sub_tree)

            prev_sub = cur_vnode.subtree
            cur_vnode.subtree = sub_tree

            if is_provider:
                push_provider_value(_ctx._props.get("context"), _ctx._props.get("value"))

            try:
                if prev_sub is None:
                    mounted_el = mount(sub_tree, _container, _anchor)
                    cur_vnode.el = mounted_el
                else:
                    patch(prev_sub, sub_tree, _container)
                    cur_vnode.el = sub_tree.el
            except Exception as e:
                if is_provider:
                    pop_provider_value()
                if _ctx._error_handler is not None:
                    _ctx._error_handler(e)
                else:
                    raise
            else:
                if is_provider:
                    pop_provider_value()

    try:
        vnode.render_effect = effect(run_component)
    except Exception as e:
        log_error(f"Render failed in function component {component_name(comp_fn)}", e)
        raise

    ctx._run_mount_callbacks()
    return vnode.el


def unmount(vnode: VNode) -> None:
    """Unmount a VNode and dispose associated resources and effects."""
    if vnode.el is None:
        return
    detach_ref(vnode.props)
    try:
        remove_all_for(vnode.el)
        vnode.el.cleanup()
    except Exception as e:
        log_error(f"Cleanup failed for {component_name(vnode.tag)}", e)

    if vnode.component_ctx is not None:
        try:
            vnode.component_ctx._run_cleanups()
            vnode.component_ctx._dispose_effects()
        except Exception as e:
            log_error(f"Component context cleanup failed in {component_name(vnode.tag)}", e)

    if vnode.render_effect is not None:
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


def _same_type(a: VNode, b: VNode) -> bool:
    """Return True when both VNodes represent the same tag/component type."""
    return a.tag == b.tag


def patch(old: Optional[VNode], new: VNode, container: Element) -> None:
    """Patch ``old`` into ``new`` by mutating DOM as needed within the container."""
    if old is None:
        mount(new, container)
        return

    if not _same_type(old, new):
        anchor = old.el.element.nextSibling if (old.el is not None) else None
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

    assert old.el is not None
    new.el = old.el

    if callable(new.tag):
        _patch_component(old, new, container)
        return

    apply_props(new.el, old.props, new.props)
    attach_ref(new.props, new.el)
    _patch_children(old, new)


def _patch_component(old: VNode, new: VNode, container: Element) -> None:
    """Patch a function component using the signals-first model."""
    ctx = old.component_ctx
    is_provider = getattr(new.tag, "_wyb_provider", False)

    # -- memo check --
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

    if ctx is not None and ctx._render_fn is not None:
        # -- REACTIVE: transfer context, update prop signals --
        ctx._props = new.props
        if ctx._prop_signals:
            defaults = getattr(new.tag, "_wyb_defaults", {})
            for name, sig in ctx._prop_signals.items():
                sig.set(new.props.get(name, defaults.get(name)))
        if ctx._props_signal is not None:
            ctx._props_signal.set(new.props)
        ctx._vnode = new

        new.component_ctx = ctx
        new.render_effect = old.render_effect
        new.subtree = old.subtree
        new.el = old.el
        return

    # -- STATELESS: re-call component with new props --
    if ctx is not None:
        ctx._props = new.props
        ctx._vnode = new
        new.component_ctx = ctx
        new.render_effect = old.render_effect
        new.subtree = old.subtree
        new.el = old.el

        _push_component_ctx(ctx)
        try:
            result = new.tag(new.props)  # type: ignore[operator]
        finally:
            _pop_component_ctx()

        if not isinstance(result, VNode):
            result = to_text_vnode(result)

        prev_sub = old.subtree
        new.subtree = result

        if is_provider:
            push_provider_value(new.props.get("context"), new.props.get("value"))
        try:
            if prev_sub is None:
                mount(result, container)
            else:
                patch(prev_sub, result, container)
            new.el = result.el
        except Exception as e:
            if is_provider:
                pop_provider_value()
            if ctx._error_handler is not None:
                ctx._error_handler(e)
            else:
                raise
        else:
            if is_provider:
                pop_provider_value()
    else:
        result = new.tag(new.props)  # type: ignore[operator]
        if not isinstance(result, VNode):
            result = to_text_vnode(result)
        prev_sub = old.subtree
        new.subtree = result
        if prev_sub is None:
            mount(result, container)
        else:
            patch(prev_sub, result, container)
        new.el = result.el


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
                mounted_el = mount(new_child, parent, next_anchor_node)
                next_anchor_node = mounted_el.element
            except Exception as e:
                log_error(f"Failed to mount child at index {i}", e)
        else:
            new_el = new_child.el
            if new_el is not None:
                if i not in lis_set:
                    try:
                        parent.element.insertBefore(new_el.element, next_anchor_node)
                    except Exception as e:
                        log_error(f"Failed to reorder child at index {i}", e)
                next_anchor_node = new_el.element

    for j, oc in enumerate(old_children):
        if not used_old[j]:
            unmount(oc)

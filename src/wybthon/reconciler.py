"""Core reconciliation engine: mounting, patching, and unmounting VNode trees.

This module implements the VDOM diffing algorithm that translates virtual node
trees into real DOM mutations.  It handles element nodes, text nodes, class
components, and function components (with hooks and reactive effects).

Key functions:
  - ``render(vnode, container)`` -- top-level entry point
  - ``mount(vnode, container, anchor)`` -- create DOM for a new VNode
  - ``unmount(vnode)`` -- tear down a VNode and its DOM
  - ``patch(old, new, container)`` -- diff two VNodes and apply DOM changes
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Callable, Dict, List, Optional, Set, Union, cast

from js import document

from ._warnings import component_name, log_error
from .component import Component
from .context import Provider, pop_provider_value, push_provider_value
from .dom import Element
from .error_boundary import ErrorBoundary
from .events import remove_all_for
from .hooks import _HooksContext, _pop_hooks_ctx, _push_hooks_ctx
from .props import apply_props, attach_ref, detach_ref
from .reactivity import effect
from .vnode import ChildType, Fragment, VNode, normalize_children, to_text_vnode

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
    """Mount a component VNode (class or function) into the container."""
    comp_ctor = vnode.tag
    assert callable(comp_ctor)

    if isinstance(comp_ctor, type) and issubclass(comp_ctor, Component):
        return _mount_class_component(vnode, comp_ctor, container, anchor)
    return _mount_function_component(vnode, comp_ctor, container, anchor)


def _mount_class_component(vnode: VNode, comp_ctor: type, container: Element, anchor: Any) -> Element:
    """Mount a class-based component."""
    instance = comp_ctor(vnode.props)
    vnode.component_instance = instance

    def run_render() -> None:
        try:
            if isinstance(instance, Provider):
                ctx = instance.props.get("context")
                value = instance.props.get("value")
                children = instance.props.get("children", [])
                push_provider_value(ctx, value)
                try:
                    next_sub = Fragment(*children) if isinstance(children, list) else Fragment(children)
                finally:
                    pop_provider_value()
            else:
                next_sub = instance.render()

            if not isinstance(next_sub, VNode):
                next_sub = to_text_vnode(next_sub)
            prev_sub = vnode.subtree
            vnode.subtree = next_sub
            if prev_sub is None:
                mounted_el = mount(next_sub, container, anchor)
                vnode.el = mounted_el
            else:
                patch(prev_sub, next_sub, container)
                vnode.el = next_sub.el
        except Exception as e:
            _handle_render_error(instance, vnode, e, container, anchor)

    vnode.render_effect = effect(run_render)

    if vnode.component_instance is not None:
        try:
            vnode.component_instance.on_mount()
        except Exception as e:
            log_error(f"on_mount() failed in {component_name(comp_ctor)}", e)
    return vnode.el


def _mount_function_component(vnode: VNode, comp_fn: Callable, container: Element, anchor: Any) -> Element:
    """Mount a function component with hooks support."""
    hooks_ctx = _HooksContext()
    hooks_ctx._component_fn = comp_fn
    hooks_ctx._props = vnode.props
    vnode.hooks_ctx = hooks_ctx

    def run_fn_render(
        _vnode: VNode = vnode,
        _container: Element = container,
        _anchor: Any = anchor,
        _hooks_ctx: _HooksContext = hooks_ctx,
    ) -> None:
        _hooks_ctx.cursor = 0
        _hooks_ctx.effect_cursor = 0
        _hooks_ctx.layout_effect_cursor = 0
        _push_hooks_ctx(_hooks_ctx)
        try:
            sub_tree = _hooks_ctx._component_fn(_hooks_ctx._props)
            if not isinstance(sub_tree, VNode):
                sub_tree = to_text_vnode(sub_tree)
            prev_sub = _vnode.subtree
            _vnode.subtree = sub_tree
            if prev_sub is None:
                mounted_el = mount(sub_tree, _container, _anchor)
                _vnode.el = mounted_el
            else:
                patch(prev_sub, sub_tree, _container)
                _vnode.el = sub_tree.el
        except Exception as e:
            log_error(f"Render failed in function component {component_name(comp_fn)}", e)
            raise
        finally:
            _pop_hooks_ctx()
        _hooks_ctx._run_pending_effects()
        _hooks_ctx._is_mounting = False

    vnode.render_effect = effect(run_fn_render)
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

    if vnode.component_instance is not None:
        try:
            vnode.component_instance._run_cleanups()
            vnode.component_instance.on_unmount()
        except Exception as e:
            log_error(f"on_unmount() failed in {component_name(type(vnode.component_instance))}", e)

    if vnode.hooks_ctx is not None:
        try:
            vnode.hooks_ctx._cleanup_all()
        except Exception as e:
            log_error(f"Hook cleanup failed in {component_name(vnode.tag)}", e)

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
    """Patch a component VNode (class or function)."""
    if isinstance(new.tag, type) and issubclass(new.tag, Component):
        _patch_class_component(old, new, container)
    else:
        _patch_function_component(old, new, container)


def _patch_class_component(old: VNode, new: VNode, container: Element) -> None:
    """Patch a class-based component by updating props and re-rendering."""
    instance = old.component_instance or new.tag(new.props)  # type: ignore[operator]
    prev_props = getattr(instance, "props", {})
    instance.props = new.props
    new.component_instance = instance
    try:
        if isinstance(instance, Provider):
            ctx = instance.props.get("context")
            value = instance.props.get("value")
            children = instance.props.get("children", [])
            push_provider_value(ctx, value)
            try:
                next_sub = Fragment(*children) if isinstance(children, list) else Fragment(children)
            finally:
                pop_provider_value()
        else:
            next_sub = instance.render()
            if not isinstance(next_sub, VNode):
                next_sub = to_text_vnode(next_sub)
        prev_sub = old.subtree
        new.subtree = next_sub
        if prev_sub is None:
            mount(next_sub, container)
        else:
            patch(prev_sub, next_sub, container)
        try:
            instance.on_update(prev_props)
        except Exception as e:
            log_error(f"on_update() failed in {component_name(type(instance))}", e)
        return
    except Exception as e:
        _handle_render_error(instance, new, e, container, None, old_subtree=old.subtree)


def _patch_function_component(old: VNode, new: VNode, container: Element) -> None:
    """Patch a function component by re-running with updated props."""
    hooks_ctx = old.hooks_ctx
    if hooks_ctx is not None:
        if getattr(new.tag, "_wyb_memo", False):
            compare_fn = getattr(new.tag, "_wyb_memo_compare", None)
            if compare_fn is not None and compare_fn(hooks_ctx._props, new.props):
                new.hooks_ctx = hooks_ctx
                new.render_effect = old.render_effect
                new.subtree = old.subtree
                return

        hooks_ctx._props = new.props
        new.hooks_ctx = hooks_ctx
        new.render_effect = old.render_effect

        hooks_ctx.cursor = 0
        hooks_ctx.effect_cursor = 0
        hooks_ctx.layout_effect_cursor = 0
        _push_hooks_ctx(hooks_ctx)
        try:
            func_sub = new.tag(new.props)  # type: ignore[operator]
            if not isinstance(func_sub, VNode):
                func_sub = to_text_vnode(func_sub)
        except Exception as e:
            log_error(f"Render failed in function component {component_name(new.tag)}", e)
            raise
        finally:
            _pop_hooks_ctx()

        prev_sub = old.subtree
        new.subtree = func_sub
        if prev_sub is None:
            mount(func_sub, container)
        else:
            patch(prev_sub, func_sub, container)
        hooks_ctx._run_pending_effects()
    else:
        func_sub = new.tag(new.props)  # type: ignore[operator]
        if not isinstance(func_sub, VNode):
            func_sub = to_text_vnode(func_sub)
        prev_sub = old.subtree
        new.subtree = func_sub
        if prev_sub is None:
            mount(func_sub, container)
        else:
            patch(prev_sub, func_sub, container)


def _handle_render_error(
    instance: Component,
    vnode: VNode,
    error: Exception,
    container: Element,
    anchor: Any,
    *,
    old_subtree: Optional[VNode] = None,
) -> None:
    """Handle a render error, delegating to ErrorBoundary if applicable."""
    if isinstance(instance, ErrorBoundary):
        instance._error.set(error)
        handler = instance.props.get("on_error")
        if callable(handler):
            try:
                handler(error)
            except Exception as cb_err:
                log_error("on_error callback failed in ErrorBoundary", cb_err)
        try:
            fb_sub = instance.render()
            if not isinstance(fb_sub, VNode):
                fb_sub = to_text_vnode(fb_sub)
        except Exception:
            fb_sub = to_text_vnode("Error in fallback")
        prev_sub = old_subtree or vnode.subtree
        vnode.subtree = fb_sub
        if prev_sub is None or getattr(prev_sub, "el", None) is None:
            mount(fb_sub, container, anchor)
            vnode.el = fb_sub.el
        else:
            patch(prev_sub, fb_sub, container)
            vnode.el = fb_sub.el
    else:
        log_error(f"Render failed in {component_name(type(instance))}", error)
        raise error


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

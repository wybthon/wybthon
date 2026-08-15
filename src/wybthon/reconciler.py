"""Owned VDOM reconciliation and retained DOM regions.

VNode objects are unmounted render descriptions. This module creates a
separate ``MountedNode`` tree containing DOM IDs, reactive subscriptions,
component owners, and mounted children. The separation lets one VNode be
mounted more than once and gives async boundaries a tree they can retain
without mutating application declarations.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Dict, Iterable, List, Optional, Set, Union

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
from .reactivity import Owner, ReactiveProps, _ComponentContext, effect
from .runtime import MountHandle, Runtime
from .template import BIND_EVENT, BIND_PROP, BIND_REACTIVE, BIND_TEXT, NODE_HOLE, NODE_STATIC, build_plan
from .vnode import Fragment, VNode, dynamic, is_getter, normalize_children, to_text_vnode

__all__ = ["MountHandle", "MountedNode", "render", "mount", "patch", "unmount"]

_emit = kernel.emit
_alloc_id = kernel.alloc_id


class MountedNode:
    """Per-mount state corresponding to one VNode description."""

    __slots__ = (
        "vnode",
        "parent_id",
        "node_id",
        "end_id",
        "children",
        "subtree",
        "render_effect",
        "component_ctx",
        "scope_owner",
        "bindings",
        "state",
        "disposed",
    )

    def __init__(self, vnode: VNode, parent_id: int) -> None:
        self.vnode = vnode
        self.parent_id = parent_id
        self.node_id: Optional[int] = None
        self.end_id: Optional[int] = None
        self.children: List[MountedNode] = []
        self.subtree: Optional[MountedNode] = None
        self.render_effect: Any = None
        self.component_ctx: Optional[_ComponentContext] = None
        self.scope_owner: Optional[Owner] = None
        self.bindings: List[Any] = []
        self.state: Any = None
        self.disposed = False

    @property
    def key(self) -> Any:
        """Stable reconciliation key from the VNode declaration."""
        return self.vnode.key


_default_runtime = Runtime()


def _coerce_container(container: Union[Element, str, int]) -> Element:
    if isinstance(container, str):
        return Element(container, existing=True)
    if isinstance(container, int):
        return Element(node_id=container)
    return container


def render(vnode: VNode, container: Union[Element, str, int]) -> MountHandle:
    """Render ``vnode`` and return its owned mount handle.

    Calling ``render`` again for the same container patches the existing
    mount. Call ``handle.dispose()`` to unmount the application.
    """
    return _default_runtime.render(vnode, container)


def _create_handle(runtime: Runtime, element: Element, vnode: VNode) -> MountHandle:
    import wybthon.reactivity as _rx

    owner = Owner()
    handle = MountHandle(runtime, element, owner)
    previous_owner = _rx._current_owner
    _rx._current_owner = owner
    _rx._begin_render()
    try:
        handle._mounted = mount(vnode, element.node_id)
    except Exception:
        owner.dispose()
        raise
    finally:
        _rx._current_owner = previous_owner
        _rx._end_render()
    kernel.commit()
    return handle


def _update_handle(handle: MountHandle, vnode: VNode) -> None:
    import wybthon.reactivity as _rx

    previous_owner = _rx._current_owner
    _rx._current_owner = handle._root_owner
    _rx._begin_render()
    try:
        handle._mounted = patch(handle._mounted, vnode, handle.container_id)
    finally:
        _rx._current_owner = previous_owner
        _rx._end_render()
    kernel.commit()


def _dispose_handle(handle: MountHandle) -> None:
    import wybthon.reactivity as _rx

    previous_owner = _rx._current_owner
    _rx._current_owner = handle._root_owner
    _rx._begin_render()
    try:
        if handle._mounted is not None:
            _unmount(handle._mounted)
            handle._mounted = None
        handle._root_owner.dispose()
        handle.disposed = True
        handle._runtime._forget(handle)
    finally:
        _rx._current_owner = previous_owner
        _rx._end_render()
    kernel.commit()


def _dispatch_to_error_boundary(exc: BaseException) -> bool:
    import wybthon.reactivity as _rx

    owner = _rx._current_owner
    while owner is not None:
        handler = owner._error_handler
        if handler is not None:
            try:
                handler(exc)
            except Exception as handler_exc:
                log_error(f"Error boundary handler raised: {handler_exc}", handler_exc)
            return True
        owner = owner._parent
    return False


def _first_dom_id(mounted: MountedNode) -> Optional[int]:
    tag = mounted.vnode.tag
    if tag == "_suspense":
        return mounted.node_id
    if tag in ("_dynamic", "_scope", "_provider") or callable(tag):
        if mounted.subtree is not None:
            found = _first_dom_id(mounted.subtree)
            if found is not None:
                return found
    return mounted.node_id


def _dom_node_ids(mounted: MountedNode) -> List[int]:
    tag = mounted.vnode.tag
    if tag == "_suspense":
        return mounted.state.live_dom_ids()
    if tag == "_dynamic":
        result = _dom_node_ids(mounted.subtree) if mounted.subtree is not None else []
        if mounted.node_id is not None:
            result.append(mounted.node_id)
        return result
    if tag in ("_scope", "_provider") or callable(tag):
        return _dom_node_ids(mounted.subtree) if mounted.subtree is not None else []
    if tag == "_fragment":
        result = [] if mounted.node_id is None else [mounted.node_id]
        for child in mounted.children:
            result.extend(_dom_node_ids(child))
        if mounted.end_id is not None:
            result.append(mounted.end_id)
        return result
    return [] if mounted.node_id is None else [mounted.node_id]


def _move_mounted(mounted: MountedNode, parent_id: int, anchor_id: Optional[int]) -> None:
    for node_id in _dom_node_ids(mounted):
        _emit((OP_INSERT, parent_id, node_id, anchor_id))
    mounted.parent_id = parent_id


def mount(vnode: Union[VNode, str], parent_id: int, anchor_id: Optional[int] = None) -> MountedNode:
    """Mount a declaration and return its independent mounted state."""
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)
    tag = vnode.tag
    if tag == "_text":
        mounted = MountedNode(vnode, parent_id)
        mounted.node_id = _alloc_id()
        _emit((OP_CREATE_TEXT, mounted.node_id, vnode.props.get("nodeValue", "")))
        _emit((OP_INSERT, parent_id, mounted.node_id, anchor_id))
        return mounted
    if tag == "_dynamic":
        return _mount_dynamic(vnode, parent_id, anchor_id)
    if tag == "_fragment":
        return _mount_fragment(vnode, parent_id, anchor_id)
    if tag == "_scope":
        return _mount_scope(vnode, parent_id, anchor_id)
    if tag == "_provider":
        return _mount_provider(vnode, parent_id, anchor_id)
    if tag == "_suspense":
        from .suspense import _mount_suspense

        return _mount_suspense(vnode, parent_id, anchor_id)
    if callable(tag):
        return _mount_component(vnode, parent_id, anchor_id)
    template_mounted = _mount_template(vnode, parent_id, anchor_id)
    return template_mounted if template_mounted is not None else _mount_element(vnode, parent_id, anchor_id)


def _mount_element(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> MountedNode:
    assert isinstance(vnode.tag, str)
    mounted = MountedNode(vnode, parent_id)
    mounted.node_id = _alloc_id()
    _emit((OP_CREATE_ELEMENT, mounted.node_id, vnode.tag))
    bindings = apply_initial_props(mounted.node_id, vnode.props)
    if bindings:
        mounted.bindings.extend(bindings)
    for child in normalize_children(vnode.children):
        mounted.children.append(mount(child, mounted.node_id))
    _emit((OP_INSERT, parent_id, mounted.node_id, anchor_id))
    attach_ref(vnode.props, mounted.node_id)
    return mounted


def _mount_template(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> Optional[MountedNode]:
    if not kernel.supports_html():
        return None
    plan = build_plan(vnode)
    if plan is None:
        return None

    count = plan.node_count
    first = kernel.alloc_ids(count)
    _emit((OP_CLONE_TPL, first, count, kernel.template_id(plan.html)))

    instances: List[Optional[MountedNode]] = [None] * count
    placeholders: List[int] = []
    root: Optional[MountedNode] = None
    for index, (kind, description, parent_index) in enumerate(plan.order):
        node_id = first + index
        parent_mounted = instances[parent_index] if parent_index >= 0 else None
        if kind == NODE_STATIC:
            instance_parent_id = parent_id
            if parent_mounted is not None:
                assert parent_mounted.node_id is not None
                instance_parent_id = parent_mounted.node_id
            instance = MountedNode(description, instance_parent_id)
            instance.node_id = node_id
            instances[index] = instance
            if parent_mounted is not None:
                parent_mounted.children.append(instance)
            else:
                root = instance
        else:
            assert parent_mounted is not None and parent_mounted.node_id is not None
            if kind == NODE_HOLE:
                child = _mount_dynamic(description, parent_mounted.node_id, end_id=node_id)
            else:
                child = mount(description, parent_mounted.node_id, node_id)
                _emit((OP_REMOVE, node_id))
                placeholders.append(node_id)
            instances[index] = child
            parent_mounted.children.append(child)

    assert root is not None
    for target_index, binding_kind, name, value in plan.bindings:
        target_mounted = instances[target_index]
        assert target_mounted is not None
        target_id = target_mounted.node_id
        assert target_id is not None
        if binding_kind == BIND_TEXT:
            if value != " ":
                _emit((OP_SET_TEXT, target_id, value))
        elif binding_kind == BIND_EVENT:
            set_handler(target_id, name, value if callable(value) else None)
        elif binding_kind == BIND_REACTIVE:
            target_mounted.bindings.append(_bind_reactive_prop(target_id, name, value))
        elif binding_kind == BIND_PROP:
            _apply_single_prop(target_id, name, None, value)
        else:
            attach_ref({name: value}, target_id)

    _emit((OP_INSERT, parent_id, first, anchor_id))
    if placeholders:
        _emit((OP_RELEASE, placeholders))
    return root


def _mount_fragment(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> MountedNode:
    mounted = MountedNode(vnode, parent_id)
    mounted.node_id = _alloc_id()
    mounted.end_id = _alloc_id()
    _emit((OP_CREATE_COMMENT, mounted.node_id))
    _emit((OP_INSERT, parent_id, mounted.node_id, anchor_id))
    _emit((OP_CREATE_COMMENT, mounted.end_id))
    _emit((OP_INSERT, parent_id, mounted.end_id, anchor_id))
    for child in normalize_children(vnode.children):
        mounted.children.append(mount(child, parent_id, mounted.end_id))
    return mounted


def _mount_scope(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> MountedNode:
    import wybthon.reactivity as _rx

    mounted = MountedNode(vnode, parent_id)
    owner = vnode.props.get("owner")
    if not isinstance(owner, Owner):
        owner = Owner()
        if _rx._current_owner is not None:
            _rx._current_owner._add_child(owner)
    mounted.scope_owner = owner
    child = vnode.children[0] if vnode.children else to_text_vnode("")
    previous_owner = _rx._current_owner
    _rx._current_owner = owner
    try:
        mounted.subtree = mount(child, parent_id, anchor_id)
    finally:
        _rx._current_owner = previous_owner
    mounted.node_id = _first_dom_id(mounted.subtree)
    return mounted


def _provider_children(props: Dict[str, Any]) -> VNode:
    children = props.get("children", [])
    if children is None:
        children = []
    if not isinstance(children, (list, tuple)):
        children = [children]
    return Fragment(*children)


def _bind_provider_value(mounted: MountedNode, value: Any) -> None:
    state = mounted.state
    signal = state["signal"]
    old_binding = state.get("binding")
    if old_binding is not None:
        old_binding.dispose()
        state["binding"] = None
    if is_getter(value):
        state["binding"] = effect(lambda: signal.set(value()))
    else:
        signal.set(value)


def _mount_provider(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> MountedNode:
    import wybthon.reactivity as _rx

    mounted = MountedNode(vnode, parent_id)
    owner = Owner()
    if _rx._current_owner is not None:
        _rx._current_owner._add_child(owner)
    mounted.scope_owner = owner

    context_object = vnode.props.get("context")
    value = vnode.props.get("value")
    if is_getter(value):
        assert callable(value)
        resolved = value()
    else:
        resolved = value
    signal = _rx.Signal(resolved)
    if context_object is not None:
        owner._set_context(context_object.id, signal)
    mounted.state = {"context": context_object, "signal": signal, "binding": None}

    previous_owner = _rx._current_owner
    _rx._current_owner = owner
    try:
        _bind_provider_value(mounted, value)
        mounted.subtree = mount(_provider_children(vnode.props), parent_id, anchor_id)
    finally:
        _rx._current_owner = previous_owner
    mounted.node_id = _first_dom_id(mounted.subtree)
    return mounted


def _coerce_dynamic_result(value: Any) -> VNode:
    if isinstance(value, VNode):
        return value
    if isinstance(value, (list, tuple)):
        from .vnode import Fragment

        return Fragment(*value)
    return to_text_vnode("" if value is None else value)


def _dynamic_updater(mounted: MountedNode, getter: Any) -> Any:
    def update() -> None:
        try:
            description = _coerce_dynamic_result(getter())
            if mounted.subtree is None:
                mounted.subtree = mount(description, mounted.parent_id, mounted.end_id)
            else:
                mounted.subtree = patch(mounted.subtree, description, mounted.parent_id)
        except Exception as exc:
            if not _dispatch_to_error_boundary(exc):
                log_error(f"Reactive region failed: {exc}", exc)

    return update


def _mount_dynamic(
    vnode: VNode,
    parent_id: int,
    anchor_id: Optional[int] = None,
    end_id: Optional[int] = None,
) -> MountedNode:
    mounted = MountedNode(vnode, parent_id)
    if end_id is None:
        end_id = _alloc_id()
        _emit((OP_CREATE_COMMENT, end_id))
        _emit((OP_INSERT, parent_id, end_id, anchor_id))
    mounted.node_id = end_id
    mounted.end_id = end_id
    getter = vnode.props.get("getter")
    if callable(getter):
        mounted.render_effect = effect(_dynamic_updater(mounted, getter))
    return mounted


def _mount_component(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> MountedNode:
    import wybthon.reactivity as _rx

    component = vnode.tag
    assert callable(component)
    mounted = MountedNode(vnode, parent_id)
    context = _ComponentContext()
    context._props = vnode.props
    context._vnode = vnode
    context._reactive_props = ReactiveProps(vnode.props, getattr(component, "_wyb_defaults", {}))
    mounted.component_ctx = context
    if _rx._current_owner is not None:
        _rx._current_owner._add_child(context)

    previous_owner = _rx._current_owner
    _rx._current_owner = context
    try:
        try:
            result = component(context._reactive_props)
        except Exception as exc:
            if _dispatch_to_error_boundary(exc):
                result = to_text_vnode("")
            else:
                log_error(f"Render failed in function component {component_name(component)}", exc)
                raise
        description = _normalize_component_result(result)
        try:
            mounted.subtree = mount(description, parent_id, anchor_id)
        except Exception as exc:
            if not _dispatch_to_error_boundary(exc):
                raise
            mounted.subtree = mount(to_text_vnode(""), parent_id, anchor_id)
    finally:
        _rx._current_owner = previous_owner
    mounted.node_id = _first_dom_id(mounted.subtree)
    context._schedule_mount_callbacks()
    return mounted


def _normalize_component_result(result: Any) -> VNode:
    if isinstance(result, VNode):
        return result
    if callable(result):
        return dynamic(result)
    return to_text_vnode(result)


def unmount(target: Union[MountHandle, MountedNode]) -> None:
    """Dispose a mount handle or an internal mounted subtree."""
    if isinstance(target, MountHandle):
        target.dispose()
        return
    _unmount(target)
    kernel.commit()


def _unmount(mounted: MountedNode) -> None:
    if mounted.disposed:
        return
    for node_id in _dom_node_ids(mounted):
        _emit((OP_REMOVE, node_id))
    released: List[int] = []
    _dispose_tree(mounted, released)
    if released:
        _emit((OP_RELEASE, released))


def _dispose_tree(mounted: MountedNode, released: List[int]) -> None:
    if mounted.disposed:
        return
    mounted.disposed = True
    tag = mounted.vnode.tag
    if tag == "_suspense":
        mounted.state.dispose_into(released)
        for node_id in (mounted.node_id, mounted.end_id):
            if node_id is not None and node_id not in released:
                released.append(node_id)
        mounted.node_id = None
        mounted.end_id = None
        return
    if mounted.render_effect is not None:
        mounted.render_effect.dispose()
        mounted.render_effect = None
    if mounted.component_ctx is not None:
        mounted.component_ctx.dispose()
    if mounted.scope_owner is not None:
        mounted.scope_owner.dispose()
    if mounted.subtree is not None:
        _dispose_tree(mounted.subtree, released)
        mounted.subtree = None
    for child in mounted.children:
        _dispose_tree(child, released)
    mounted.children.clear()
    if isinstance(tag, str) and not tag.startswith("_") and mounted.node_id is not None:
        detach_ref(mounted.vnode.props)
        remove_handlers_for(mounted.node_id)
    for node_id in (mounted.node_id, mounted.end_id):
        if node_id is not None and node_id not in released:
            released.append(node_id)
    mounted.node_id = None
    mounted.end_id = None


def _same_type(mounted: MountedNode, vnode: VNode) -> bool:
    return mounted.vnode.tag == vnode.tag


def patch(old: Optional[MountedNode], new: VNode, parent_id: int) -> MountedNode:
    """Patch a mounted instance with a new VNode description."""
    if old is None:
        return mount(new, parent_id)
    if old.vnode is new:
        return old
    if not _same_type(old, new):
        return _replace(old, new, parent_id)

    old_vnode = old.vnode
    old.vnode = new
    tag = new.tag
    if tag == "_text":
        if old.node_id is not None:
            old_text = old_vnode.props.get("nodeValue", "")
            new_text = new.props.get("nodeValue", "")
            if old_text != new_text:
                _emit((OP_SET_TEXT, old.node_id, new_text))
        return old
    if tag == "_dynamic":
        return _patch_dynamic(old, old_vnode, new)
    if tag == "_fragment":
        old.children = _reconcile_children(old.children, normalize_children(new.children), parent_id, old.end_id)
        return old
    if tag == "_scope":
        if old_vnode.props.get("owner") is not new.props.get("owner"):
            old.vnode = old_vnode
            return _replace(old, new, parent_id)
        child = new.children[0] if new.children else to_text_vnode("")
        assert old.subtree is not None
        old.subtree = patch(old.subtree, child, parent_id)
        old.node_id = _first_dom_id(old.subtree)
        return old
    if tag == "_provider":
        return _patch_provider(old, old_vnode, new, parent_id)
    if tag == "_suspense":
        from .suspense import _patch_suspense

        return _patch_suspense(old, old_vnode, new)
    if callable(tag):
        _patch_component(old, new)
        return old

    assert old.node_id is not None
    apply_props(old.node_id, old_vnode.props, new.props)
    attach_ref(new.props, old.node_id)
    old.children = _reconcile_children(old.children, normalize_children(new.children), old.node_id, None)
    return old


def _patch_dynamic(mounted: MountedNode, old_vnode: VNode, new_vnode: VNode) -> MountedNode:
    old_getter = old_vnode.props.get("getter")
    new_getter = new_vnode.props.get("getter")
    if old_getter is new_getter:
        return mounted
    if mounted.render_effect is not None:
        mounted.render_effect.dispose()
        mounted.render_effect = None
    if callable(new_getter):
        mounted.render_effect = effect(_dynamic_updater(mounted, new_getter))
    return mounted


def _patch_component(mounted: MountedNode, vnode: VNode) -> None:
    context = mounted.component_ctx
    if context is None:
        return
    context._props = vnode.props
    if context._reactive_props is not None:
        context._reactive_props._update(vnode.props)
    context._vnode = vnode


def _patch_provider(
    mounted: MountedNode,
    old_vnode: VNode,
    new_vnode: VNode,
    parent_id: int,
) -> MountedNode:
    old_context = old_vnode.props.get("context")
    new_context = new_vnode.props.get("context")
    if old_context is not new_context:
        mounted.vnode = old_vnode
        return _replace(mounted, new_vnode, parent_id)

    import wybthon.reactivity as _rx

    previous_owner = _rx._current_owner
    _rx._current_owner = mounted.scope_owner
    try:
        _bind_provider_value(mounted, new_vnode.props.get("value"))
        assert mounted.subtree is not None
        mounted.subtree = patch(mounted.subtree, _provider_children(new_vnode.props), parent_id)
    finally:
        _rx._current_owner = previous_owner
    mounted.node_id = _first_dom_id(mounted.subtree)
    return mounted


def _replace(old: MountedNode, new: VNode, parent_id: int) -> MountedNode:
    anchor = _first_dom_id(old)
    if anchor is None:
        _unmount(old)
        return mount(new, parent_id)
    marker = _alloc_id()
    _emit((OP_CREATE_COMMENT, marker))
    _emit((OP_INSERT, parent_id, marker, anchor))
    _unmount(old)
    mounted = mount(new, parent_id, marker)
    _emit((OP_REMOVE, marker))
    _emit((OP_RELEASE, [marker]))
    return mounted


def _identity_positions(children: Iterable[MountedNode]) -> Dict[int, List[int]]:
    positions: Dict[int, List[int]] = {}
    for index, child in enumerate(children):
        positions.setdefault(id(child.vnode), []).append(index)
    return positions


def _reconcile_children(
    old_children: List[MountedNode],
    descriptions: List[VNode],
    parent_id: int,
    end_marker: Optional[int],
) -> List[MountedNode]:
    old_count = len(old_children)
    new_count = len(descriptions)
    used = [False] * old_count
    sources = [-1] * new_count
    should_patch = [False] * new_count
    identity = _identity_positions(old_children)
    identity_cursor: Dict[int, int] = {}
    keyed: Dict[Any, List[int]] = {}
    key_cursor: Dict[Any, int] = {}
    for index, child in enumerate(old_children):
        if child.key is not None:
            keyed.setdefault(child.key, []).append(index)

    unmatched: List[int] = []
    for index, description in enumerate(descriptions):
        positions = identity.get(id(description), ())
        cursor = identity_cursor.get(id(description), 0)
        while cursor < len(positions) and used[positions[cursor]]:
            cursor += 1
        identity_cursor[id(description)] = cursor + 1
        if cursor < len(positions):
            source = positions[cursor]
            used[source] = True
            sources[index] = source
            continue
        if description.key is not None:
            positions = keyed.get(description.key, ())
            cursor = key_cursor.get(description.key, 0)
            while cursor < len(positions) and used[positions[cursor]]:
                cursor += 1
            key_cursor[description.key] = cursor + 1
            if cursor < len(positions):
                source = positions[cursor]
                used[source] = True
                sources[index] = source
                should_patch[index] = True
                continue
        unmatched.append(index)

    type_queues: Dict[Any, List[int]] = {}
    type_cursor: Dict[Any, int] = {}
    for index, child in enumerate(old_children):
        if not used[index] and child.key is None:
            type_queues.setdefault(child.vnode.tag, []).append(index)
    for index in unmatched:
        description = descriptions[index]
        if description.key is not None:
            continue
        positions = type_queues.get(description.tag, ())
        cursor = type_cursor.get(description.tag, 0)
        while cursor < len(positions) and used[positions[cursor]]:
            cursor += 1
        type_cursor[description.tag] = cursor + 1
        if cursor < len(positions):
            source = positions[cursor]
            used[source] = True
            sources[index] = source
            should_patch[index] = True

    result: List[Optional[MountedNode]] = [None] * new_count
    for index, source in enumerate(sources):
        if source >= 0:
            instance = old_children[source]
            result[index] = patch(instance, descriptions[index], parent_id) if should_patch[index] else instance

    tails: List[int] = []
    tail_indices: List[int] = []
    predecessors = [-1] * new_count
    for index, source in enumerate(sources):
        if source < 0:
            continue
        position = bisect_left(tails, source)
        if position == len(tails):
            tails.append(source)
            tail_indices.append(index)
        else:
            tails[position] = source
            tail_indices[position] = index
        predecessors[index] = tail_indices[position - 1] if position else -1
    stable: Set[int] = set()
    cursor = tail_indices[-1] if tail_indices else -1
    while cursor >= 0:
        stable.add(cursor)
        cursor = predecessors[cursor]

    anchor = end_marker
    for index in range(new_count - 1, -1, -1):
        candidate = result[index]
        if candidate is None:
            candidate = mount(descriptions[index], parent_id, anchor)
            result[index] = candidate
        elif index not in stable:
            _move_mounted(candidate, parent_id, anchor)
        first = _first_dom_id(candidate)
        if first is not None:
            anchor = first

    for index, child in enumerate(old_children):
        if not used[index]:
            _unmount(child)
    return [child for child in result if child is not None]


def _mounted_node_count(mounted: Optional[MountedNode]) -> int:
    if mounted is None:
        return 0
    return 1 + _mounted_node_count(mounted.subtree) + sum(_mounted_node_count(child) for child in mounted.children)

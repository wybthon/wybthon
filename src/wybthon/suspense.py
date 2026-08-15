"""Retained Suspense boundaries and coordinated reveal ordering.

Primary content mounts once under a gated owner. While a resource is pending,
the content's DOM range moves to a detached document fragment instead of being
disposed. Revealing moves the same nodes back and releases held ``on_mount``
callbacks and initial user effects after the DOM commit.
"""

from __future__ import annotations

from typing import Any, List, Optional, Set

from . import kernel
from .kernel import OP_CREATE_COMMENT, OP_CREATE_FRAGMENT, OP_INSERT
from .reactivity import (
    SUSPENSE_CONTEXT_KEY,
    SUSPENSE_GATE_CONTEXT_KEY,
    Owner,
    _get_component_ctx,
    _SuspenseGate,
    effect,
)
from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["Suspense", "SuspenseList"]

SUSPENSE_LIST_CONTEXT_KEY = "__wyb_suspense_list__"


def _primary_children(vnode: VNode) -> List[Any]:
    """Resolve Suspense's explicit ``children`` slot once per description."""
    children = vnode.props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    if len(children) == 1 and callable(children[0]) and not isinstance(children[0], type):
        children = children[0]()
        if children is None:
            return []
        if isinstance(children, (list, tuple)):
            return list(children)
        return [children]
    return children


class _SuspenseCollector:
    """Track resources read by one retained primary region."""

    __slots__ = ("_controller", "_resources", "_watchers")

    def __init__(self, controller: "_SuspenseController") -> None:
        self._controller = controller
        self._resources: Set[Any] = set()
        self._watchers: List[Any] = []

    def register(self, resource: Any) -> None:
        if resource in self._resources:
            return
        self._resources.add(resource)

        def watch() -> None:
            loading = bool(resource._loading.get())
            if not loading:
                self._resources.discard(resource)
            self._controller.resource_changed()

        import wybthon.reactivity as _rx

        previous_owner = _rx._current_owner
        _rx._current_owner = self._controller.primary_owner
        try:
            self._watchers.append(effect(watch))
        finally:
            _rx._current_owner = previous_owner

    def is_loading(self) -> bool:
        return any(bool(resource._loading.peek()) for resource in self._resources)


class _SuspenseController:
    """Own primary, fallback, staging, and lifecycle state for a boundary."""

    __slots__ = (
        "mounted",
        "parent_id",
        "end_id",
        "boundary_owner",
        "primary_owner",
        "fallback_owner",
        "gate",
        "collector",
        "primary",
        "fallback",
        "fallback_value",
        "staging_id",
        "mode",
        "mounting",
        "list_state",
    )

    def __init__(self, mounted: Any, parent_id: int, end_id: int, owner: Owner, list_state: Any) -> None:
        self.mounted = mounted
        self.parent_id = parent_id
        self.end_id = end_id
        self.boundary_owner = owner
        self.primary_owner = Owner()
        owner._add_child(self.primary_owner)
        self.fallback_owner: Optional[Owner] = None
        self.gate = _SuspenseGate()
        self.primary_owner._set_context(SUSPENSE_GATE_CONTEXT_KEY, self.gate)
        self.collector = _SuspenseCollector(self)
        self.primary_owner._set_context(SUSPENSE_CONTEXT_KEY, self.collector)
        self.primary: Any = None
        self.fallback: Any = None
        self.fallback_value: Any = None
        self.staging_id: Optional[int] = None
        self.mode = "content"
        self.mounting = True
        self.list_state: Optional[_SuspenseListState] = list_state

    @property
    def pending(self) -> bool:
        return self.collector.is_loading()

    def finish_mount(self) -> None:
        self.mounting = False
        if self.list_state is not None:
            self.list_state.register(self)
        else:
            self.apply_mode("fallback" if self.pending else "content")

    def resource_changed(self) -> None:
        if self.mounting:
            return
        from .reactivity import _is_transition_pending

        if self.pending and self.mode == "content" and _is_transition_pending():
            return
        if self.list_state is not None:
            self.list_state.reconsider_all()
        else:
            self.apply_mode("fallback" if self.pending else "content")

    def _ensure_staging(self) -> int:
        if self.staging_id is None:
            self.staging_id = kernel.alloc_id()
            kernel.emit((OP_CREATE_FRAGMENT, self.staging_id))
        return self.staging_id

    def _stage_primary(self) -> None:
        if self.primary is None or self.mode != "content":
            return
        from .reconciler import _move_mounted

        _move_mounted(self.primary, self._ensure_staging(), None)

    def _fallback_description(self) -> VNode:
        value = self.fallback_value
        if callable(value) and not isinstance(value, VNode):
            try:
                value = value()
            except Exception:
                value = "Loading..."
        return value if isinstance(value, VNode) else to_text_vnode("" if value is None else value)

    def _mount_fallback(self) -> None:
        if self.fallback is not None:
            return
        import wybthon.reactivity as _rx

        from .reconciler import mount

        owner = Owner()
        self.boundary_owner._add_child(owner)
        self.fallback_owner = owner
        previous_owner = _rx._current_owner
        _rx._current_owner = owner
        try:
            self.fallback = mount(self._fallback_description(), self.parent_id, self.end_id)
        finally:
            _rx._current_owner = previous_owner

    def _unmount_fallback(self) -> None:
        if self.fallback is None:
            return
        from .reconciler import _unmount

        _unmount(self.fallback)
        self.fallback = None
        if self.fallback_owner is not None:
            self.fallback_owner.dispose()
            self.fallback_owner = None

    def apply_mode(self, mode: str) -> None:
        if mode == self.mode and not (mode == "content" and self.gate.blocked):
            return
        from .reconciler import _move_mounted

        if mode == "content":
            self._unmount_fallback()
            if self.primary is not None and self.mode != "content":
                _move_mounted(self.primary, self.parent_id, self.end_id)
            self.mode = "content"
            self.gate.reveal()
            return

        if self.mode == "content":
            self._stage_primary()
        self._unmount_fallback()
        self.mode = mode
        if mode == "fallback":
            self._mount_fallback()

    def patch(self, vnode: VNode) -> None:
        import wybthon.reactivity as _rx

        from .reconciler import patch

        self.fallback_value = vnode.props.get("fallback")
        primary_parent = self.parent_id if self.mode == "content" else self._ensure_staging()
        previous_owner = _rx._current_owner
        _rx._current_owner = self.primary_owner
        try:
            self.primary = patch(self.primary, Fragment(*_primary_children(vnode)), primary_parent)
        finally:
            _rx._current_owner = previous_owner
        if self.fallback is not None:
            _rx._current_owner = self.fallback_owner
            try:
                self.fallback = patch(self.fallback, self._fallback_description(), self.parent_id)
            finally:
                _rx._current_owner = previous_owner

    def live_dom_ids(self) -> List[int]:
        from .reconciler import _dom_node_ids

        result: List[int] = []
        if self.mounted.node_id is not None:
            result.append(self.mounted.node_id)
        visible = self.primary if self.mode == "content" else self.fallback
        if visible is not None:
            result.extend(_dom_node_ids(visible))
        if self.end_id is not None:
            result.append(self.end_id)
        return result

    def dispose_into(self, released: List[int]) -> None:
        from .reconciler import _dispose_tree

        if self.list_state is not None:
            self.list_state.unregister(self)
        if self.primary is not None:
            _dispose_tree(self.primary, released)
            self.primary = None
        if self.fallback is not None:
            _dispose_tree(self.fallback, released)
            self.fallback = None
        self.boundary_owner.dispose()
        if self.staging_id is not None:
            released.append(self.staging_id)
            self.staging_id = None


def Suspense(fallback: Any = None, children: Any = None) -> VNode:
    """Render retained primary content with a fallback while resources load."""
    if children is None:
        children = []
    elif not isinstance(children, list):
        children = [children]
    return VNode("_suspense", {"fallback": fallback, "children": children}, [])


def _mount_suspense(vnode: VNode, parent_id: int, anchor_id: Optional[int]) -> Any:
    import wybthon.reactivity as _rx

    from .reconciler import MountedNode, mount

    mounted = MountedNode(vnode, parent_id)
    mounted.node_id = kernel.alloc_id()
    mounted.end_id = kernel.alloc_id()
    kernel.emit((OP_CREATE_COMMENT, mounted.node_id))
    kernel.emit((OP_INSERT, parent_id, mounted.node_id, anchor_id))
    kernel.emit((OP_CREATE_COMMENT, mounted.end_id))
    kernel.emit((OP_INSERT, parent_id, mounted.end_id, anchor_id))

    boundary_owner = Owner()
    if _rx._current_owner is not None:
        _rx._current_owner._add_child(boundary_owner)
    list_state = boundary_owner._lookup_context(SUSPENSE_LIST_CONTEXT_KEY, None)
    controller = _SuspenseController(mounted, parent_id, mounted.end_id, boundary_owner, list_state)
    mounted.state = controller
    controller.fallback_value = vnode.props.get("fallback")
    if list_state is not None:
        controller.primary_owner._set_context(SUSPENSE_LIST_CONTEXT_KEY, None)

    previous_owner = _rx._current_owner
    _rx._current_owner = controller.primary_owner
    try:
        controller.primary = mount(Fragment(*_primary_children(vnode)), parent_id, mounted.end_id)
    finally:
        _rx._current_owner = previous_owner
    controller.finish_mount()
    return mounted


def _patch_suspense(mounted: Any, _old: VNode, new: VNode) -> Any:
    mounted.state.patch(new)
    return mounted


class _SuspenseListState:
    """Coordinate retained boundaries without blocking their preparation."""

    __slots__ = ("reveal_order", "tail", "controllers")

    def __init__(self, reveal_order: str, tail: Optional[str]) -> None:
        self.reveal_order = reveal_order
        self.tail = tail
        self.controllers: List[_SuspenseController] = []

    def register(self, controller: _SuspenseController) -> None:
        self.controllers.append(controller)
        self.reconsider_all()

    def unregister(self, controller: _SuspenseController) -> None:
        if controller in self.controllers:
            self.controllers.remove(controller)
            self.reconsider_all()

    def reconsider_all(self) -> None:
        for index, controller in enumerate(list(self.controllers)):
            controller.apply_mode(self.display_mode(index))

    def display_mode(self, index: int) -> str:
        controllers = self.controllers
        if not controllers:
            return "content"
        if self.reveal_order == "together":
            if not any(controller.pending for controller in controllers):
                return "content"
            return self._pending_mode(index, range(len(controllers)))
        if self.reveal_order == "backwards":
            order = range(len(controllers) - 1, -1, -1)
            blocked = any(controllers[j].pending for j in range(len(controllers) - 1, index, -1))
        else:
            order = range(len(controllers))
            blocked = any(controllers[j].pending for j in range(index))
        if not blocked and not controllers[index].pending:
            return "content"
        return self._pending_mode(index, order)

    def _pending_mode(self, index: int, order: Any) -> str:
        if self.tail is None:
            return "fallback"
        if self.tail == "hidden":
            return "hidden"
        for current in order:
            if self.controllers[current].pending:
                return "fallback" if current == index else "hidden"
        return "hidden"


def SuspenseList(children: Any = None, reveal_order: str = "forwards", tail: Optional[str] = None) -> VNode:
    """Coordinate the reveal order of retained Suspense boundaries."""
    if reveal_order not in ("forwards", "backwards", "together"):
        raise ValueError('reveal_order must be "forwards", "backwards", or "together"')
    if tail not in (None, "collapsed", "hidden"):
        raise ValueError('tail must be None, "collapsed", or "hidden"')
    return h(_SuspenseListComponent, {"children": children, "reveal_order": reveal_order, "tail": tail})


def _SuspenseListComponent(props: Any) -> VNode:
    state = _SuspenseListState(props.value("reveal_order"), props.value("tail"))
    context = _get_component_ctx()
    if context is not None:
        context._set_context(SUSPENSE_LIST_CONTEXT_KEY, state)
    children = props.value("children") or []
    if not isinstance(children, list):
        children = [children]
    return Fragment(*children)


_SuspenseListComponent._wyb_component = True  # type: ignore[attr-defined]

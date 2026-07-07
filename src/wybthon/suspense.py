"""`Suspense` component for rendering fallback UI during async loading.

[`Suspense`][wybthon.Suspense] tracks resources **automatically**,
matching SolidJS: any [`Resource`][wybthon.Resource] read (called) under
the boundary while it's still `"pending"` registers itself, and the
boundary shows its fallback until every registered resource resolves.
No `resources` prop wiring is needed.

Refetches don't re-trigger the boundary. A resource that already has
data enters the `"refreshing"` state and keeps serving its previous
value, so content stays visible during reloads.

Example:
    ```python
    user = create_resource(fetch_user)

    Suspense(
        fallback=lambda: p("Loading..."),
        children=[div(lambda: (user() or {}).get("name", ""))],
    )
    ```

See Also:
    - [Suspense and lazy loading guide](../concepts/suspense-lazy.md)
"""

from __future__ import annotations

from typing import Any, Set

from .reactivity import SUSPENSE_CONTEXT_KEY, Signal, _get_component_ctx
from .vnode import Fragment, VNode, dynamic, h, to_text_vnode

__all__ = ["Suspense"]


class _SuspenseCollector:
    """Tracks pending resources read under one Suspense boundary."""

    __slots__ = ("_version", "_pending")

    def __init__(self) -> None:
        self._version: Signal[int] = Signal(0)
        self._pending: Set[Any] = set()

    def register(self, resource: Any) -> None:
        """Called by `Resource.__call__` when read while pending."""
        if resource in self._pending:
            return
        self._pending.add(resource)
        self._version.set(self._version.peek() + 1)

    def is_loading(self) -> bool:
        """Tracked read: True while any registered resource is loading.

        Resolved resources are pruned so a later refetch (which doesn't
        go through the pending state) can't re-trigger the boundary.
        """
        self._version.get()
        done = [r for r in self._pending if not r._loading.get()]
        for r in done:
            self._pending.discard(r)
        return bool(self._pending)


def Suspense(fallback: Any = None, children: Any = None) -> VNode:
    """Show a fallback while resources read under the boundary are pending.

    Args:
        fallback: `VNode`, string, or callable returning one of those.
            Shown while any registered resource is pending.
        children: Children rendered when nothing is pending. Resources
            called anywhere in this subtree self-register with the
            boundary while they're in their initial `"pending"` state.

    Returns:
        A component [`VNode`][wybthon.VNode] that toggles between
        fallback and children.
    """
    return h(_SuspenseComponent, {"fallback": fallback, "children": children})


def _SuspenseComponent(props: Any) -> Any:
    """Internal component backing [`Suspense`][wybthon.Suspense]."""
    collector = _SuspenseCollector()
    ctx = _get_component_ctx()
    if ctx is not None:
        ctx._set_context(SUSPENSE_CONTEXT_KEY, collector)

    def _render_children() -> VNode:
        children = props.value("children")
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    def _render_fallback() -> VNode:
        fb = props.value("fallback")
        vnode: Any
        if callable(fb) and not isinstance(fb, VNode):
            try:
                vnode = fb()
            except Exception:
                vnode = to_text_vnode("Loading...")
        else:
            vnode = fb if isinstance(fb, VNode) else to_text_vnode("" if fb is None else str(fb))
        if not isinstance(vnode, VNode):
            vnode = to_text_vnode(vnode)
        return vnode

    def render() -> VNode:
        if collector.is_loading():
            return _render_fallback()
        return _render_children()

    return dynamic(render)


_SuspenseComponent._wyb_component = True  # type: ignore[attr-defined]

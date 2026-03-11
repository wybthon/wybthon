"""Portal component for rendering children into a different DOM container."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .component import Component
from .dom import Element
from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["create_portal"]


class _PortalComponent(Component):
    """Internal component that mounts its children into a separate DOM container."""

    def __init__(self, props: Dict[str, Any]) -> None:
        super().__init__(props)
        self._portal_tree: Optional[VNode] = None
        self._portal_container: Optional[Element] = None

    def render(self) -> VNode:
        """Return an empty text node as placeholder in the original tree."""
        return to_text_vnode("")

    def on_mount(self) -> None:
        self._do_portal_render()

    def on_update(self, prev_props: Dict[str, Any]) -> None:
        self._do_portal_render()

    def _do_portal_render(self) -> None:
        from .reconciler import mount, patch

        container = self.props.get("_portal_container")
        if isinstance(container, str):
            container = Element(container, existing=True)
        self._portal_container = container

        children: List[Any] = self.props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        new_tree = Fragment(*children)

        old_tree = self._portal_tree
        self._portal_tree = new_tree

        if old_tree is None:
            mount(new_tree, container)
        else:
            patch(old_tree, new_tree, container)

    def on_unmount(self) -> None:
        if self._portal_tree is not None:
            from .reconciler import unmount

            unmount(self._portal_tree)
            self._portal_tree = None


def create_portal(children: Union[VNode, List[VNode]], container: Union[Element, str]) -> VNode:
    """Render children into a different DOM container.

    Returns a VNode that, when mounted, renders *children* into *container*
    instead of the parent component's DOM node.  Useful for modals, tooltips,
    and overlays that need to break out of their parent's DOM hierarchy.

    *container* may be an ``Element`` or a CSS selector string.
    """
    if not isinstance(children, list):
        children = [children]
    return h(_PortalComponent, {"children": children, "_portal_container": container})

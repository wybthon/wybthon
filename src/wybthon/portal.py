"""Portal component for rendering children into a different DOM container."""

from __future__ import annotations

from typing import Any, List, Optional, Union

from .reactivity import on_cleanup, on_mount, read_prop
from .vnode import Fragment, VNode, dynamic, h, to_text_vnode

__all__ = ["create_portal"]


def _PortalComponent(props: Any) -> Any:
    """Internal stateful component that mounts children into a separate container."""
    portal_tree: List[Optional[VNode]] = [None]

    def _do_render() -> None:
        from .dom import Element
        from .reconciler import mount, patch

        container = read_prop(props, "_portal_container")
        if isinstance(container, str):
            container = Element(container, existing=True)

        children = read_prop(props, "children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        new_tree = Fragment(*children)

        old_tree = portal_tree[0]
        portal_tree[0] = new_tree

        if old_tree is None:
            mount(new_tree, container)
        else:
            patch(old_tree, new_tree, container)

    on_mount(_do_render)

    def _cleanup() -> None:
        if portal_tree[0] is not None:
            from .reconciler import unmount

            unmount(portal_tree[0])
            portal_tree[0] = None

    on_cleanup(_cleanup)

    def render() -> VNode:
        # Reading children inside the reactive hole tracks the children
        # signal so the portal re-renders into its container when the
        # parent updates them.
        _ = read_prop(props, "children")
        if portal_tree[0] is not None:
            _do_render()
        return to_text_vnode("")

    return dynamic(render)


_PortalComponent._wyb_component = True  # type: ignore[attr-defined]


def create_portal(children: Union[VNode, List[VNode]], container: Any) -> VNode:
    """Render children into a different DOM container.

    Returns a VNode that, when mounted, renders *children* into *container*
    instead of the parent component's DOM node.  Useful for modals,
    tooltips, and overlays that need to break out of their parent's DOM
    hierarchy.

    *container* may be an ``Element`` or a CSS selector string.
    """
    if not isinstance(children, list):
        children = [children]
    return h(_PortalComponent, {"children": children, "_portal_container": container})

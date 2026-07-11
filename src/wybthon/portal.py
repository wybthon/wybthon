"""Portal component for rendering children into a different DOM container.

Use [`Portal`][wybthon.Portal] to render content outside of the
current component's DOM ancestor while keeping it part of the same
reactive ownership tree (so signals, effects, and context still work).
Common use cases include modals, tooltips, and toast notifications.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from .reactivity import on_cleanup, on_mount
from .vnode import Fragment, VNode, dynamic, h, to_text_vnode

__all__ = ["Portal"]


def _PortalComponent(props: Any) -> Any:
    """Internal stateful component that mounts children into another container."""
    portal_tree: List[Optional[VNode]] = [None]

    def _resolve_container_id(container: Any) -> int:
        from .dom import Element

        if isinstance(container, int):
            return container
        if isinstance(container, str):
            container = Element(container, existing=True)
        return container.node_id

    def _do_render() -> None:
        from .reconciler import mount, patch

        container_id = _resolve_container_id(props.value("mount"))

        children = props.value("children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        new_tree = Fragment(*children)

        old_tree = portal_tree[0]
        portal_tree[0] = new_tree

        if old_tree is None:
            mount(new_tree, container_id)
        else:
            patch(old_tree, new_tree, container_id)

    on_mount(_do_render)

    def _cleanup() -> None:
        if portal_tree[0] is not None:
            from .reconciler import unmount

            unmount(portal_tree[0])
            portal_tree[0] = None

    on_cleanup(_cleanup)

    def render() -> VNode:
        _ = props.value("children")
        if portal_tree[0] is not None:
            _do_render()
        return to_text_vnode("")

    return dynamic(render)


_PortalComponent._wyb_component = True  # type: ignore[attr-defined]


def Portal(children: Union[VNode, List[VNode], None] = None, mount: Any = "body") -> VNode:
    """Render children into a different DOM container.

    Matches SolidJS's `<Portal mount={...}>`. The children mount into
    `mount` (by default `document.body`) while remaining linked to the
    surrounding component's reactive scope, so signals, context, and
    lifecycle hooks still apply.

    Args:
        children: A single [`VNode`][wybthon.VNode] or a list of them.
        mount: The target container: an [`Element`][wybthon.Element]
            instance, a CSS selector string, or a kernel node id.
            Defaults to `"body"`.

    Returns:
        A component `VNode` whose children render inside `mount`.

    Example:
        ```python
        Show(
            when=show_modal,
            children=lambda: Portal(
                div(p("Modal content"), class_="modal"),
                mount="#modal-root",
            ),
        )
        ```
    """
    if children is None:
        children = []
    elif not isinstance(children, list):
        children = [children]
    return h(_PortalComponent, {"children": children, "mount": mount})

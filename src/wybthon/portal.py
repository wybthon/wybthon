"""Portal component for rendering children into a different DOM container.

Use [`Portal`][wybthon.Portal] to render content outside of the
current component's DOM ancestor while keeping it part of the same
reactive ownership tree (so signals, effects, and context still work).
Common use cases include modals, tooltips, and toast notifications.
"""

from __future__ import annotations

from typing import Any

from .component import component
from .kernel import OP_ROOT, OP_UNROOT
from .reactivity import _core
from .reactivity._primitives import on_cleanup
from .reactivity._props import Props
from .vnode import Fragment, VNode, h, hole

__all__ = ["Portal"]


def _resolve_container_id(container: Any) -> int:
    from .dom import Element

    if isinstance(container, int):
        return container
    if isinstance(container, str):
        container = Element(container, existing=True)
    return int(container.node_id)


class _PortalProps(Props):
    children: Any = None
    mount: Any = "body"


@component
def _Portal(props: _PortalProps) -> Any:
    from . import kernel, reconciler

    if _core._server_depth:
        # Portal targets live outside the rendered container; the content
        # mounts in the browser once the page has hydrated.
        return None
    container_id = _resolve_container_id(props.mount)
    children = props.children
    tree: VNode
    if isinstance(children, VNode):
        tree = children
    elif isinstance(children, list):
        tree = Fragment(*children)
    elif callable(children):
        tree = hole(children)
    else:
        tree = Fragment()

    # The target becomes a delegation root so handlers inside the portal
    # fire even when it sits outside the render root (the kernel refcounts
    # roots, so a target that is also the app root is unaffected).
    reconciler._emit((OP_ROOT, container_id))
    # Mount under the current owner so context and disposal flow through
    # the portal exactly as they would for in-place children. The server
    # never renders portal content, so hydration creates it.
    claiming = kernel.claiming
    kernel.claiming = False
    try:
        reconciler.mount(tree, container_id)
    finally:
        kernel.claiming = claiming

    def cleanup() -> None:
        reconciler._unmount(tree)
        reconciler._emit((OP_UNROOT, container_id))

    on_cleanup(cleanup)
    return None


_Portal.__name__ = "Portal"


def Portal(children: Any = None, *, mount: Any = "body") -> VNode:
    """Render children into a different DOM container.

    Matches SolidJS's `<Portal mount={...}>`. The children mount into
    `mount` (by default `document.body`) while remaining linked to the
    surrounding component's reactive scope, so signals, context, and
    lifecycle hooks still apply, and they're removed when the portal
    unmounts.

    Args:
        children: A VNode, a list of VNodes, or a zero-arg callable
            (rendered as a reactive hole).
        mount: The target container: an [`Element`][wybthon.Element]
            instance, a CSS selector string, or a kernel node id.
            Defaults to `"body"`.

    Returns:
        A component `VNode` whose children render inside `mount`.

    Note:
        A portal renders nothing during a server render. Its children
        mount in the browser once the page has hydrated.

    Example:
        ```python
        Show(
            show_modal,
            lambda: Portal(
                div(p("Modal content"), class_="modal"),
                mount="#modal-root",
            ),
        )
        ```
    """
    return h(_Portal, {"children": children, "mount": mount})

"""`Suspense` component for rendering fallback UI during async loading.

[`Suspense`][wybthon.Suspense] subscribes to one or more
[`Resource`][wybthon.Resource]s and shows a fallback while any of
them are loading. Set `keep_previous=True` to keep showing the
previously-resolved children when refetching.

See Also:
    - [Suspense and lazy loading guide](../concepts/suspense-lazy.md)
"""

from __future__ import annotations

from typing import Any, List

from .reactivity import create_signal, read_prop
from .vnode import Fragment, VNode, dynamic, to_text_vnode

__all__ = ["Suspense"]


def Suspense(props: Any) -> Any:
    """Render a fallback while one or more resources are loading.

    Args:
        props: The component's props with the following keys:

            - `resources` / `resource`: A single
              [`Resource`][wybthon.Resource] or a list of resources.
              When omitted, the component just renders its children.
            - `fallback`: `VNode`, string, or callable returning
              one of those. Shown while any resource is loading.
            - `keep_previous` (`bool`, default `False`): When `True`,
              show previously-resolved children during refetches
              instead of replacing them with the fallback.
            - `children`: Children rendered when no resource is
              loading.

    Returns:
        A reactive [`VNode`][wybthon.VNode] subtree that toggles
        between fallback and children.
    """
    has_completed, set_completed = create_signal(False)

    def _normalize_resources(p: Any) -> List[Any]:
        res = read_prop(p, "resources")
        if res is None:
            res = read_prop(p, "resource")
        if res is None:
            return []
        if not isinstance(res, list):
            res = [res]
        return [r for r in res if r is not None]

    def _is_loading(resources: List[Any]) -> bool:
        for r in resources:
            try:
                loading_sig = getattr(r, "loading", None)
                if loading_sig is None:
                    continue
                if callable(getattr(loading_sig, "get", None)) and loading_sig.get():
                    return True
            except Exception:
                continue
        return False

    def _render_children(p: Any) -> VNode:
        children = read_prop(p, "children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    def _render_fallback(p: Any) -> VNode:
        fb = read_prop(p, "fallback")
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
        resources = _normalize_resources(props)
        if not resources:
            return _render_children(props)
        keep_previous = bool(read_prop(props, "keep_previous", False))
        loading = _is_loading(resources)
        if loading:
            if keep_previous and has_completed():
                return _render_children(props)
            return _render_fallback(props)
        if not has_completed():
            set_completed(True)
        return _render_children(props)

    return dynamic(render)


Suspense._wyb_component = True  # type: ignore[attr-defined]

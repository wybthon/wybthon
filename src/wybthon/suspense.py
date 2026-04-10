"""Suspense function component for rendering fallback UI during async loading."""

from __future__ import annotations

from typing import Any, List

from .reactivity import create_signal
from .vnode import Fragment, VNode, to_text_vnode

__all__ = ["Suspense"]


def Suspense(props: Any) -> Any:
    """Render a fallback while one or more resources are loading.

    Props:
      - resources | resource: Resource or list of Resources
      - fallback: VNode | str | callable returning VNode/str
      - keep_previous: bool (default False)
      - children: child VNodes to render when not loading
    """
    has_completed, set_completed = create_signal(False)

    def _normalize_resources(p: Any) -> List[Any]:
        res = p.get("resources")
        if res is None and "resource" in p:
            res = [p.get("resource")]
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
        children: List[Any] = p.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    def _render_fallback(p: Any) -> VNode:
        fb = p.get("fallback")
        vnode: Any
        if callable(fb):
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
        keep_previous = bool(props.get("keep_previous", False))
        loading = _is_loading(resources)
        if loading:
            if keep_previous and has_completed():
                return _render_children(props)
            return _render_fallback(props)
        if not has_completed():
            set_completed(True)
        return _render_children(props)

    return render

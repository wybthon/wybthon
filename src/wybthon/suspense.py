"""Suspense component for rendering fallback UI during async resource loading."""

from __future__ import annotations

from typing import Any, Dict, List

from .component import Component
from .vnode import Fragment, VNode, to_text_vnode

__all__ = ["Suspense"]


class Suspense(Component):
    """Render a fallback while one or more resources are loading.

    Props:
      - resources | resource: Resource or list of Resources (objects exposing ``.loading.get()``)
      - fallback: VNode | str | callable returning VNode/str
      - keep_previous: bool (default False) -- when True, keep children visible after first
        successful load even if a subsequent reload is in-flight.
      - children: child VNodes to render when not loading
    """

    def __init__(self, props: Dict[str, Any]) -> None:
        super().__init__(props)
        self._has_completed_once: bool = False

    def render(self) -> VNode:
        """Render fallback or children based on resource loading state."""
        resources = self._normalize_resources()
        if not resources:
            return self._render_children()
        keep_previous = bool(self.props.get("keep_previous", False))
        is_loading = self._is_loading(resources)
        if is_loading:
            if keep_previous and self._has_completed_once:
                return self._render_children()
            return self._render_fallback()
        self._has_completed_once = True
        return self._render_children()

    def _normalize_resources(self) -> List[Any]:
        """Normalize the resources prop(s) to a flat list."""
        res = self.props.get("resources")
        if res is None and "resource" in self.props:
            res = [self.props.get("resource")]
        if res is None:
            return []
        if not isinstance(res, list):
            res = [res]
        return [r for r in res if r is not None]

    def _is_loading(self, resources: List[Any]) -> bool:
        """Return True if any resource reports loading=True."""
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

    def _render_children(self) -> VNode:
        """Render the children inside a Fragment container."""
        children: List[Any] = self.props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    def _render_fallback(self) -> VNode:
        """Render the fallback content as a VNode."""
        fb = self.props.get("fallback")
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

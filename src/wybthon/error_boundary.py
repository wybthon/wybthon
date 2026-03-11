"""ErrorBoundary component for catching render errors in subtrees."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .component import Component
from .reactivity import Signal, signal
from .vnode import Fragment, VNode, to_text_vnode

__all__ = ["ErrorBoundary"]


class ErrorBoundary(Component):
    """Component that catches errors in its subtree and renders a fallback.

    Props:
      - fallback: VNode | str | callable(error, reset) -> VNode
      - on_error: optional callback invoked with the caught exception
      - reset_key / reset_keys: when this value changes the error is auto-cleared
      - children: child VNodes to render when there is no error
    """

    def __init__(self, props: Dict[str, Any]) -> None:
        super().__init__(props)
        self._error: Signal[Optional[Any]] = signal(None)
        self._last_reset_token: str = ""

    def render(self) -> VNode:
        """Render fallback when an error is stored, otherwise children."""
        token = self._compute_reset_token()
        current_err = self._error.get()

        if token != self._last_reset_token and current_err is not None:
            self._error.set(None)
            current_err = None
        self._last_reset_token = token

        if current_err is not None:
            return self._render_fallback(current_err)

        return self._render_children()

    def reset(self) -> None:
        """Clear the current error and re-render children."""
        self._error.set(None)

    def _compute_reset_token(self) -> str:
        """Derive a stable token from reset_keys/reset_key for auto-clear."""
        try:
            if "reset_keys" in self.props:
                rk = self.props.get("reset_keys")
            elif "reset_key" in self.props:
                rk = self.props.get("reset_key")
            else:
                return ""
            if isinstance(rk, (list, tuple)):
                return repr(tuple(rk))
            return repr(rk)
        except Exception:
            return ""

    def _render_fallback(self, err: Any) -> VNode:
        """Build the fallback VNode from the ``fallback`` prop."""
        fb = self.props.get("fallback")
        if callable(fb):
            try:
                try:
                    vnode = fb(err, self.reset)
                except TypeError:
                    vnode = fb(err)
            except Exception:
                vnode = to_text_vnode("Error rendering fallback")
        else:
            vnode = (
                fb if isinstance(fb, VNode) else to_text_vnode(str(fb) if fb is not None else "Something went wrong.")
            )
        if not isinstance(vnode, VNode):
            vnode = to_text_vnode(vnode)
        return vnode

    def _render_children(self) -> VNode:
        """Render the wrapped children inside a Fragment."""
        children: List[Any] = self.props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

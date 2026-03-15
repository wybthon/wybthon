"""ErrorBoundary function component for catching render errors in subtrees."""

from __future__ import annotations

from typing import Any, Dict, List

from .reactivity import _get_component_ctx, create_signal, get_props
from .vnode import Fragment, VNode, to_text_vnode

__all__ = ["ErrorBoundary"]


def _compute_reset_token(props: Dict[str, Any]) -> str:
    """Derive a stable token from reset_keys/reset_key for auto-clear."""
    try:
        if "reset_keys" in props:
            rk = props.get("reset_keys")
        elif "reset_key" in props:
            rk = props.get("reset_key")
        else:
            return ""
        if callable(rk):
            rk = rk()
        if isinstance(rk, (list, tuple)):
            return repr(tuple(rk))
        return repr(rk)
    except Exception:
        return ""


def _render_fallback(err: Any, props: Dict[str, Any], reset_fn: Any) -> VNode:
    """Build the fallback VNode from the ``fallback`` prop."""
    fb = props.get("fallback")
    if callable(fb):
        try:
            try:
                vnode = fb(err, reset_fn)
            except TypeError:
                vnode = fb(err)
        except Exception:
            vnode = to_text_vnode("Error rendering fallback")
    else:
        vnode = fb if isinstance(fb, VNode) else to_text_vnode(str(fb) if fb is not None else "Something went wrong.")
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)
    return vnode


def ErrorBoundary(props: Dict[str, Any]) -> Any:
    """Catch render errors in children and display a fallback.

    Props:
      - fallback: VNode | str | callable(error, reset) -> VNode
      - on_error: optional callback invoked with the caught exception
      - reset_key / reset_keys: when this value changes the error is auto-cleared
      - children: child VNodes to render when there is no error
    """
    error, set_error = create_signal(None)
    last_token: List[str] = [""]
    ctx = _get_component_ctx()
    props_getter = get_props()

    def reset() -> None:
        set_error(None)

    def _handle_error(err: Any) -> None:
        set_error(err)
        p = props_getter()
        handler = p.get("on_error")
        if callable(handler):
            try:
                handler(err)
            except Exception:
                pass

    if ctx is not None:
        ctx._error_handler = _handle_error

    def render() -> VNode:
        p = props_getter()
        err = error()

        token = _compute_reset_token(p)
        if token != last_token[0] and err is not None:
            set_error(None)
            err = None
        last_token[0] = token

        if err is not None:
            return _render_fallback(err, p, reset)

        children: List[Any] = p.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    return render

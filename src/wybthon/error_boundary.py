"""`ErrorBoundary` component for catching render errors in subtrees.

[`ErrorBoundary`][wybthon.ErrorBoundary] is a function component that
installs an error handler on its owner scope. When a child render or
effect raises, the boundary swaps in a fallback while leaving sibling
trees untouched. It is the recommended way to surface unexpected
errors without crashing the whole app.

See Also:
    - [Suspense and lazy loading guide](../concepts/suspense-lazy.md)
"""

from __future__ import annotations

from typing import Any, List

from .reactivity import _get_component_ctx, create_signal, read_prop
from .vnode import Fragment, VNode, dynamic, to_text_vnode

__all__ = ["ErrorBoundary"]


def _compute_reset_token(props: Any) -> str:
    """Derive a stable token from `reset_keys` / `reset_key` for auto-clear."""
    try:
        if "reset_keys" in props:
            rk: Any = read_prop(props, "reset_keys")
        elif "reset_key" in props:
            rk = read_prop(props, "reset_key")
        else:
            return ""
        if callable(rk):
            rk = rk()
        if isinstance(rk, (list, tuple)):
            return repr(tuple(rk))
        return repr(rk)
    except Exception:
        return ""


def _render_fallback(err: Any, props: Any, reset_fn: Any) -> VNode:
    """Build the fallback `VNode` from the boundary's `fallback` prop.

    Args:
        err: The caught exception.
        props: The boundary's prop bag.
        reset_fn: Callable that clears the error state.

    Returns:
        A `VNode` representing the fallback UI. Falls back to a text
        node when the prop is missing or when the user-supplied
        callable raises.
    """
    fb = read_prop(props, "fallback")
    if callable(fb) and not isinstance(fb, VNode):
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


def ErrorBoundary(props: Any) -> Any:
    """Catch render errors in children and display a fallback.

    Args:
        props: The component's props with the following keys:

            - `fallback`: A `VNode`, a string, or a callable
              `(error, reset) -> VNode`. The callable form may also
              accept just `(error,)`.
            - `on_error`: Optional callback invoked with the caught
              exception (errors raised inside the callback are
              swallowed).
            - `reset_key` / `reset_keys`: When this value (or
              callable result) changes, the boundary auto-clears the
              current error.
            - `children`: Children rendered when no error is active.

    Returns:
        A reactive [`VNode`][wybthon.VNode] subtree that swaps to the
        fallback whenever a child raises.
    """
    error, set_error = create_signal(None)
    last_token: List[str] = [""]
    ctx = _get_component_ctx()

    def reset() -> None:
        set_error(None)

    def _handle_error(err: Any) -> None:
        set_error(err)
        handler = read_prop(props, "on_error")
        if callable(handler):
            try:
                handler(err)
            except Exception:
                pass

    if ctx is not None:
        ctx._error_handler = _handle_error

    def render() -> VNode:
        err = error()

        token = _compute_reset_token(props)
        if token != last_token[0] and err is not None:
            set_error(None)
            err = None
        last_token[0] = token

        if err is not None:
            return _render_fallback(err, props, reset)

        children = read_prop(props, "children", [])
        if children is None:
            children = []
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    return dynamic(render)


ErrorBoundary._wyb_component = True  # type: ignore[attr-defined]

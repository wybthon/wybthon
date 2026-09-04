"""`Errored`: catch render and effect errors in a subtree.

[`Errored`][wybthon.Errored] installs an error handler on its owner
scope. When a child render, hole, or effect raises, the boundary swaps
in a fallback while leaving sibling trees untouched. It's the
recommended way to surface unexpected errors without crashing the
whole app.

Boundaries **heal automatically**: the boundary remembers which
reactive inputs the failing computation had read, and when any of them
changes it re-renders its children. A fixed `user_id`, a re-fetched
memo, or a corrected form field clears the error without an explicit
`reset()`; `reset` and `reset_on` remain for manual retries.

Example:
    ```python
    Errored(
        lambda: Dashboard(),
        fallback=lambda err, reset: div(
            p("Something went wrong: ", str(err)),
            button("Retry", on_click=lambda e: reset()),
        ),
    )
    ```

See Also:
    - [Async and loading guide](../concepts/async-loading.md)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .reactivity import _core
from .reactivity._core import Computation, Signal, _positional_count
from .reactivity._props import Props
from .vnode import Fragment, VNode, h, to_text_vnode

__all__ = ["Errored"]


def Errored(
    children: Any = None,
    *,
    fallback: Any = None,
    on_error: Callable[[BaseException], Any] | None = None,
    reset_on: Any = None,
) -> VNode:
    """Catch errors raised while rendering `children` and show a fallback.

    Args:
        children: Content rendered while no error is active: a VNode, a
            zero-arg callable, or a list of either.
        fallback: A VNode, a string, or a callable
            `(error, reset) -> VNode` (or `(error) -> VNode`). `reset()`
            clears the error and re-renders the children.
        on_error: Optional callback invoked with the caught exception.
        reset_on: An accessor (or plain value) whose change clears the
            current error automatically, for example the current route.

    Returns:
        A component [`VNode`][wybthon.VNode] that swaps to the fallback
        whenever a descendant raises.
    """
    return h(_Errored, {"children": children, "fallback": fallback, "on_error": on_error, "reset_on": reset_on})


def _render_content(value: Any) -> VNode:
    if isinstance(value, VNode):
        return value
    if value is None:
        return Fragment()
    if isinstance(value, list):
        items = [v() if callable(v) and not isinstance(v, VNode) else v for v in value]
        return Fragment(*items)
    if callable(value):
        return _render_content(value())
    return to_text_vnode(value)


def _render_fallback(fb: Any, err: BaseException, reset: Callable[[], None]) -> VNode:
    vnode: Any
    if callable(fb) and not isinstance(fb, VNode):
        try:
            n = _positional_count(fb)
            if n == 0:
                vnode = fb()
            elif n == 1:
                vnode = fb(err)
            else:
                vnode = fb(err, reset)
        except Exception:
            vnode = to_text_vnode("Error rendering fallback")
    elif isinstance(fb, VNode):
        vnode = fb
    else:
        vnode = to_text_vnode(str(fb) if fb is not None else "Something went wrong.")
    if isinstance(vnode, list):
        vnode = Fragment(*vnode)
    if not isinstance(vnode, VNode):
        vnode = to_text_vnode(vnode)
    return vnode


def _Errored(props: Props) -> Any:
    # Framework-internal signal: the handler runs inside whatever tracking
    # scope raised, so it bypasses the dev-mode write guard, and it
    # reveals immediately even while a transition holds data.
    error: Signal[BaseException | None] = Signal(None)
    children = props.raw("children")
    fallback = props.raw("fallback")
    on_error = props.raw("on_error")
    reset_on = props.reset_on
    last_token: list[Any] = [_UNSET]
    # Sources the failing computation had read when it raised. The
    # boundary heals (re-renders its children) when any of them changes,
    # so a fixed input clears the error without an explicit reset.
    heal_sources: list[Any] = []

    def reset() -> None:
        error._set(None, _core._O_REVEAL)

    def handle(err: BaseException, comp: Any) -> None:
        heal_sources[:] = _leaf_inputs(comp)
        error._set(err, _core._O_REVEAL)
        if callable(on_error):
            try:
                on_error(err)
            except Exception:
                pass

    owner = _core._current_owner
    if owner is not None:
        owner._error_handler = handle

    def render() -> VNode:
        err = error()
        token = reset_on()
        if last_token[0] is _UNSET:
            last_token[0] = token
        elif token != last_token[0]:
            last_token[0] = token
            if err is not None:
                error._set(None, _core._O_REVEAL)
                err = None
        if err is not None:
            if heal_sources:
                _arm_healing(list(heal_sources), reset)
            return _render_fallback(fallback, err, reset)
        return _render_content(children)

    return render


def _leaf_inputs(comp: Any) -> list[Any]:
    """Return the signals the failed computation depended on, through any memos.

    The memos themselves may live inside the subtree the fallback
    replaces (a component's async memo), so the boundary watches the
    inputs those memos read instead: when one changes, re-rendering the
    children recreates the memos with the new input.
    """
    leaves: list[Any] = []
    seen: set[int] = set()
    stack = [comp]
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        srcs = getattr(node, "_sources", None)
        if isinstance(node, Computation):
            if srcs:
                stack.extend(srcs)
        else:
            leaves.append(node)
    return leaves


def _arm_healing(sources: list[Any], reset: Callable[[], None]) -> None:
    """Reset the boundary when any input of the failed computation changes.

    Owned by the boundary's render hole, so it's disposed as soon as the
    boundary re-renders (whether healed or failed again).
    """

    def watch() -> None:
        for src in sources:
            _core._track_source(src)

    comp = Computation(watch, kind=_core._K_RENDER, apply=lambda _v: reset(), defer=True, pass_prev=False)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    comp._update_if_necessary()


_Errored.__name__ = "Errored"
_UNSET = object()

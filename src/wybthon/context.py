"""Context system for passing values through the component tree.

Context values are stored on the reactive ownership tree.  ``use_context``
walks up the owner chain to find the nearest Provider, eliminating the
need for a separate render-time stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .vnode import Fragment

__all__ = ["Context", "create_context", "use_context", "Provider"]

_next_context_id = 0


@dataclass(frozen=True)
class Context:
    """Opaque context identifier and default value container."""

    id: int
    default: Any


def create_context(default: Any) -> Context:
    """Create a new `Context` with a unique identifier and default value."""
    global _next_context_id
    _next_context_id += 1
    return Context(id=_next_context_id, default=default)


def use_context(ctx: Context) -> Any:
    """Read the current value for *ctx* from the ownership tree.

    Walks up the owner chain looking for the nearest Provider that set
    a value for this context.  Falls back to the context's default.
    """
    from .reactivity import _current_owner

    owner = _current_owner
    while owner is not None:
        if owner._context_map is not None and ctx.id in owner._context_map:
            return owner._context_map[ctx.id]
        owner = owner._parent
    return ctx.default


def Provider(props: Dict[str, Any]) -> Any:
    """Context provider component (function component).

    Renders its children transparently.  The reconciler sets the context
    value on this component's ownership scope so that descendants can
    find it via ``use_context``.

    Children are rendered through a reactive hole so that updates from
    the parent (e.g. a router swapping the matched route component) flow
    into the subtree even though the Provider body runs only once.

    Props:
      - context: Context
      - value: Any
      - children: VNode or list of VNodes
    """

    def render() -> Any:
        children = props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return Fragment(*children)

    return render


Provider._wyb_provider = True  # type: ignore[attr-defined]

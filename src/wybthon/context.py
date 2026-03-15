"""Tiny context system for passing values through the component tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .vnode import Fragment

__all__ = ["Context", "create_context", "use_context", "Provider"]

_next_context_id = 0
_context_stack: List[Dict[int, Any]] = []


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


def _current_map() -> Dict[int, Any]:
    """Return the current effective context mapping for the render scope."""
    if _context_stack:
        return _context_stack[-1]
    return {}


def use_context(ctx: Context) -> Any:
    """Read the current value for `ctx`, or its default if not provided."""
    mapping = _current_map()
    return mapping.get(ctx.id, ctx.default)


def push_provider_value(ctx: Context, value: Any) -> None:
    """Push a new provider value for `ctx` onto the context stack."""
    base = _current_map().copy()
    base[ctx.id] = value
    _context_stack.append(base)


def pop_provider_value() -> None:
    """Pop the latest provider scope from the context stack if present."""
    if _context_stack:
        _context_stack.pop()


def Provider(props: Dict[str, Any]) -> Any:
    """Context provider component (function component).

    Renders its children transparently.  The reconciler handles pushing
    and popping context values around this component's subtree mount.

    Props:
      - context: Context
      - value: Any
      - children: VNode or list of VNodes
    """
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return Fragment(*children)


Provider._wyb_provider = True  # type: ignore[attr-defined]

"""Tiny context system for passing values through the component tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

__all__ = ["Context", "create_context", "use_context", "Provider"]

# Avoid importing browser/DOM-dependent Component in non-browser/test environments
try:  # pragma: no cover - import guard behavior varies by environment
    from .component import Component as _Component
except Exception:  # pragma: no cover
    _Component = None  # type: ignore


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


class Provider(_Component if _Component is not None else object):  # type: ignore[misc]
    """Context provider component.

    Props:
      - context: Context
      - value: Any
      - children: VNode or list of VNodes
    """

    def render(self):
        """Render passthrough children; VDOM manages push/pop of context value."""
        # Provider render is a simple passthrough; the VDOM is responsible for
        # pushing/popping the provided value around this component's subtree.
        children = self.props.get("children")
        return children

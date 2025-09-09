from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Avoid importing browser/DOM-dependent Component in non-browser/test environments
try:  # pragma: no cover - import guard behavior varies by environment
    from .component import Component as _Component  # type: ignore
except Exception:  # pragma: no cover
    _Component = None  # type: ignore


_next_context_id = 0
_context_stack: List[Dict[int, Any]] = []


@dataclass(frozen=True)
class Context:
    id: int
    default: Any


def create_context(default: Any) -> Context:
    global _next_context_id
    _next_context_id += 1
    return Context(id=_next_context_id, default=default)


def _current_map() -> Dict[int, Any]:
    if _context_stack:
        return _context_stack[-1]
    return {}


def use_context(ctx: Context) -> Any:
    mapping = _current_map()
    return mapping.get(ctx.id, ctx.default)


def push_provider_value(ctx: Context, value: Any) -> None:
    base = _current_map().copy()
    base[ctx.id] = value
    _context_stack.append(base)


def pop_provider_value() -> None:
    if _context_stack:
        _context_stack.pop()


class Provider(_Component if _Component is not None else object):  # type: ignore[misc]
    """Context provider component.

    Props:
      - context: Context
      - value: Any
      - children: VNode or list of VNodes
    """

    def render(self):  # type: ignore[override]
        # Provider render is a simple passthrough; the VDOM is responsible for
        # pushing/popping the provided value around this component's subtree.
        children = self.props.get("children")
        return children

"""Context system for passing values through the component tree.

Context values are stored on the reactive ownership tree.  ``use_context``
walks up the owner chain to find the nearest Provider, eliminating the
need for a separate render-time stack.

The provider's ``value`` is wrapped in a ``Signal``, so descendants
that read it inside a tracking scope (e.g. a reactive hole or
``create_effect``) automatically re-run when the provider's value
changes — without re-mounting any subtrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["Context", "create_context", "use_context", "Provider"]

_next_context_id = 0


@dataclass(frozen=True)
class Context:
    """Opaque context identifier and default value container."""

    id: int
    default: Any


def create_context(default: Any) -> Context:
    """Create a new ``Context`` with a unique identifier and default value."""
    global _next_context_id
    _next_context_id += 1
    return Context(id=_next_context_id, default=default)


def use_context(ctx: Context) -> Any:
    """Read the current value for *ctx* from the ownership tree.

    Walks up the owner chain looking for the nearest Provider that set
    a value for this context.  Falls back to the context's default.

    The returned value is unwrapped from the provider's signal — so
    callers receive the *current* value.  When called inside a
    tracking scope (e.g. a reactive hole or effect), the dependency
    on the provider signal is recorded so the scope re-runs when the
    provider updates.
    """
    from .reactivity import Signal, _current_owner

    owner = _current_owner
    while owner is not None:
        if owner._context_map is not None and ctx.id in owner._context_map:
            stored = owner._context_map[ctx.id]
            if isinstance(stored, Signal):
                return stored.get()
            return stored
        owner = owner._parent
    return ctx.default


def Provider(props: Any) -> Any:
    """Context provider component.

    Renders its children transparently.  The reconciler stores
    ``value`` as a ``Signal`` on this component's ownership scope so
    that descendants can find it via :func:`use_context` and react to
    updates fine-grainedly.

    Children are wrapped in a reactive hole so updates from the
    parent (e.g. a router swapping the matched route component) flow
    into the subtree even though the Provider body runs only once.

    Props:
      - context: Context
      - value: Any
      - children: VNode or list of VNodes
    """
    from .reactivity import ReactiveProps
    from .vnode import Fragment, dynamic

    if isinstance(props, ReactiveProps):
        children_getter = props.children
    else:

        def children_getter() -> Any:
            return props.get("children", [])

    def _render() -> Any:
        kids = children_getter()
        if kids is None:
            kids = []
        if not isinstance(kids, list):
            kids = [kids]
        return Fragment(*kids)

    return dynamic(_render)


Provider._wyb_provider = True  # type: ignore[attr-defined]
Provider._wyb_component = True  # type: ignore[attr-defined]

"""Context system for passing values through the component tree.

Context values are stored on the reactive ownership tree.
[`use_context`][wybthon.use_context] walks up the owner chain to find
the nearest [`Provider`][wybthon.Provider], eliminating the need for a
separate render-time stack.

The provider's `value` is wrapped in a [`Signal`][wybthon.Signal], so
descendants that read it inside a tracking scope (e.g. a reactive hole
or [`create_effect`][wybthon.create_effect]) automatically re-run when
the provider's value changes — without re-mounting any subtrees.

See Also:
    - [Components guide](../concepts/components.md)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["Context", "create_context", "use_context", "Provider"]

_next_context_id = 0


@dataclass(frozen=True)
class Context:
    """Opaque context identifier paired with a default value.

    Returned by [`create_context`][wybthon.create_context]. Treat the
    object as opaque — pass it to a [`Provider`][wybthon.Provider] and
    to [`use_context`][wybthon.use_context] but do not rely on its
    fields.

    Attributes:
        id: Process-unique integer used as the storage key on owner
            scopes.
        default: Value returned by `use_context` when no enclosing
            provider is found.
    """

    id: int
    default: Any


def create_context(default: Any) -> Context:
    """Create a new [`Context`][wybthon.Context] with the given default value.

    Args:
        default: Value returned by [`use_context`][wybthon.use_context]
            when no provider is found above the consumer.

    Returns:
        A fresh `Context` token. Each call returns a context with a
        unique id, even when `default` is the same.
    """
    global _next_context_id
    _next_context_id += 1
    return Context(id=_next_context_id, default=default)


def use_context(ctx: Context) -> Any:
    """Read the current value for `ctx` from the ownership tree.

    Walks up the owner chain looking for the nearest provider that
    stored a value for this context. The returned value is unwrapped
    from the provider's signal so callers always observe the current
    value. When invoked inside a tracking scope (a reactive hole or
    effect), the dependency on the provider signal is recorded so the
    scope re-runs whenever the provider updates.

    Args:
        ctx: The context token created by
            [`create_context`][wybthon.create_context].

    Returns:
        The nearest provider's current value, or
        `ctx.default` when no provider exists above the caller.
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

    Renders its children transparently. The reconciler stores `value`
    as a [`Signal`][wybthon.Signal] on this component's ownership
    scope so that descendants can find it via
    [`use_context`][wybthon.use_context] and react to updates with
    fine-grained precision.

    Children are wrapped in a reactive hole so updates from the parent
    (for example a router swapping the matched route component) flow
    into the subtree even though the provider body itself runs only
    once.

    Args:
        props: The component's props with the following keys:

            - `context` ([`Context`][wybthon.Context]): The context
              being provided.
            - `value`: The current value to expose to descendants.
            - `children`: A `VNode` or list of `VNode`s rendered
              transparently.

    Returns:
        A reactive [`VNode`][wybthon.VNode] subtree containing the
        provider's children.
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

"""Context: pass values down the tree without threading props.

A [`Context`][wybthon.Context] is created with
[`create_context`][wybthon.create_context] and **is its own provider**:
call it with a `value` and children to expose that value to every
descendant, and read it with [`use_context`][wybthon.use_context].

Values live on the reactive ownership tree, so `use_context` works
anywhere an owner exists: component bodies, effects, memos, and list
rows. The value is handed to consumers exactly as provided, so pass a
signal (or any accessor) when consumers should react to changes.

Example:
    ```python
    Theme: Context[Accessor[str]] = create_context()

    @component
    def Button():
        theme = use_context(Theme)
        return button("Hi", class_=lambda: f"btn-{theme()}")

    @component
    def App():
        theme, set_theme = create_signal("light")
        return Theme(theme, Button())   # value first, then children
    ```
"""

from __future__ import annotations

from typing import Any

from .reactivity import _core
from .reactivity._props import Props
from .vnode import VNode, h

__all__ = ["Context", "ContextNotFoundError", "create_context", "use_context"]

_MISSING = object()


class ContextNotFoundError(LookupError):
    """Raised by [`use_context`][wybthon.use_context] when no provider is found and no default exists."""


class Context[T]:
    """A context token that also acts as its provider component.

    Created by [`create_context`][wybthon.create_context]. Calling the
    context with a value and children returns a provider `VNode`:

    ```python
    Theme(value, *children)
    Theme("dark", App())
    Theme(lambda: theme(), App())     # reactive value
    ```

    Attributes:
        default: Value returned by `use_context` when no provider is
            found, if one was declared.
        name: Optional label for diagnostics.
    """

    __slots__ = ("default", "name", "_id")

    _counter = 0

    def __init__(self, default: Any = _MISSING, name: str | None = None) -> None:
        self.default = default
        self.name = name
        Context._counter += 1
        self._id = Context._counter

    @property
    def has_default(self) -> bool:
        """Whether the context was created with a default value."""
        return self.default is not _MISSING

    def __call__(self, value: Any, *children: Any) -> VNode:
        """Return a provider `VNode` exposing `value` to `children`."""
        return h(_provider, {"context": self, "value": value, "children": list(children)})

    def __repr__(self) -> str:
        return f"Context({self.name or self._id})"

    __hash__ = object.__hash__


def create_context[T](default: Any = _MISSING, *, name: str | None = None) -> Context[T]:
    """Create a [`Context`][wybthon.Context].

    Args:
        default: Optional value returned by `use_context` when no
            provider is above the reader. Without one, reading outside
            a provider raises
            [`ContextNotFoundError`][wybthon.ContextNotFoundError].
        name: Optional label for diagnostics.

    Returns:
        A new `Context`; call it to provide, pass it to `use_context` to read.
    """
    return Context(default, name)


def use_context[T](ctx: Context[T]) -> T:
    """Read the nearest provided value for `ctx`.

    Walks up the ownership tree from the active scope and returns the
    value exactly as the provider received it: a signal or accessor
    stays a signal or accessor (call it where you need the value), a
    static value is returned directly.

    Raises:
        ContextNotFoundError: No provider is above the caller and the
            context has no default.
    """
    owner = _core._current_owner
    while owner is not None:
        cm = owner._context_map
        if cm is not None and ctx in cm:
            return cm[ctx]
        owner = owner._parent
    if ctx.default is _MISSING:
        raise ContextNotFoundError(
            f"use_context({ctx!r}) found no provider above the caller and the context has no default."
        )
    return ctx.default


def _provider(props: Props) -> Any:
    """Internal provider component: stores `value` on its own owner scope."""
    owner = _core._current_owner
    assert owner is not None
    owner._set_context(props.raw("context"), props.raw("value"))
    kids = props.children
    return lambda: kids()


_provider.__name__ = "Provider"

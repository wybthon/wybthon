"""Run-time support for compiled modules (see [`wybthon.compiler`][wybthon.compiler]).

The compiler imports this module into every module it rewrites, as
`__wybthon__`, and calls these helpers from the code it generates.
Application code never uses them directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .reactivity._core import _Getter as getter
from .reactivity._core import _positional_count
from .templates import Precompiled as template
from .templates import formatted
from .vnode import Node

__all__ = ["getter", "template", "call", "content", "fmt", "formatted", "is_component", "props"]


def is_component(fn: Any) -> bool:
    """Whether calling `fn` in a template builds a component (it takes getters for its props).

    True for `@component` functions and for every built-in that renders
    markup (`Show`, `For`, `Loading`, a context, `Link`, ...): they're
    marked with a `__wybthon_component__` attribute.
    """
    return getattr(fn, "__wybthon_component__", False) is True


def call(fn: Any, deferred: Callable[[], Any], prepared: Callable[[], Any]) -> Any:
    """Evaluate a call in a template's child position.

    `prepared` calls `fn` with each dynamic argument as a getter;
    `deferred` makes the original call. A component is built now with the
    prepared arguments, so it reads its props through getters, as a JSX
    component does. Any other callable becomes a reactive expression
    that makes the whole call, as a function call in JSX does.
    """
    if getattr(fn, "__wybthon_component__", False) is True:
        return prepared()
    return getter(deferred)


def content(build: Callable[[], Any]) -> Callable[..., Any]:
    """A flow control's lazy content: a capitalized call the compiler deferred until its branch shows.

    The call usually builds a component, whose node is the content. It
    may instead build a callable, such as an instance of a class with
    `__call__`, that the flow control would have called with its
    arguments (`Show`'s accessor, `Errored`'s error and reset); that
    callable receives them, as many as it takes.
    """

    def lazy(*args: Any) -> Any:
        value = build()
        if type(value) is getter:
            # In a template the call was dispatched, and a call that doesn't
            # build a component came back as an expression: its value is the
            # content, as a branch's slot is (see `_regions`).
            value = value.fn()
        if not args or not callable(value) or isinstance(value, Node):
            return value
        count = _positional_count(value)
        return value(*args) if count < 0 else value(*args[:count])

    return lazy


def props[F: Callable[..., Any]](body: Callable[..., Any]) -> Callable[[F], F]:
    """Attach a component's compiled body to the function whose signature declares its props.

    The compiler keeps an `@component` function's signature on the
    original `def` (emptied) and moves its body, with every parameter
    read rewritten into a props read, to a function of one argument, the
    props object. `@component` finds the body here.
    """

    def mark(signature: F) -> F:
        signature.__wybthon_body__ = body  # type: ignore[attr-defined]
        return signature

    return mark


def fmt(value: Any, conversion: str | None, spec: str) -> str:
    """Format an interpolation's value with its conversion and format spec, as a t-string would."""
    if conversion == "r":
        value = repr(value)
    elif conversion == "s":
        value = str(value)
    elif conversion == "a":
        value = ascii(value)
    if value is None:
        return ""
    return format(value, spec)

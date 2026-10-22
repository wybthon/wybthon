"""Run-time support for compiled modules (see [`wybthon.compiler`][wybthon.compiler]).

The compiler imports this module into every module it rewrites, as
`__wybthon__`, and calls these helpers from the code it generates.
Application code never uses them directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .reactivity._core import _Getter as getter
from .templates import Precompiled as template

__all__ = ["getter", "template", "call", "fmt", "is_component"]


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

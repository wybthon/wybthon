"""The `@component` decorator and the `Component` type it produces.

Wybthon components **run once**: the body executes a single time when
the component mounts and returns a VNode tree. Every parameter is bound
to a [`Prop`][wybthon.Prop] accessor; call it to read the current value
(tracked), or embed it in the returned tree to create a reactive hole.
Parents update a mounted component by passing new props, which flow
into the same accessors; the body never re-runs.

Authoring:

- **Named parameters** (the common case). Each parameter becomes a
  `Prop`. Declare defaults with [`prop`][wybthon.prop] so the type is
  `Prop[T]`; a plain default also works when you don't need the type.
- **`**rest`**. Undeclared props arrive as `Prop`s in `rest`; forward
  them with `div(**rest)` or [`merge`][wybthon.merge].
- **Single `props` parameter** (a lone positional parameter, or one
  annotated `Props`). The function receives the whole
  [`Props`][wybthon.Props] mapping.

Calling a component with keyword arguments returns a `VNode`
(`Counter(initial=5)`), so trees compose like any other element.

Example:
    ```python
    @component
    def Counter(initial: Prop[int] = prop(0), label: Prop[str] = prop("Count")):
        count, set_count = create_signal(initial.peek())
        return div(
            p(label, ": ", count),
            button("+", on_click=lambda e: set_count(lambda n: n + 1)),
        )

    render(Counter(initial=10), "#app")
    ```
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from .reactivity._props import Props, default_value
from .vnode import VNode, h

__all__ = ["component", "Component"]


class _ParamPlan:
    """How to bind a `Props` mapping to a component function's parameters."""

    __slots__ = ("names", "defaults", "var_keyword", "takes_props")

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.names: tuple[str, ...] = ()
        self.defaults: dict[str, Any] = {}
        self.var_keyword: bool = False
        self.takes_props: bool = False
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            self.takes_props = True
            return
        names: list[str] = []
        positional_required = 0
        for name, param in sig.parameters.items():
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                self.var_keyword = True
                continue
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                continue
            names.append(name)
            if param.default is not inspect.Parameter.empty:
                self.defaults[name] = default_value(param.default)
            elif param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                positional_required += 1
                ann = param.annotation
                if ann is Props or (isinstance(ann, str) and ann.split(".")[-1] == "Props"):
                    self.takes_props = True
        self.names = tuple(names)
        # `def Card(props): ...` receives the whole mapping; a single
        # annotated parameter such as `def Card(title: Prop[str])` is a prop.
        if len(names) == 1 and positional_required == 1 and not self.var_keyword:
            only = sig.parameters[names[0]]
            if only.annotation is inspect.Parameter.empty and names[0] == "props":
                self.takes_props = True


class Component:
    """A run-once component produced by [`component`][wybthon.component].

    Instances are callable: `MyComponent(child, other, key=value)` returns
    a [`VNode`][wybthon.VNode] with the positional arguments as
    `children`. The reconciler invokes the wrapped function once per
    mount through `_render`.
    """

    __name__: str
    __qualname__: str

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self._plan = _ParamPlan(fn)
        functools.update_wrapper(self, fn, updated=())

    def __call__(self, *children: Any, **props: Any) -> VNode:
        """Return a `VNode` for this component with `children` as the `children` prop."""
        all_props: dict[str, Any] = dict(props)
        if children:
            all_props["children"] = list(children)
        return h(self, all_props)

    @property
    def defaults(self) -> dict[str, Any]:
        """Declared parameter defaults (with `prop()` markers unwrapped)."""
        return self._plan.defaults

    def _render(self, props: Props) -> Any:
        """Invoke the body once with `Prop` accessors bound to its parameters."""
        plan = self._plan
        if plan.takes_props:
            return self.fn(props)
        kwargs: dict[str, Any] = {name: props[name] for name in plan.names}
        if plan.var_keyword:
            declared = plan.names
            for key in props:
                if key not in declared and key != "key":
                    kwargs[key] = props[key]
        return self.fn(**kwargs)

    def __repr__(self) -> str:
        return f"<component {self.__qualname__}>"


def component(fn: Callable[..., Any]) -> Component:
    """Declare a function as a run-once Wybthon component.

    Each parameter of `fn` becomes a [`Prop`][wybthon.Prop] accessor.
    The decorated object is a [`Component`][wybthon.Component]: calling
    it with children and keyword props returns a `VNode`.

    Args:
        fn: The component body. Runs once per mount and returns a
            `VNode`, a string, a list, or a reactive expression.

    Returns:
        A `Component`.

    Example:
        ```python
        @component
        def Greeting(name: Prop[str] = prop("world")):
            return p("Hello, ", name, "!")

        Greeting(name="Ada")           # -> VNode
        Greeting(name=lambda: user())  # reactive: updates when user() changes
        ```
    """
    if isinstance(fn, Component):
        return fn
    return Component(fn)

"""The `@component` decorator and the `Component` type it produces.

Wybthon components **run once**: the body executes a single time when
the component mounts and returns a tree. Inputs are declared on a
[`Props`][wybthon.Props] class and arrive as one typed parameter, the
counterpart of Solid's `props` object:

```python
class CounterProps(Props):
    label: Prop[str] = prop(default="Count")
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())
    return div(
        p(props.label, ": ", count),
        button("+", on_click=lambda: set_count(lambda n: n + 1)),
    )


render(Counter(initial=10), "#app")
```

Calling a component with keyword props returns a node. Type checkers
see the call as constructing the props class, so missing, mistyped, and
unknown props are errors without a plugin. A component with no inputs
takes no parameters.

Children are the `children` prop. Pass them as a keyword, or use item
syntax on the call: `Card(title="Hi")[h2("Body"), p("More")]`. Declare
them with [`ParentProps`][wybthon.ParentProps].
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, overload

from . import _warnings
from .reactivity._props import Props
from .vnode import VNode, flatten_children

__all__ = ["component", "Component"]


class Component:
    """A run-once component produced by [`component`][wybthon.component].

    Calling it returns a [`VNode`][wybthon.VNode]; the reconciler runs the
    wrapped function once per mount.
    """

    __slots__ = ("fn", "_props_class", "_resolved", "__dict__")

    __name__: str
    __qualname__: str

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self._props_class: type[Props] | None = None
        self._resolved = False
        functools.update_wrapper(self, fn, updated=())

    def _resolve(self) -> type[Props] | None:
        """Find the props class from the function's single parameter annotation (lazily)."""
        if self._resolved:
            return self._props_class
        try:
            params = list(inspect.signature(self.fn, eval_str=True).parameters.values())
        except NameError as exc:
            raise TypeError(f"Component {self.fn.__qualname__}: can't resolve its props annotation ({exc})") from exc
        if not params:
            cls = None
        elif len(params) == 1 and params[0].kind in (params[0].POSITIONAL_ONLY, params[0].POSITIONAL_OR_KEYWORD):
            cls = params[0].annotation
            if not (isinstance(cls, type) and issubclass(cls, Props)):
                raise TypeError(
                    f"Component {self.fn.__qualname__} must take no parameters or one parameter annotated with a "
                    "Props subclass (class CardProps(Props): ...; def Card(props: CardProps))."
                )
        else:
            raise TypeError(
                f"Component {self.fn.__qualname__} must take no parameters or one parameter annotated with a "
                "Props subclass."
            )
        self._props_class = cls
        self._resolved = True
        return cls

    def __call__(self, *children: Any, **props: Any) -> VNode:
        """Return a node for this component; positional arguments become `children`."""
        if children:
            props["children"] = flatten_children(children)
        if _warnings.DEV_MODE:
            cls = self._resolve()
            if cls is None:
                if props.keys() - {"key"}:
                    raise TypeError(f"{self.__qualname__}() takes no props")
            else:
                cls._wyb_check(props, self.__qualname__)
        return VNode(self, props, [], props.get("key"))

    def _render(self, props: dict[str, Any], patchable: bool) -> tuple[Any, Props | None]:
        """Run the body once; returns its result and the live props instance.

        `patchable` says whether the reconciler may later push new props
        into this instance (see `Props`): only then do reads of constant
        props subscribe to anything.
        """
        cls = self._resolve()
        if cls is None:
            return self.fn(), None
        instance = cls._wyb_bind(props, patchable)
        return self.fn(instance), instance

    def __repr__(self) -> str:
        return f"<component {self.__qualname__}>"


@overload
def component[P: Props](fn: Callable[[P], Any]) -> type[P]: ...
@overload
def component(fn: Callable[[], Any]) -> Callable[[], VNode]: ...
def component(fn: Callable[..., Any]) -> Any:
    """Declare a function as a run-once Wybthon component.

    The function takes no parameters, or one parameter annotated with a
    [`Props`][wybthon.Props] subclass. Calling the result returns a node
    for the tree.

    Static typing: the decorated object is typed as the props class (or
    as a no-argument callable), so a type checker validates each call's
    keywords against the declared fields. At run time it's a
    [`Component`][wybthon.Component] that returns a `VNode`.

    Example:
        ```python
        class GreetingProps(Props):
            name: Prop[str] = prop(default="world")


        @component
        def Greeting(props: GreetingProps):
            return p("Hello, ", props.name, "!")


        Greeting(name="Ada")          # a node
        Greeting(name=lambda: user())  # reactive: updates when user() changes
        ```
    """
    if isinstance(fn, Component):
        return fn
    return Component(fn)

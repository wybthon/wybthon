"""The `@component` decorator and the `Component` type it produces.

Wybthon components **run once**: the body executes a single time when
the component mounts and returns its markup. A component declares its
inputs as ordinary parameters, which are its props:

```python
@component
def Counter(label: str = "Count", initial: int = 0):
    count, set_count = create_signal(untrack(lambda: initial))

    def increment():
        set_count(lambda n: n + 1)

    return html(t"<div><p>{label}: {count()}</p><button onclick={increment}>+</button></div>")


render(Counter(initial=10), "#app")
```

Wybthon's compiler turns every read of a parameter in the body into a
tracked read of the parent's current value, as reading a property of
Solid's props object is. So `{label}` in the markup updates when the
parent passes an expression that changes, and a handler that reads a
parameter reads its latest value. Reading one at the top level of the
body reads it once, as destructuring Solid's props does; dev mode warns
when the value was reactive.

Calling a component returns a node, and so does a component tag in a
template (`<{Counter} initial={5} />`). Type checkers see the call as a
call of the function, so missing, mistyped, and unknown props are errors
without a plugin. Content arrives as the `children` parameter: a tag's
markup, the `children` keyword, or item syntax on the call,
`Card(title="Hi")[html(t"<p>Body</p>")]`. A `**rest` parameter collects
the props the component doesn't declare, as a reactive view that
spreads onto an element.
"""

from __future__ import annotations

import annotationlib
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from . import _warnings
from .reactivity._props import Props
from .vnode import Node, VNode, flatten_children

__all__ = ["component", "Component", "builtin", "declared_props"]


class Component[**P]:
    """A run-once component produced by [`component`][wybthon.component].

    Calling it returns a [`VNode`][wybthon.vnode.VNode]; the reconciler runs
    the component's body once per mount.
    """

    __slots__ = ("fn", "signature", "_props_class", "_resolved", "_compiled", "__dict__")

    # A component call in a compiled template receives getters for its
    # dynamic props (see `wybthon._compiled.call`).
    __wybthon_component__ = True

    __name__: str
    __qualname__: str

    def __init__(self, fn: Callable[..., Any]) -> None:
        body = getattr(fn, "__wybthon_body__", None)
        # The function whose signature declares the props.
        self.signature = fn
        # What runs at mount: the compiled body, which takes the props object.
        self.fn: Callable[..., Any] = body if body is not None else fn
        self._compiled = body is not None
        self._props_class: type[Props] | None = None
        self._resolved = False
        functools.update_wrapper(self, fn, updated=())

    def _resolve(self) -> type[Props] | None:
        """Build the props class from the function's signature (on first use)."""
        if self._resolved:
            return self._props_class
        fn = self.signature
        try:
            params = list(inspect.signature(fn, annotation_format=annotationlib.Format.FORWARDREF).parameters.values())
        except (TypeError, ValueError) as exc:  # pragma: no cover - every function has a signature
            raise TypeError(f"Component {fn.__qualname__}: can't read its signature ({exc})") from exc
        cls: type[Props] | None
        if not params:
            cls = None
        elif not self._compiled and (internal := _internal_props(fn, params)) is not None:
            cls = internal
        else:
            cls = Props._wyb_from_signature(fn.__qualname__, params)
            if not self._compiled:
                if _warnings.DEV_MODE:
                    raise TypeError(
                        f"Component {fn.__qualname__} takes props as parameters, which only Wybthon's compiler "
                        "makes reactive, and its module wasn't compiled. Modules imported after wybthon, wyb build, "
                        "wyb dev, wyb run, and pytest compile components; see the compiler documentation."
                    )
                self.fn = _uncompiled(fn, cls)
        self._props_class = cls
        self._resolved = True
        return cls

    def _wyb_check_children(self) -> None:
        """Dev mode: reject item syntax (`Card(title="Hi")[...]`) on a component that takes no `children`."""
        if not _warnings.DEV_MODE:
            return
        cls = self._resolve()
        if cls is None or not (cls._wyb_open or cls._wyb_internal or "children" in cls._wyb_names):
            raise TypeError(
                f"{self.__qualname__}() got unexpected prop(s): children "
                "(declare a `children: Children = None` parameter to take content)"
            )

    def _hot_replace(self, other: Component[Any]) -> None:
        """Take on another component's code, keeping this object's identity (hot module replacement)."""
        self.signature = other.signature
        self.fn = other.fn
        self._compiled = other._compiled
        self._props_class = None
        self._resolved = False
        for attribute in ("__doc__", "__wrapped__", "__annotations__"):
            if hasattr(other, attribute):
                setattr(self, attribute, getattr(other, attribute))

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Node:
        """Return a node for this component; arguments bind to its parameters as in a call."""
        props: dict[str, Any] = kwargs
        if args:
            cls = self._resolve()
            if cls is not None and cls._wyb_internal:
                props["children"] = flatten_children(args)
            else:
                names = cls._wyb_positional if cls is not None else ()
                if len(args) > len(names):
                    raise TypeError(
                        f"{self.__qualname__}() takes {len(names)} positional argument(s) but {len(args)} were given"
                    )
                for name, value in zip(names, args, strict=False):
                    if name in props:
                        raise TypeError(f"{self.__qualname__}() got multiple values for argument {name!r}")
                    props[name] = value
        if _warnings.DEV_MODE:
            cls = self._resolve()
            if cls is None:
                if props:
                    raise TypeError(f"{self.__qualname__}() takes no props")
            else:
                cls._wyb_check(props, self.__qualname__)
        return VNode(self, props, [])

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


def declared_props(comp: Any) -> frozenset[str] | None:
    """The props a component declares by name, or `None` when it can't say (internal).

    A component with a `**rest` parameter also accepts props it doesn't
    declare, but its declared names are still returned: the router passes
    a route's component only the route props (`params`, `search`, `data`,
    `children`) it declares, so they never land in its `**rest` spread.
    A lazy component, a built-in, and a plain function used as a tag
    return `None`.
    """
    if type(comp) is not Component:
        return None
    cls = comp._resolve()
    if cls is None:
        return frozenset()
    if cls._wyb_internal:
        return None
    return cls._wyb_names


def _internal_props(fn: Callable[..., Any], params: list[inspect.Parameter]) -> type[Props] | None:
    """The props class of one of Wybthon's built-ins, which take their props object as their one parameter."""
    if len(params) != 1 or params[0].kind not in (params[0].POSITIONAL_ONLY, params[0].POSITIONAL_OR_KEYWORD):
        return None
    annotation = params[0].annotation
    if isinstance(annotation, str):
        # A module with `from __future__ import annotations`, as Wybthon's own are.
        try:
            annotation = inspect.signature(fn, eval_str=True).parameters[params[0].name].annotation
        except Exception:
            return None
    return annotation if isinstance(annotation, type) and issubclass(annotation, Props) else None


def _uncompiled(fn: Callable[..., Any], cls: type[Props]) -> Callable[[Props], Any]:
    """Run a component whose module wasn't compiled with its props' current values (outside dev mode)."""
    names = tuple(cls._wyb_fields)

    def body(props: Props) -> Any:
        values = {name: getattr(props, name) for name in names}
        if cls._wyb_open:
            values.update({key: value for key, value in props._raw.items() if key not in values})
        return fn(**values)

    return body


def builtin[F](fn: F) -> F:
    """Mark a built-in that renders markup, so compiled templates pass it getters (internal).

    `Show`, `For`, `Loading`, and the other flow and boundary functions
    aren't `@component`s, but a call of one in a template should build it
    with getters for its dynamic arguments, as a component call does.
    """
    fn.__wybthon_component__ = True  # type: ignore[attr-defined]
    return fn


if TYPE_CHECKING:
    # To a type checker a component is its own function returning a node, so
    # a call is checked against the function's signature and errors name it.
    def component[**P](fn: Callable[P, object]) -> Callable[P, Node]:
        """Declare a function as a run-once Wybthon component."""
        ...

else:

    def component(fn: Callable[..., object]) -> Component[...]:
        """Declare a function as a run-once Wybthon component.

        The function's parameters are its props. Calling the result returns
        a node for the tree; type checkers check the call against the
        function's own signature.

        Example:
            ```python
            @component
            def Greeting(name: str = "world"):
                return html(t"<p>Hello, {name}!</p>")


            Greeting(name="Ada")                       # a node
            html(t"<{Greeting} name={user().name} />")  # updates when user() changes
            ```
        """
        if isinstance(fn, Component):
            return fn
        return Component(fn)

"""Component base class and ``@component`` decorator for VDOM components."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List

if TYPE_CHECKING:
    from .vdom import VNode

__all__ = ["Component", "component", "forward_ref"]


class Component:
    """Class component base for the VDOM renderer.

    Subclasses should implement `render(self) -> VNode`.
    Lifecycle hooks:
      - on_mount(self)
      - on_update(self, prev_props: dict)
      - on_unmount(self)
    """

    def __init__(self, props: Dict[str, Any]) -> None:
        self.props = props
        self._cleanups: List[Callable[[], Any]] = []

    def render(self) -> "VNode":
        raise NotImplementedError

    # Lifecycle hooks
    def on_mount(self) -> None:  # noqa: D401
        """Called after the component is first mounted."""
        pass

    def on_update(self, prev_props: Dict[str, Any]) -> None:  # noqa: D401
        """Called after props update and render diff applied."""
        pass

    def on_unmount(self) -> None:  # noqa: D401
        """Called before the component is removed from the DOM."""
        pass

    # --------------- Cleanup management ---------------
    def add_cleanup(self, fn: Callable[[], Any]) -> None:
        """Register a cleanup callback to run on unmount."""
        self._cleanups.append(fn)

    # Alias for ergonomics
    on_cleanup = add_cleanup

    def _run_cleanups(self) -> None:
        """Run and clear all registered cleanup callbacks safely."""
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                # Swallow cleanup errors to avoid breaking render pipeline
                pass


def component(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that enables Pythonic keyword-argument props for function components.

    **Stateless** – return a ``VNode`` directly (re-called on prop changes)::

        @component
        def Greeting(name: str = "world"):
            return p(f"Hello, {name}!")

    **Stateful** – create signals during setup and return a *render function*
    (setup runs once, render re-runs when signals change)::

        @component
        def Counter(initial: int = 0):
            count, set_count = create_signal(initial)
            def render():
                return div(p(f"Count: {count()}"),
                           button("+", on_click=lambda e: set_count(count() + 1)))
            return render

    **Children** are available via a ``children`` parameter::

        @component
        def Card(title: str = "", children=None):
            return section(h3(title), *(children or []))

    **Direct calls** with keyword arguments return a ``VNode``, so you can
    compose components without ``h()``::

        Counter(initial=5)
        Card("child1", "child2", title="My Card")

    The component still works with ``h()`` as usual::

        h(Counter, {"initial": 5})
    """
    sig = inspect.signature(fn)
    params = sig.parameters

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # VDOM engine path: called with a single props dict
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            props = args[0]
            fn_kwargs: Dict[str, Any] = {}
            for name in params:
                if name in props:
                    fn_kwargs[name] = props[name]
            return fn(**fn_kwargs)

        # Direct call: positional args are children, keyword args are props
        from .vdom import h  # noqa: F811 — lazy import avoids circular dependency

        all_props: Dict[str, Any] = dict(kwargs)
        if args:
            all_props["children"] = list(args)
        return h(wrapper, all_props)

    wrapper._wyb_component = True  # type: ignore[attr-defined]
    return wrapper


def forward_ref(render_fn: Callable[..., Any]) -> Callable[..., "VNode"]:
    """Create a component that forwards a ``ref`` prop to a child element.

    The wrapped function receives ``(props, ref)`` instead of ``(props,)``,
    where *ref* is the value of the ``ref`` prop (or ``None``).

    Example::

        FancyInput = forward_ref(lambda props, ref: input_(
            type="text", ref=ref, class_name="fancy", **props,
        ))
    """

    def ForwardRefWrapper(props: Dict[str, Any]) -> "VNode":
        ref = props.get("ref")
        inner_props = {k: v for k, v in props.items() if k != "ref"}
        return render_fn(inner_props, ref)

    ForwardRefWrapper._wyb_forward_ref = True  # type: ignore[attr-defined]
    ForwardRefWrapper.__name__ = f"forward_ref({getattr(render_fn, '__name__', 'Component')})"
    ForwardRefWrapper.__qualname__ = ForwardRefWrapper.__name__
    return ForwardRefWrapper

"""``@component`` decorator and ``forward_ref`` for function components.

The ``@component`` decorator converts each function parameter into a
**reactive getter** backed by a Signal.  This means prop changes from a
parent automatically propagate without boilerplate.  The component body
always runs **once** (setup phase).  To produce dynamic output, return a
*render function* that will be re-invoked whenever a tracked signal
(including a prop getter) changes.

Reactive prop getters
---------------------
Each named parameter in the decorated function is replaced by a
zero-argument *getter* function.  Call it to read the current value::

    @component
    def Greeting(name="world"):
        def render():
            return p(f"Hello, {name()}!")
        return render

The getter is backed by a ``Signal`` that the reconciler updates
whenever the parent provides new prop values.
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict

if TYPE_CHECKING:
    pass

__all__ = ["component", "forward_ref"]


def component(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that turns function parameters into reactive prop getters.

    **Stateful** -- create signals during setup and return a *render function*
    (setup runs once, render re-runs when signals change)::

        @component
        def Counter(initial=0):
            count, set_count = create_signal(initial())
            def render():
                return div(p(f"Count: {count()}"),
                           button("+", on_click=lambda e: set_count(count() + 1)))
            return render

    **Stateless** -- return a ``VNode`` directly.  The body is auto-wrapped
    as a render function and re-called when prop signals change::

        @component
        def Greeting(name="world"):
            return p(f"Hello, {name()}!")

    **Children** are available via a ``children`` parameter::

        @component
        def Card(title="", children=None):
            def render():
                kids = children() or []
                if not isinstance(kids, list):
                    kids = [kids]
                return section(h3(title()), *kids)
            return render

    **Direct calls** with keyword arguments return a ``VNode``::

        Counter(initial=5)
        Card("child1", "child2", title="My Card")

    The component still works with ``h()`` as usual::

        h(Counter, {"initial": 5})
    """
    from .reactivity import Signal, _get_component_ctx

    sig = inspect.signature(fn)
    params = sig.parameters

    defaults: Dict[str, Any] = {}
    for name, param in params.items():
        if param.default is not inspect.Parameter.empty:
            defaults[name] = param.default
        else:
            defaults[name] = None

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            props = args[0]

            prop_signals: Dict[str, Signal] = {}
            getter_kwargs: Dict[str, Callable[[], Any]] = {}
            for pname in params:
                value = props.get(pname, defaults.get(pname))
                prop_sig: Signal = Signal(value)
                prop_signals[pname] = prop_sig
                getter_kwargs[pname] = prop_sig.get

            ctx = _get_component_ctx()
            if ctx is not None:
                ctx._prop_signals = prop_signals

            result = fn(**getter_kwargs)

            if not callable(result):
                _gkw = getter_kwargs

                def _stateless_render() -> Any:
                    return fn(**_gkw)

                if ctx is not None:
                    ctx._render_fn = _stateless_render

            return result

        from .vnode import h

        all_props: Dict[str, Any] = dict(kwargs)
        if args:
            all_props["children"] = list(args)
        return h(wrapper, all_props)

    wrapper._wyb_component = True  # type: ignore[attr-defined]
    wrapper._wyb_defaults = defaults  # type: ignore[attr-defined]
    return wrapper


def forward_ref(render_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a component that forwards a ``ref`` prop to a child element.

    The wrapped function receives ``(props, ref)`` instead of ``(props,)``,
    where *ref* is the value of the ``ref`` prop (or ``None``).

    Example::

        FancyInput = forward_ref(lambda props, ref: input_(
            type="text", ref=ref, class_name="fancy", **props,
        ))
    """

    def ForwardRefWrapper(props: Dict[str, Any]) -> Any:
        ref = props.get("ref")
        inner_props = {k: v for k, v in props.items() if k != "ref"}
        return render_fn(inner_props, ref)

    ForwardRefWrapper._wyb_forward_ref = True  # type: ignore[attr-defined]
    ForwardRefWrapper.__name__ = f"forward_ref({getattr(render_fn, '__name__', 'Component')})"
    ForwardRefWrapper.__qualname__ = ForwardRefWrapper.__name__
    return ForwardRefWrapper

"""``@component`` decorator and ``forward_ref`` for function components.

The ``@component`` decorator provides two main features:

1. **Kwargs calling convention** -- call a component directly with
   keyword arguments and it returns an ``h()`` VNode::

       Counter(initial=5)          # → h(Counter, {"initial": 5})
       Card("child", title="Hi")   # → h(Card, {"title": "Hi", "children": ["child"]})

2. **Automatic prop destructuring** -- named parameters are read from
   the ``ReactiveProps`` proxy and passed as plain Python values.  For
   **stateless** components (those that return a VNode directly), the
   decorator wraps the body in a render function that re-reads props
   on each render cycle, keeping the output reactive.

Reactive prop access
--------------------
Props are plain values inside the function body — no callable getters::

    @component
    def Greeting(name="world"):
        return p(f"Hello, {name}!")   # name is a plain string

For **stateful** components, setup runs once with initial values.
Use ``get_props()`` to access the ``ReactiveProps`` proxy for
reactive tracking inside effects or the render function::

    @component
    def Counter(initial=0):
        count, set_count = create_signal(initial)
        def render():
            return div(p(f"Count: {count()}"))
        return render
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict

if TYPE_CHECKING:
    pass

__all__ = ["component", "forward_ref"]


def component(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that provides kwargs calling and prop destructuring.

    **Stateful** -- create signals during setup and return a *render function*
    (setup runs once, render re-runs when signals change)::

        @component
        def Counter(initial=0):
            count, set_count = create_signal(initial)
            def render():
                return div(p(f"Count: {count()}"),
                           button("+", on_click=lambda e: set_count(count() + 1)))
            return render

    **Stateless** -- return a ``VNode`` directly.  The body is auto-wrapped
    as a render function and re-called when prop signals change::

        @component
        def Greeting(name="world"):
            return p(f"Hello, {name}!")

    **Children** are available via a ``children`` parameter::

        @component
        def Card(title="", children=None):
            kids = children or []
            if not isinstance(kids, list):
                kids = [kids]
            return section(h3(title), *kids)

    **Direct calls** with keyword arguments return a ``VNode``::

        Counter(initial=5)
        Card("child1", "child2", title="My Card")

    The component still works with ``h()`` as usual::

        h(Counter, {"initial": 5})
    """
    from .reactivity import ReactiveProps, _get_component_ctx

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
        if len(args) == 1 and isinstance(args[0], (dict, ReactiveProps)) and not kwargs:
            props_input = args[0]

            if isinstance(props_input, ReactiveProps):
                reactive_props = props_input
            else:
                reactive_props = ReactiveProps(props_input, defaults)

            ctx = _get_component_ctx()
            if ctx is not None:
                ctx._reactive_props = reactive_props

            initial_kwargs: Dict[str, Any] = {}
            for pname in params:
                initial_kwargs[pname] = reactive_props.get(pname, defaults.get(pname))

            result = fn(**initial_kwargs)

            if not callable(result):
                _rp = reactive_props
                _params = params

                def _stateless_render() -> Any:
                    kw: Dict[str, Any] = {}
                    for pn in _params:
                        kw[pn] = _rp._get(pn)
                    return fn(**kw)

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

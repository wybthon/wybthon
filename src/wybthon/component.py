"""``@component`` decorator and ``forward_ref`` for function components.

The ``@component`` decorator provides two main features:

1. **Kwargs calling convention** -- call a component directly with
   keyword arguments and it returns an ``h()`` VNode::

       Counter(initial=5)          # → h(Counter, {"initial": 5})
       Card("child", title="Hi")   # → h(Card, {"title": "Hi", "children": ["child"]})

2. **Automatic prop destructuring** -- named parameters are read from
   the ``ReactiveProps`` proxy and passed as plain Python values **once**
   during component setup.  This matches SolidJS-style "setup runs once"
   semantics: the body is invoked a single time when the component is
   mounted, and updates flow through reactive holes embedded in the
   returned VNode tree.

Reactive prop access
--------------------
Inside the body, parameter values are plain Python values that
reflect the **initial** props.  Because the body never re-runs,
re-rendering on prop changes happens at the **hole** boundary -- pass
a getter expression directly in the VNode tree::

    @component
    def Greeting(name="world"):
        # `name` here is the initial value; for reactive updates use a hole:
        props = get_props()
        return p("Hello, ", lambda: props.name, "!")

For the special case where you only need access to the **current** prop
value at one site, calling ``get_props()`` and reading attribute
accesses inside a hole is the idiomatic pattern.

The legacy "return a render function" pattern is still supported and
implemented as syntactic sugar for a single-root reactive hole::

    @component
    def Counter(initial=0):
        count, set_count = create_signal(initial)
        def render():
            return div(p(f"Count: {count()}"))
        return render

When the component returns a callable, the reconciler wraps it in a
``_dynamic`` VNode whose effect re-runs the render function on
dependency changes.  This is identical to writing the render fn as a
direct child of a div::

    return div(lambda: p(f"Count: {count()}"))
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

    Components run **once** during mount.  Reactive updates inside the
    component come from holes in the returned VNode tree (callable
    children/props), not from re-running the body.

    **Stateful** -- create signals during setup; embed them as
    reactive holes in the returned tree::

        @component
        def Counter(initial=0):
            count, set_count = create_signal(initial)
            return div(
                p("Count: ", count),
                button("+", on_click=lambda e: set_count(count() + 1)),
            )

    **Legacy stateful** -- returning a render function is still supported;
    the reconciler treats it as a single-root reactive hole::

        @component
        def Counter(initial=0):
            count, set_count = create_signal(initial)
            def render():
                return div(p(f"Count: {count()}"))
            return render

    **Stateless** -- return a ``VNode`` directly.  Note that prop values
    captured in the body are read **once** at mount; for live updates
    use ``get_props()`` and access props inside a reactive hole::

        @component
        def Greeting(name="world"):
            return p(f"Hello, {name}!")   # name is the initial value

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

            return fn(**initial_kwargs)

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

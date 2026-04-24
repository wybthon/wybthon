"""`@component` decorator and `forward_ref` for function components.

Wybthon's component model is **fully reactive** and **runs once**:

- The body of an `@component` function executes a single time when the
  component mounts.
- Each parameter declared in the function signature receives a
  **reactive accessor** (a zero-argument callable). Calling the accessor
  returns the *current* prop value and tracks it as a reactive
  dependency.
- Embedding an accessor directly inside a `VNode` tree turns the
  surrounding region into a fine-grained **reactive hole** that updates
  only the relevant DOM when the prop changes.
- The decorator also enables a **direct call** style — invoking the
  component with keyword arguments yields a `VNode` instead of running
  the body, so trees can be authored ergonomically.

Authoring modes:

- **Named accessor mode** — used when the signature has zero args, kwargs
  with defaults, or `**kwargs`. Each parameter becomes a reactive
  accessor for the prop of the same name.
- **Proxy mode** — used when the signature has exactly one positional-only
  or positional-or-keyword parameter with no default and no
  `*args`/`**kwargs`. The single parameter receives the full
  [`ReactiveProps`][wybthon.ReactiveProps] proxy.

Example:
    A trivial greeting and a counter::

        @component
        def Greet(name="world"):
            return p("Hello, ", name, "!")

        @component
        def Counter(initial=0):
            # ``untrack`` snapshots the seed value without subscribing
            # (otherwise we would re-seed on every parent update, and
            # dev mode would warn about a destructured prop).
            count, set_count = create_signal(untrack(initial))
            return div(
                p("Count: ", count),
                button("+", on_click=lambda e: set_count(count() + 1)),
            )

When you need the underlying `ReactiveProps` proxy (e.g. to iterate
keys or forward unknown props), call
[`get_props`][wybthon.reactivity.get_props] from inside the component
body, or declare the component with a single positional parameter
(proxy mode).

Components are expected to return a [`VNode`][wybthon.VNode]. Use
[`dynamic`][wybthon.dynamic] for explicit reactive holes when an entire
subtree needs to swap based on a signal. A callable return is also
accepted (it is wrapped in a single-root reactive hole) but the
canonical style is "return a VNode and embed `dynamic(...)` where you
need reactive swaps".
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

if TYPE_CHECKING:
    pass

from ._warnings import (
    is_dev_mode,
    warn_destructured_prop,
)

__all__ = ["component", "forward_ref"]


def _build_param_plan(
    fn: Callable[..., Any],
) -> Tuple[List[str], Dict[str, Any], bool]:
    """Inspect `fn` once and produce a `(param_names, defaults, proxy_mode)` plan.

    `proxy_mode` is True when the function takes a single positional or
    positional-or-keyword parameter with no default — in which case the
    decorator passes the `ReactiveProps` proxy directly instead of
    destructuring kwargs.

    Args:
        fn: The function to inspect.

    Returns:
        A tuple `(param_names, defaults, proxy_mode)`.
    """
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return [], {}, False

    param_names: List[str] = []
    defaults: Dict[str, Any] = {}
    positional_no_default = 0
    has_var = False

    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            has_var = True
            continue
        param_names.append(name)
        if param.default is not inspect.Parameter.empty:
            defaults[name] = param.default
        else:
            defaults[name] = None
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                positional_no_default += 1

    proxy_mode = not has_var and positional_no_default == 1 and len(param_names) == 1
    return param_names, defaults, proxy_mode


def _make_setup_getter(
    base_getter: Callable[[], Any],
    pname: str,
    comp_fn: Callable[..., Any],
    in_setup: list,
) -> Callable[[], Any]:
    """Wrap a prop accessor to fire a dev-mode warning on setup-time reads.

    The wrapper is stable — it forwards every call through to `base_getter`
    without changing tracking semantics. A warning fires only when **all**
    of the following hold during setup:

    - `in_setup[0]` is True — the component body has not returned yet.
    - The read is **not** inside [`untrack`][wybthon.untrack] (the
      canonical opt-out).
    - No reactive computation is currently active — i.e. the read is a
      raw setup-time call, not a read inside `create_effect` /
      `create_memo` (which subscribe correctly).

    Combined, these correctly target the actual footgun (`_ = name()` in
    the component body) without false positives on legitimate patterns
    like `create_effect(lambda: print(name()))`.

    Args:
        base_getter: The underlying reactive prop accessor.
        pname: The prop name (used in the warning message).
        comp_fn: The component function (used to identify the offender
            in the warning).
        in_setup: A single-element list flag toggled by the caller. While
            `in_setup[0]` is True, setup-time reads warn.

    Returns:
        A new accessor with the same tracking semantics as `base_getter`.
    """

    def getter() -> Any:
        if in_setup[0]:
            from .reactivity import _has_current_computation, _is_inside_untrack

            if not _is_inside_untrack() and not _has_current_computation():
                warn_destructured_prop(comp_fn, pname)
        return base_getter()

    getter._wyb_getter = True  # type: ignore[attr-defined]
    getter.__qualname__ = f"{getattr(comp_fn, '__qualname__', '<component>')}.{pname}"
    getter.__name__ = pname
    return getter


def component(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a function as a Wybthon component.

    The body of `fn` is invoked **once** per mount. Each declared parameter
    is bound to a **reactive accessor** — call it to read the current
    value (tracked) or pass it directly into a `VNode` tree to create a
    reactive hole.

    The decorated callable also supports a **direct call** style:
    `Counter(initial=5)` returns a `VNode` (equivalent to
    `h(Counter, {"initial": 5})`) so component composition feels natural.

    See the module docstring for the complete authoring guide and the
    full mode-selection table.

    Args:
        fn: The function to decorate. Its signature determines whether
            named-accessor mode or proxy mode is used.

    Returns:
        A wrapped callable. When called by the reconciler with a single
        props dict, it executes `fn` with the appropriate accessors;
        when called by user code with kwargs, it returns a `VNode`.
    """
    from .reactivity import ReactiveProps, _get_component_ctx

    param_names, defaults, proxy_mode = _build_param_plan(fn)

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # VDOM engine path: invoked with a single dict / ReactiveProps and no kwargs.
        if len(args) == 1 and isinstance(args[0], (dict, ReactiveProps)) and not kwargs:
            props_input = args[0]

            if isinstance(props_input, ReactiveProps):
                reactive_props = props_input
            else:
                reactive_props = ReactiveProps(props_input, defaults)

            ctx = _get_component_ctx()
            if ctx is not None:
                ctx._reactive_props = reactive_props

            if proxy_mode:
                return fn(reactive_props)

            # Dev-mode path: wrap each prop accessor so we can detect
            # setup-time unwraps (the destructured-prop footgun).  The
            # wrapper has a small but non-zero per-read cost, so we
            # skip it entirely in production.
            if is_dev_mode():
                in_setup = [True]
                dev_kwargs: Dict[str, Any] = {}
                for pname in param_names:
                    base = reactive_props._make_getter(pname)
                    dev_kwargs[pname] = _make_setup_getter(base, pname, fn, in_setup)
                try:
                    return fn(**dev_kwargs)
                finally:
                    in_setup[0] = False

            getter_kwargs: Dict[str, Any] = {pname: reactive_props._make_getter(pname) for pname in param_names}
            return fn(**getter_kwargs)

        # Direct call: build a VNode for tree authoring (no body execution).
        from .vnode import h

        all_props: Dict[str, Any] = dict(kwargs)
        if args:
            all_props["children"] = list(args)
        return h(wrapper, all_props)

    wrapper._wyb_component = True  # type: ignore[attr-defined]
    wrapper._wyb_defaults = defaults  # type: ignore[attr-defined]
    return wrapper


def forward_ref(render_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a component that forwards a `ref` prop to a child element.

    The wrapped function receives `(props, ref)` instead of `(props,)`,
    where `ref` is the value of the `ref` prop (or `None`). `ref` is
    **stripped from props** — matching React's `forwardRef` semantics —
    so the wrapped function only sees its own concerns.

    Args:
        render_fn: A callable taking `(props, ref)` and returning a
            `VNode` subtree.

    Returns:
        A component callable that forwards the `ref` prop to `render_fn`.

    Example:
        ```python
        FancyInput = forward_ref(lambda props, ref: input_(
            type="text", ref=ref, class_="fancy",
        ))

        my_ref = Ref()
        h(FancyInput, {"ref": my_ref})
        ```
    """
    from .reactivity import ReactiveProps

    def ForwardRefWrapper(props: Any) -> Any:
        if isinstance(props, ReactiveProps):
            ref = props.value("ref")
            raw = object.__getattribute__(props, "_raw")
            defaults = object.__getattribute__(props, "_defaults")
            stripped_raw = {k: v for k, v in raw.items() if k != "ref"}
            stripped_defaults = {k: v for k, v in defaults.items() if k != "ref"}
            stripped = ReactiveProps(stripped_raw, stripped_defaults)
            return render_fn(stripped, ref)
        ref = props.get("ref")
        stripped_dict = {k: v for k, v in props.items() if k != "ref"}
        return render_fn(stripped_dict, ref)

    ForwardRefWrapper._wyb_forward_ref = True  # type: ignore[attr-defined]
    ForwardRefWrapper._wyb_component = True  # type: ignore[attr-defined]
    ForwardRefWrapper.__name__ = f"forward_ref({getattr(render_fn, '__name__', 'Component')})"
    ForwardRefWrapper.__qualname__ = ForwardRefWrapper.__name__
    return ForwardRefWrapper

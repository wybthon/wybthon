"""Lazy-loaded components integrated with Suspense.

[`lazy`][wybthon.lazy] wraps a **loader** callback (sync or async) that
produces a component. The component loads on first mount, backed by a
[`Resource`][wybthon.Resource]: while the load is in flight, the
nearest [`Suspense`][wybthon.Suspense] boundary shows its fallback, and
a load failure raises into the nearest
[`ErrorBoundary`][wybthon.ErrorBoundary]. This matches SolidJS's
`lazy(() => import(...))` semantics, adapted to Python's import system.

The loader may return:

- a component callable directly,
- an imported module (an export is picked by convention: `Page`, then
  `default`, then the first callable), or
- a module path string, or a `(module_path, attr)` tuple, imported via
  `importlib`.

Async loaders can `await` arbitrary work first (for example
`micropip.install(...)` in Pyodide) before returning any of the above.

Example:
    ```python
    About = lazy(lambda: ("app.about.page", "Page"))

    async def load_chart():
        import micropip
        await micropip.install("app-charts")
        import app_charts
        return app_charts.Chart

    Chart = lazy(load_chart)
    Chart.preload()  # warm the cache on hover/intent

    Suspense(fallback=p("Loading..."), children=[About()])
    ```

See Also:
    - [Suspense and lazy loading guide](../concepts/suspense-lazy.md)
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable as AbcAwaitable
from typing import Any, Callable, Dict, Optional

from .reactivity import ReactiveProps, Resource, create_resource
from .vnode import VNode, dynamic, h, to_text_vnode

__all__ = ["lazy"]


def _resolve_attr(mod: Any, attr: Optional[str]) -> Any:
    """Pick an exported component from `mod`, by name or by convention.

    When `attr` is omitted, prefers `Page`, then `default`, then the
    first callable export.

    Args:
        mod: The imported module.
        attr: Optional attribute name to resolve.

    Returns:
        The resolved component object.

    Raises:
        AttributeError: When no suitable export can be found.
    """
    if not attr:
        for candidate in ("Page", "default"):
            if hasattr(mod, candidate):
                return getattr(mod, candidate)
        for name in dir(mod):
            if name.startswith("__"):
                continue
            obj = getattr(mod, name)
            if callable(obj):
                return obj
        raise AttributeError("No export found to use as component")
    return getattr(mod, attr)


def _coerce_component(result: Any) -> Any:
    """Turn a loader result into a component callable.

    Accepts a component, a module, a module-path string, or a
    `(module_path, attr)` tuple.
    """
    if isinstance(result, str):
        return _resolve_attr(importlib.import_module(result), None)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str):
        module_path, attr = result
        return _resolve_attr(importlib.import_module(module_path), attr)
    if hasattr(result, "__spec__") and not callable(result):  # a module
        return _resolve_attr(result, None)
    if callable(result):
        return result
    raise TypeError(f"lazy loader returned {result!r}, which is not a component, module, or module path")


def _props_to_dict(props: Any) -> Dict[str, Any]:
    """Convert [`ReactiveProps`][wybthon.ReactiveProps] (or a plain dict) into a snapshot."""
    if isinstance(props, ReactiveProps):
        return {k: props.value(k) for k in props}
    return dict(props) if hasattr(props, "items") else {}


def lazy(loader: Callable[[], Any]) -> Callable[..., Any]:
    """Create a lazily-loaded component from a loader callback.

    The loader runs once, on the first mount (or on
    [`preload`](#preload)); the resolved component is cached for every
    later mount. While loading, the nearest
    [`Suspense`][wybthon.Suspense] boundary shows its fallback. A
    loader error raises into the nearest
    [`ErrorBoundary`][wybthon.ErrorBoundary].

    Args:
        loader: Zero-arg callable, sync or async, returning a component
            callable, a module, a module-path string, or a
            `(module_path, attr)` tuple.

    Returns:
        A component callable with a `.preload()` method that starts the
        load early and returns the backing
        [`Resource`][wybthon.Resource].

    Example:
        ```python
        Team = lazy(lambda: ("app.about.team.page", "Page"))

        Route(path="/about/team", component=Team)
        Link("Team", href="/about/team", on_mouseenter=lambda e: Team.preload())
        ```
    """
    holder: Dict[str, Optional[Resource[Any]]] = {"resource": None}

    async def _load() -> Any:
        result = loader()
        if isinstance(result, AbcAwaitable):
            result = await result
        return _coerce_component(result)

    def _ensure_resource() -> Resource[Any]:
        res = holder["resource"]
        if res is None:
            res = create_resource(_load)
            holder["resource"] = res
        return res

    def LazyComponent(props: Any) -> Any:
        res = _ensure_resource()

        def render() -> VNode:
            comp = res()  # tracked; registers with Suspense while pending
            err = res.error
            if err is not None:
                raise err
            if comp is None:
                return to_text_vnode("")
            return h(comp, _props_to_dict(props))

        return dynamic(render)

    def preload() -> Resource[Any]:
        """Start loading now; returns the backing resource."""
        return _ensure_resource()

    LazyComponent.preload = preload  # type: ignore[attr-defined]
    LazyComponent._wyb_component = True  # type: ignore[attr-defined]
    LazyComponent.__name__ = "lazy"
    LazyComponent.__qualname__ = "lazy"
    return LazyComponent

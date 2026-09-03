"""Lazy-loaded components integrated with `Loading` boundaries.

[`lazy`][wybthon.lazy] wraps a **loader** callback (sync or async) that
produces a component. The component loads on first mount, backed by an
async [`create_memo`][wybthon.create_memo]: while the load is in
flight, the nearest [`Loading`][wybthon.Loading] boundary shows its
fallback, and a load failure raises into the nearest
[`Errored`][wybthon.Errored] boundary. This matches SolidJS's
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

    Loading(lambda: About(), fallback=p("Loading..."))
    ```

See Also:
    - [Async and loading guide](../concepts/async-loading.md)
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable as AbcAwaitable
from collections.abc import Callable
from typing import Any

from .component import Component
from .reactivity._core import Memo, run_with_owner
from .reactivity._primitives import create_memo, latest
from .reactivity._props import Props
from .vnode import VNode, h

__all__ = ["lazy"]


def _resolve_attr(mod: Any, attr: str | None) -> Any:
    """Pick an exported component from `mod`, by name or by convention.

    When `attr` is omitted, prefers `Page`, then `default`, then the
    first callable export.

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


class LazyComponent(Component):
    """A component returned by [`lazy`][wybthon.lazy]; call `.preload()` to load early."""

    def __init__(self, loader: Callable[[], Any]) -> None:
        self._loader = loader
        self._memo: Memo[Any] | None = None
        super().__init__(self._render_lazy)
        self.__name__ = "lazy"
        self.__qualname__ = "lazy"

    async def _load(self) -> Any:
        result = self._loader()
        if isinstance(result, AbcAwaitable):
            result = await result
        return _coerce_component(result)

    def _ensure_memo(self) -> Memo[Any]:
        memo = self._memo
        if memo is None:
            # Detached from the mounting component's ownership so the
            # loaded component stays cached across unmounts.
            memo = run_with_owner(None, lambda: create_memo(lambda: self._load()))
            self._memo = memo
        return memo

    def _render_lazy(self, props: Props) -> Any:
        memo = self._ensure_memo()

        def render() -> VNode | None:
            comp = memo()  # raises NotReadyError while loading
            if comp is None:
                return None
            forwarded = {k: props.raw(k) for k in props}
            children = forwarded.pop("children", None)
            if children is None:
                return h(comp, forwarded)
            if not isinstance(children, list):
                children = [children]
            return h(comp, forwarded, *children)

        return render

    def preload(self) -> None:
        """Start loading now (a no-op when already loading or loaded)."""
        latest(self._ensure_memo())


def lazy(loader: Callable[[], Any]) -> LazyComponent:
    """Create a lazily-loaded component from a loader callback.

    The loader runs once, on the first mount (or on `.preload()`); the
    resolved component is cached for every later mount. While loading,
    the nearest [`Loading`][wybthon.Loading] boundary shows its
    fallback. A loader error raises into the nearest
    [`Errored`][wybthon.Errored] boundary.

    Args:
        loader: Zero-arg callable, sync or async, returning a component
            callable, a module, a module-path string, or a
            `(module_path, attr)` tuple.

    Returns:
        A component with a `.preload()` method that starts the load
        early.

    Example:
        ```python
        Team = lazy(lambda: ("app.about.team.page", "Page"))

        Route(path="/about/team", component=Team)
        Link("Team", href="/about/team", on_mouseenter=lambda e: Team.preload())
        ```
    """
    return LazyComponent(loader)

"""Helpers for lazy-loading components with simple loading/error states.

Wybthon's lazy loaders use Python's `importlib` so they work with any
module that is reachable at import time — including packages bundled
into the Pyodide image and packages fetched via `micropip`. Pair them
with [`preload_component`][wybthon.preload_component] to warm caches
ahead of navigation.

Public surface:

- [`lazy`][wybthon.lazy]: build a component from a `loader` callback
  returning `(module_path, attr?)`.
- [`load_component`][wybthon.load_component]: build a component
  directly from a known module path / attribute name.
- [`preload_component`][wybthon.preload_component]: eagerly import a
  component to populate the module cache.

See Also:
    - [Suspense and lazy loading guide](../concepts/suspense-lazy.md)
"""

from __future__ import annotations

import importlib
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Union

from .reactivity import ReactiveProps, Signal, read_prop
from .vnode import VNode, dynamic, h

__all__ = ["lazy", "load_component", "preload_component"]

LoadFn = Callable[[], Union[Awaitable[Any], Any]]


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


def _props_to_dict(props: Any) -> Dict[str, Any]:
    """Convert [`ReactiveProps`][wybthon.ReactiveProps] (or plain dict) into a snapshot."""
    if isinstance(props, ReactiveProps):
        return {k: props.value(k) for k in props}
    return dict(props) if hasattr(props, "items") else {}


def load_component(module_path: str, attr: Optional[str] = None) -> Callable[[Any], VNode]:
    """Dynamically import a module and return a component wrapping the export.

    The returned function component renders a small loader until the
    module finishes importing. On success it renders the loaded
    component with the forwarded props; on error it renders a minimal
    error message.

    Args:
        module_path: Importable Python module path.
        attr: Optional attribute name on the loaded module. When
            omitted, the loader picks an export by convention
            (`Page`, `Component`, `Default`, or first PascalCase symbol).

    Returns:
        A function component that proxies its props to the loaded
        component once it becomes available.
    """
    loaded: Signal[Optional[Any]] = Signal(None)
    error_sig: Signal[Optional[Any]] = Signal(None)

    def _do_import() -> None:
        try:
            mod = importlib.import_module(module_path)
            comp = _resolve_attr(mod, attr)
            loaded.set(comp)
        except Exception as e:  # pragma: no cover - depends on runtime module availability
            error_sig.set(e)

    try:
        _do_import()
    except Exception as e:
        error_sig.set(e)

    def _Component(props: Any) -> Any:
        def render() -> VNode:
            comp = loaded.get()
            err = error_sig.get()
            if comp is None and err is None:
                fallback = read_prop(props, "fallback", "Loading...")
                return h("div", {"class": "lazy-loading"}, fallback)
            if err is not None:
                return h("div", {"class": "lazy-error"}, f"Failed to load: {err}")
            return h(comp, _props_to_dict(props))

        return dynamic(render)

    _Component._wyb_component = True  # type: ignore[attr-defined]
    return _Component


def lazy(loader: Callable[[], Tuple[str, Optional[str]]]) -> Callable[[Any], VNode]:
    """Create a lazily-loaded component from a `loader` callback.

    Args:
        loader: Callable returning `(module_path, attr_name)`. The
            second item may be `None` to fall back to the standard
            export convention (`Page`, `Component`, `Default`, or first
            PascalCase symbol).

    Returns:
        A function component that imports the target module on first
        render and forwards props to the resolved component.

    Example:
        ```python
        def UserPageLazy():
            return ("app.users.page", "Page")

        Route(path="/users/:id", component=lazy(UserPageLazy))
        ```
    """
    loaded: Signal[Optional[Any]] = Signal(None)
    error_sig: Signal[Optional[Any]] = Signal(None)

    def start_load() -> None:
        try:
            mp, an = loader()
            mod = importlib.import_module(mp)
            comp = _resolve_attr(mod, an)
            loaded.set(comp)
        except Exception as e:
            error_sig.set(e)

    try:
        start_load()
    except Exception as e:  # pragma: no cover
        error_sig.set(e)

    def _Component(props: Any) -> Any:
        def render() -> VNode:
            comp = loaded.get()
            err = error_sig.get()
            if comp is None and err is None:
                fallback = read_prop(props, "fallback", "Loading...")
                return h("div", {"class": "lazy-loading"}, fallback)
            if err is not None:
                return h("div", {"class": "lazy-error"}, f"Failed to load: {err}")
            return h(comp, _props_to_dict(props))

        return dynamic(render)

    _Component._wyb_component = True  # type: ignore[attr-defined]
    return _Component


def preload_component(module_path: str, attr: Optional[str] = None) -> None:
    """Eagerly import a component to warm caches before navigation.

    Errors are swallowed so this helper can be safely called as a
    "best effort" warmup (for example from a hover handler on a
    `<Link>`).

    Args:
        module_path: Importable Python module path.
        attr: Optional attribute name on the loaded module.
    """
    try:
        mod = importlib.import_module(module_path)
        _resolve_attr(mod, attr)
    except Exception:
        pass

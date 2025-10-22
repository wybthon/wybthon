"""Helpers for lazy-loading components with simple loading/error states."""

from __future__ import annotations

import importlib
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Union

from .reactivity import Signal, effect, signal
from .vdom import VNode, h

__all__ = ["lazy", "load_component", "preload_component"]

LoadFn = Callable[[], Union[Awaitable[Any], Any]]


def _resolve_attr(mod: Any, attr: Optional[str]) -> Any:
    """Pick an exported component by name or by convention from a module."""
    if not attr:
        # Prefer `Page` then `default` then first callable/class in module
        for candidate in ("Page", "default"):
            if hasattr(mod, candidate):
                return getattr(mod, candidate)
        # Fallback: search attributes for a callable/class export
        for name in dir(mod):
            if name.startswith("__"):
                continue
            obj = getattr(mod, name)
            if callable(obj):
                return obj
        raise AttributeError("No export found to use as component")
    return getattr(mod, attr)


def load_component(module_path: str, attr: Optional[str] = None) -> Callable[[Dict[str, Any]], VNode]:
    """Dynamically import a module (optionally attribute) and return a function component factory.

    The returned function component will render a small loader until the module
    is imported. On success it will render the loaded component with the same
    props. On error, it renders a minimal error text.

    This utility is Pyodide-friendly: it uses Python's import system, which
    is compatible with packages pre-bundled or fetched via micropip. Use
    `preload_component` to warm the cache.
    """

    loaded: Signal[Optional[Callable[[Dict[str, Any]], VNode]]] = signal(None)
    error_sig: Signal[Optional[Any]] = signal(None)

    def _do_import() -> None:
        try:
            mod = importlib.import_module(module_path)
            comp = _resolve_attr(mod, attr)

            # Wrap class components into h(class, props) and allow function components to pass through
            def as_vnode(props: Dict[str, Any]) -> VNode:
                from .component import Component  # local import to avoid cycles

                if isinstance(comp, type) and issubclass(comp, Component):
                    return h(comp, props)
                sub = comp(props)
                if isinstance(sub, VNode):
                    return sub
                return h("div", {}, sub)

            loaded.set(as_vnode)
        except Exception as e:  # pragma: no cover - depends on runtime module availability
            error_sig.set(e)

    # Kick off import immediately (sync). In Pyodide, heavy modules might still be async-resolved
    # by the loader, but Python import is synchronous from the view of this function.
    try:
        _do_import()
    except Exception as e:
        error_sig.set(e)

    def _Component(props: Dict[str, Any]) -> VNode:
        comp_fn = loaded.get()
        err = error_sig.get()
        if comp_fn is None and err is None:
            # Trigger a re-render when load completes
            def tick() -> None:
                if loaded.get() is not None or error_sig.get() is not None:
                    # No op; reads signals to subscribe
                    pass

            effect(tick)
            return h("div", {"class": "lazy-loading"}, props.get("fallback", "Loading..."))
        if err is not None:
            return h("div", {"class": "lazy-error"}, f"Failed to load: {err}")
        # got it
        return comp_fn(props)

    return _Component


def lazy(loader: Callable[[], Tuple[str, Optional[str]]]) -> Callable[[Dict[str, Any]], VNode]:
    """Create a lazily-loaded component from a loader that returns (module_path, attr_name?).

    Example:
        def UserPageLazy():
            return ("app.users.page", "Page")

        Route(path="/users/:id", component=lazy(UserPageLazy))
    """

    module_path: Signal[Optional[str]] = signal(None)
    attr_name: Signal[Optional[str]] = signal(None)
    loaded: Signal[Optional[Callable[[Dict[str, Any]], VNode]]] = signal(None)
    error_sig: Signal[Optional[Any]] = signal(None)

    def start_load() -> None:
        try:
            mp, an = loader()
            module_path.set(mp)
            attr_name.set(an)
            comp = load_component(mp, an)
            loaded.set(comp)
        except Exception as e:
            error_sig.set(e)

    # Start load immediately
    try:
        start_load()
    except Exception as e:  # pragma: no cover
        error_sig.set(e)

    def _Component(props: Dict[str, Any]) -> VNode:
        comp_fn = loaded.get()
        err = error_sig.get()
        if comp_fn is None and err is None:

            def tick() -> None:
                if loaded.get() is not None or error_sig.get() is not None:
                    pass

            effect(tick)
            return h("div", {"class": "lazy-loading"}, props.get("fallback", "Loading..."))
        if err is not None:
            return h("div", {"class": "lazy-error"}, f"Failed to load: {err}")
        return comp_fn(props)

    return _Component


def preload_component(module_path: str, attr: Optional[str] = None) -> None:
    """Eagerly import a component to warm caches before navigation."""
    try:
        mod = importlib.import_module(module_path)
        _resolve_attr(mod, attr)
    except Exception:
        # Ignore preload errors; actual render will surface them
        pass

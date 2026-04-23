"""Helpers for lazy-loading components with simple loading/error states."""

from __future__ import annotations

import importlib
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Union

from .reactivity import ReactiveProps, Signal, read_prop
from .vnode import VNode, dynamic, h

__all__ = ["lazy", "load_component", "preload_component"]

LoadFn = Callable[[], Union[Awaitable[Any], Any]]


def _resolve_attr(mod: Any, attr: Optional[str]) -> Any:
    """Pick an exported component by name or by convention from a module."""
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
    """Convert ``ReactiveProps`` (or plain dict) into a plain dict snapshot."""
    if isinstance(props, ReactiveProps):
        return {k: props.value(k) for k in props}
    return dict(props) if hasattr(props, "items") else {}


def load_component(module_path: str, attr: Optional[str] = None) -> Callable[[Any], VNode]:
    """Dynamically import a module (optionally attribute) and return a component.

    The returned function component renders a small loader until the module
    is imported.  On success it renders the loaded component with the
    forwarded props.  On error it renders a minimal error message.

    Pyodide-friendly: uses Python's import system, so packages pre-bundled
    or fetched via ``micropip`` work transparently.  Pair with
    :func:`preload_component` to warm caches before navigation.
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
    """Create a lazily-loaded component from a loader returning ``(module_path, attr_name?)``.

    Example::

        def UserPageLazy():
            return ("app.users.page", "Page")

        Route(path="/users/:id", component=lazy(UserPageLazy))
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
    """Eagerly import a component to warm caches before navigation."""
    try:
        mod = importlib.import_module(module_path)
        _resolve_attr(mod, attr)
    except Exception:
        pass

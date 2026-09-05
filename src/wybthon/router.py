"""Client-side router components and navigation helpers for Pyodide apps.

This module exposes the browser-facing router built on top of
[`router_core`][wybthon.router_core]:

- [`Route`][wybthon.Route]: declarative mapping of a path pattern to
  a component, optionally with nested children.
- [`Router`][wybthon.Router]: component that renders the matched
  route's component and provides the route context.
- [`Link`][wybthon.Link]: anchor element that navigates via the
  History API and toggles an active class.
- [`navigate`][wybthon.navigate]: programmatic navigation helper.
- [`current_path`][wybthon.current_path]: accessor for the current
  pathname plus query string.
- [`use_params`][wybthon.use_params] / [`use_query`][wybthon.use_query]:
  accessors for the matched route's params and the parsed query string.

The matched component receives `params` and `query` as reactive props,
so navigating between `/users/1` and `/users/2` updates the mounted
component's props instead of remounting it.

Example:
    ```python
    @component
    def User(params: Prop[dict]):
        return h1("User ", lambda: params()["id"])

    Router(
        [Route("/", Home), Route("/users/:id", User)],
        not_found=NotFound,
    )

    Link("Home", href="/")
    ```

See Also:
    - [Routing guide](../concepts/router.md)
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

from .component import component
from .context import Context, create_context, use_context
from .html import a
from .reactivity import _core
from .reactivity._core import Accessor, Prop, Signal, is_accessor
from .reactivity._primitives import create_memo
from .reactivity._props import Props, prop
from .router_core import resolve as _resolve_core
from .vnode import VNode, h

__all__ = [
    "Route",
    "Router",
    "Link",
    "navigate",
    "current_path",
    "use_params",
    "use_query",
    "use_base_path",
    "use_hash",
    "Outlet",
    "QueryParams",
    "preload",
]


def _current_url() -> str:
    """Return the current pathname plus search string, or `"/"` on failure."""
    try:
        from js import window

        return str(window.location.pathname) + str(window.location.search) + str(getattr(window.location, "hash", ""))
    except Exception:
        return "/"


_path: Signal[str] = Signal(_current_url(), name="current_path")

current_path: Accessor[str] = _path
"""Accessor for the current pathname plus query string.

Updated by [`navigate`][wybthon.navigate] and by the global `popstate`
listener (back/forward navigation). Read it inside reactive scopes to
re-render when the URL changes.
"""

_popstate_proxy: Any = None


def _install_popstate() -> None:
    """Install the `popstate` listener once when running in a browser."""
    global _popstate_proxy
    if _popstate_proxy is not None:
        return
    try:
        from js import window
        from pyodide.ffi import create_proxy

        def _on_popstate(_evt: Any) -> None:
            _path._set(_current_url())

            def restore() -> None:
                if _core._tx is not None:
                    _core._tx.reverts.append(lambda: _core._settled_queue.append(_restore_scroll))
                else:
                    _restore_scroll()

            _core._settled_queue.append(restore)

        _popstate_proxy = create_proxy(_on_popstate)
        window.addEventListener("popstate", _popstate_proxy)
        window.addEventListener("hashchange", _popstate_proxy)
    except Exception:
        pass


_install_popstate()


_scroll_positions: dict[str, tuple[float, float]] = {}


def _restore_scroll() -> None:
    try:
        from js import window

        position = _scroll_positions.get(_path.peek(), (0, 0))
        window.scrollTo(*position)
    except (ImportError, AttributeError):
        pass


def navigate(path: str, *, replace: bool = False, scroll: bool = True) -> None:
    """Navigate within this origin, resolving relative URLs and preserving hashes.

    External URLs use normal browser navigation. Back/forward restores recorded
    scroll positions; ordinary navigation scrolls to a hash target or the top
    once the destination's transition commits.
    """
    target = urlsplit(path)
    external = bool(target.scheme or target.netloc)
    try:
        from js import window

        origin = str(window.location.origin)
        if external and target.scheme + "://" + target.netloc != origin:
            window.location.assign(path)
            return
        _scroll_positions[_path.peek()] = (float(getattr(window, "scrollX", 0)), float(getattr(window, "scrollY", 0)))
        if len(_scroll_positions) > 256:
            _scroll_positions.pop(next(iter(_scroll_positions)))
        resolved = urlsplit(urljoin(origin + _current_url(), path))
        canonical = (
            resolved.path
            + ("?" + resolved.query if resolved.query else "")
            + ("#" + resolved.fragment if resolved.fragment else "")
        )
        if replace:
            window.history.replaceState(None, "", canonical)
        else:
            window.history.pushState(None, "", canonical)
    except (ImportError, AttributeError):
        if external:
            return
        canonical = urljoin(_path.peek(), path)
    _path._set(canonical)
    if scroll:

        def after_commit() -> None:
            def position() -> None:
                try:
                    from js import document, window

                    fragment = urlsplit(canonical).fragment
                    element = document.getElementById(_decode(fragment)) if fragment else None
                    if element is not None:
                        element.scrollIntoView()
                    else:
                        window.scrollTo(0, 0)
                except (ImportError, AttributeError):
                    pass

            if _core._tx is not None:
                _core._tx.reverts.append(lambda: _core._settled_queue.append(position))
            else:
                position()

        _core._settled_queue.append(after_commit)


class QueryParams(dict[str, str]):
    """Decoded query parameters with last-value lookup and ``get_all``."""

    def __init__(self, search: str = "") -> None:
        self._pairs = parse_qsl(search.removeprefix("?"), keep_blank_values=True)
        super().__init__(self._pairs)

    def get_all(self, key: str) -> list[str]:
        """Return every occurrence in URL order."""
        return [value for name, value in self._pairs if name == key]


def _parse_query(search: str) -> QueryParams:
    """Parse a query string like `"?a=1&b=2"` into a dict, decoding values."""
    return QueryParams(search)


def _decode(s: str) -> str:
    """Decode a URL-encoded component."""
    try:
        from urllib.parse import unquote_plus

        return unquote_plus(s)
    except Exception:
        return s


def _split_path(path: str) -> tuple[str, str]:
    parsed = urlsplit(path)
    return parsed.path or "/", "?" + parsed.query if parsed.query else ""


@dataclass
class Route:
    """Declarative route definition mapping a path to a component.

    Attributes:
        path: Route pattern (e.g., `"/users/:id"`, `"/docs/*"`).
        component: The component to render when the path matches. It
            receives `params` and `query` props, accessors yielding the
            path parameters and query string as dicts.
        children: Optional nested routes whose paths are joined with
            this route's `path`.
    """

    path: str
    component: Any
    children: list[Route] = field(default_factory=list)
    preload: Callable[[dict[str, Any]], Any] | None = None


class _RouteState:
    __slots__ = ("params", "query", "base_path", "preload")

    def __init__(self, params: Accessor[dict[str, Any]], query: Accessor[QueryParams], base_path: str) -> None:
        self.params = params
        self.query = query
        self.base_path = base_path
        self.preload: Callable[[str], Any] | None = None


RouteContext: Context[_RouteState | None] = create_context(None, name="Route")
"""Context the router provides to the matched subtree (params, query, base path)."""


def use_params() -> Accessor[dict[str, Any]]:
    """Accessor for the matched route's params (`{}` outside a router)."""
    state = use_context(RouteContext)
    if state is None:
        return create_memo(lambda: {})
    return state.params


def use_query() -> Accessor[QueryParams]:
    """Accessor for the parsed query string (`{}` outside a router)."""
    state = use_context(RouteContext)
    if state is None:
        return create_memo(QueryParams)
    return state.query


def use_base_path() -> str:
    """The base path of the surrounding [`Router`][wybthon.Router] (`""` outside one)."""
    state = use_context(RouteContext)
    return state.base_path if state is not None else ""


def Router(routes: Any, *, base_path: Any = "", not_found: Any = None) -> VNode:
    """Render the component of the route matching [`current_path`][wybthon.current_path].

    Only a change in *which* route matches re-mounts the outlet; param
    and query changes flow into the mounted component as prop updates.

    Args:
        routes: A list of [`Route`][wybthon.Route]s (or an accessor
            returning one).
        base_path: Base path stripped before matching, and prepended
            by [`Link`][wybthon.Link]s underneath.
        not_found: Optional component rendered when no route matches.
            Falls back to a literal `"Not Found"` `<div>`.

    Returns:
        A component [`VNode`][wybthon.VNode].
    """
    return h(_Router, {"routes": routes, "base_path": base_path, "not_found": not_found})


@component
def _Router(routes: Prop[list[Route]], base_path: Prop[str] = prop(""), not_found: Prop[Any] = prop(None)) -> Any:
    def location() -> tuple[str, str]:
        return _split_path(current_path())

    pathname = create_memo(lambda: location()[0])
    query = create_memo(lambda: _parse_query(location()[1]))

    def resolved() -> Any:
        result = _resolve_core(routes() or [], pathname(), base_path() or "")
        return result[1] if result is not None else {"params": {}, "matches": []}

    match = create_memo(resolved)
    matches = create_memo(lambda: match()["matches"])
    params = create_memo(lambda: match()["params"])
    state = _RouteState(params, query, base_path.peek() or "")
    warmed: dict[tuple[int, str], Any] = {}

    def preload_path(path: str) -> Any:
        result = _resolve_core(routes(), path, base_path() or "")
        if result is None:
            return None
        _, info = result
        tasks = []
        for route in info["matches"]:
            loader = getattr(route.component, "preload", None)
            if loader is not None:
                loader()
            if route.preload is not None:
                key = (id(route), path)
                if key not in warmed:
                    value = route.preload(info["params"])
                    warmed[key] = asyncio.ensure_future(value) if inspect.isawaitable(value) else value
                    if isinstance(warmed[key], asyncio.Future):

                        def settled(future: asyncio.Future[Any], key: tuple[int, str] = key) -> None:
                            if future.cancelled() or future.exception() is not None:
                                if warmed.get(key) is future:
                                    warmed.pop(key, None)

                        warmed[key].add_done_callback(settled)
                    if len(warmed) > 64:
                        removed = warmed.pop(next(iter(warmed)))
                        if isinstance(removed, asyncio.Future) and not removed.done():
                            removed.cancel()
                value = warmed[key]
                if inspect.isawaitable(value):
                    tasks.append(value)
        if tasks:

            async def wait() -> None:
                await asyncio.gather(*(asyncio.shield(task) for task in tasks))

            return wait()
        return None

    state.preload = preload_path

    def ready() -> Any:
        path = current_path()
        value = preload_path(path)
        if inspect.isawaitable(value):

            async def wait() -> bool:
                await value
                return True

            return wait()
        return True

    readiness = create_memo(ready)

    def level(depth: int) -> VNode:
        def outlet() -> Any:
            readiness()
            chain = matches()
            if depth >= len(chain):
                if depth:
                    return None
                nf = not_found()
                return h(nf, {"params": params, "query": query}) if nf else h("div", {}, "Not Found")
            matched = chain[depth]
            return h(
                _RouteEntry,
                {
                    "route": matched,
                    "params": params,
                    "query": query,
                    "matches": matches,
                    "router_state": state,
                    "key": id(matched),
                },
            )

        return OutletContext(lambda: level(depth + 1), outlet)

    def cleanup() -> None:
        for value in warmed.values():
            if isinstance(value, asyncio.Future) and not value.done():
                value.cancel()
        warmed.clear()

    _core._current_owner._add_cleanup(cleanup)
    return RouteContext(state, lambda: level(0))


def _RouteEntry(props: Props) -> Any:
    route = props.raw("route")
    parent = props.raw("router_state")
    # A departing route keeps its last inputs until unmount. Preparing the
    # destination mustn't give its still-mounted predecessor missing params.
    params = create_memo(lambda previous: props.params() if route in props.matches() else (previous or {}))
    query = create_memo(lambda previous: props.query() if route in props.matches() else (previous or QueryParams()))
    state = _RouteState(params, query, parent.base_path)
    state.preload = parent.preload
    return RouteContext(state, lambda: h(route.component, {"params": params, "query": query}))


_Router.__name__ = "Router"


OutletContext: Context[Any] = create_context(None, name="Outlet")


def Outlet() -> VNode:
    """Render the next matched child route inside a persistent parent layout."""
    return h(_Outlet)


def _Outlet(props: Props) -> Any:
    child = use_context(OutletContext)
    return child if child is not None else None


def use_hash() -> Accessor[str]:
    """Read the decoded current URL fragment, without its leading hash."""
    return create_memo(lambda: _decode(urlsplit(current_path()).fragment))


def preload(path: str) -> Any:
    """Warm route code and data through the surrounding router."""
    state = use_context(RouteContext)
    return state.preload(_with_base(path, state.base_path)) if state is not None and state.preload else None


def _with_base(target: str, base_path: str) -> str:
    if not isinstance(target, str):
        return "/"
    if urlsplit(target).scheme or target.startswith(("//", "#", "?")):
        return target
    if not base_path:
        return target
    if target.startswith("/"):
        if base_path == "/":
            return target
        return (base_path.rstrip("/") or "/") + target
    if base_path == "/":
        return "/" + target.strip("/")
    return (base_path.rstrip("/") or "") + "/" + target.strip("/")


def _class_names(value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if is_accessor(value):
        value = value()
    if isinstance(value, str):
        return value.split()
    if isinstance(value, dict):
        out: list[str] = []
        for name, on in value.items():
            if is_accessor(on):
                on = on()
            if on:
                out.extend(str(name).split())
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_class_names(item))
        return out
    return [str(value)]


def Link(
    *children: Any,
    href: Any = "/",
    replace: bool = False,
    active_class: str | None = "active",
    end: bool = False,
    **rest: Any,
) -> VNode:
    """An anchor that navigates with the History API and marks itself active.

    Modifier-key clicks (Cmd/Ctrl/Shift) and middle-clicks are passed
    through to the browser so users can open links in a new tab.

    Args:
        *children: Link content.
        href: Target path (or an accessor). Joined with the surrounding
            router's base path unless it starts with `http://`,
            `https://`, or `#`.
        replace: Replace the current history entry instead of pushing.
        active_class: Class added while the link matches the current
            path. `None` disables the active class.
        end: When `True`, the link is active only on an exact match;
            otherwise it's also active for nested paths.
        **rest: Forwarded to the `<a>` element (`class_`, `on_click`,
            `aria_label`, ...).

    Example:
        ```python
        Link("Users", href="/users", class_="nav-link", end=True)
        ```
    """
    return h(
        _Link,
        {
            "href": href,
            "replace": replace,
            "active_class": active_class,
            "end": end,
            "children": list(children),
            **rest,
        },
    )


def _Link(props: Props) -> Any:
    from .events import DomEvent

    base_path = use_base_path()
    href = props.href
    replace = props.replace
    active_class = props.active_class
    end = props.end
    user_class = props.raw("class_")
    children = props.raw("children") or []
    forwarded = {k: props.raw(k) for k in props if k not in _LINK_OWN}

    def full_href() -> str:
        return _with_base(href(), base_path)

    def is_active() -> bool:
        current = _split_path(current_path())[0]
        target = _split_path(full_href())[0]
        if current == target:
            return True
        if end():
            return False
        return target != "/" and current.startswith(target.rstrip("/") + "/")

    def classes() -> str | None:
        names = _class_names(user_class)
        ac = active_class()
        if ac and is_active():
            names.extend(str(ac).split())
        return " ".join(dict.fromkeys(names)) or None

    def handle_click(evt: DomEvent) -> None:
        user_click = props.raw("on_click")
        if callable(user_click):
            result = user_click(evt)
            if inspect.isawaitable(result):
                from .events import _handle_async_error

                owner = _core._current_owner
                _core._drive_coroutine(
                    result,
                    owner=owner,
                    observer=None,
                    alive=lambda: owner is None or not owner._disposed,
                    on_done=lambda value: None,
                    on_error=_handle_async_error,
                )
        if evt._default_prevented or evt.meta_key or evt.ctrl_key or evt.shift_key or evt.alt_key or evt.button != 0:
            return
        target = full_href()
        if props.raw("download") is not None or props.raw("target") not in (None, "", "_self"):
            return
        if target.startswith("#") or urlsplit(target).scheme or target.startswith("//"):
            return
        evt.prevent_default()
        navigate(full_href(), replace=bool(replace()))

    route_state = use_context(RouteContext)

    def warm(evt: Any) -> Any:
        return route_state.preload(full_href()) if route_state is not None and route_state.preload else None

    forwarded.setdefault("on_mouseenter", warm)
    forwarded.setdefault("on_focus", warm)
    return a(*children, href=full_href, class_=classes, on_click=handle_click, **forwarded)


_Link.__name__ = "Link"
_LINK_OWN = frozenset({"href", "replace", "active_class", "end", "children", "class_", "on_click"})

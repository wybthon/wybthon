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

from dataclasses import dataclass, field
from typing import Any

from .component import component
from .context import Context, create_context, use_context
from .html import a
from .reactivity._core import Accessor, Prop, Signal, is_accessor
from .reactivity._primitives import create_memo
from .reactivity._props import Props, prop
from .router_core import resolve as _resolve_core
from .vnode import VNode, h

__all__ = ["Route", "Router", "Link", "navigate", "current_path", "use_params", "use_query", "use_base_path"]


def _current_url() -> str:
    """Return the current pathname plus search string, or `"/"` on failure."""
    try:
        from js import window

        return str(window.location.pathname) + str(window.location.search)
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

        _popstate_proxy = create_proxy(_on_popstate)
        window.addEventListener("popstate", _popstate_proxy)
    except Exception:
        pass


_install_popstate()


def navigate(path: str, *, replace: bool = False) -> None:
    """Programmatically change the current path and update `current_path`.

    Args:
        path: Target URL path, including any query string.
        replace: When `True`, use `history.replaceState` so the
            current history entry is overwritten instead of appended.
    """
    try:
        from js import window

        if replace:
            window.history.replaceState(None, "", path)
        else:
            window.history.pushState(None, "", path)
    except Exception:
        pass
    _path._set(path)


def _parse_query(search: str) -> dict[str, str]:
    """Parse a query string like `"?a=1&b=2"` into a dict, decoding values."""
    if not search or not search.startswith("?"):
        return {}
    out: dict[str, str] = {}
    for part in search[1:].split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        out[_decode(k)] = _decode(v)
    return out


def _decode(s: str) -> str:
    """Decode a URL-encoded component."""
    try:
        from urllib.parse import unquote_plus

        return unquote_plus(s)
    except Exception:
        return s


def _split_path(path: str) -> tuple[str, str]:
    if "?" in path:
        pathname, search = path.split("?", 1)
        return pathname, "?" + search
    return path, ""


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


class _RouteState:
    __slots__ = ("params", "query", "base_path")

    def __init__(self, params: Accessor[dict[str, Any]], query: Accessor[dict[str, str]], base_path: str) -> None:
        self.params = params
        self.query = query
        self.base_path = base_path


RouteContext: Context[_RouteState | None] = create_context(None, name="Route")
"""Context the router provides to the matched subtree (params, query, base path)."""


def use_params() -> Accessor[dict[str, Any]]:
    """Accessor for the matched route's params (`{}` outside a router)."""
    state = use_context(RouteContext)
    if state is None:
        return create_memo(lambda: {})
    return state.params


def use_query() -> Accessor[dict[str, str]]:
    """Accessor for the parsed query string (`{}` outside a router)."""
    state = use_context(RouteContext)
    if state is None:
        return create_memo(lambda: {})
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

    def resolved() -> tuple[Route | None, dict[str, Any]]:
        result = _resolve_core(routes() or [], pathname(), base_path() or "")
        if result is None:
            return None, {}
        route, info = result
        return route, dict(info.get("params") or {})

    match = create_memo(resolved)
    route = create_memo(lambda: match()[0])
    params = create_memo(lambda: match()[1])

    def outlet() -> Any:
        matched = route()
        if matched is None:
            nf = not_found()
            if nf is not None:
                return h(nf, {"params": params, "query": query})
            return h("div", {}, "Not Found")
        return h(matched.component, {"params": params, "query": query})

    return RouteContext(_RouteState(params, query, base_path.peek() or ""), outlet)


_Router.__name__ = "Router"


def _with_base(target: str, base_path: str) -> str:
    if not isinstance(target, str):
        return "/"
    if target.startswith(("http://", "https://", "#")):
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
    user_click = props.raw("on_click")
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
        if callable(user_click):
            user_click(evt)
        if evt.meta_key or evt.ctrl_key or evt.shift_key or evt.button != 0:
            return
        evt.prevent_default()
        navigate(full_href(), replace=bool(replace()))

    return a(*children, href=full_href, class_=classes, on_click=handle_click, **forwarded)


_Link.__name__ = "Link"
_LINK_OWN = frozenset({"href", "replace", "active_class", "end", "children", "class_", "on_click"})
